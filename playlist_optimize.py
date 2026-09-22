#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
playlist_optimize.py — 用模拟退火算出一个「好听」的曲序。

输入是一份**曲目清单**（可分组），输出是重排后的 catalog id 列表，
可以直接喂给 `am_playlist.py create --json` 建歌单。

约束（依据见 docs/how-to-build-a-good-playlist.md）：
  硬性（相邻）  不要两首慢歌相邻
                不要"只慢一点"（降幅 0–12%，会让慢歌显得拖）
                相邻不该在 tempo 和 key 上「同时」相似
                不要 BPM 无理由地大跳（>40%）
                能量骤变且调性不兼容 = 突兀
  软性（整体）  valence/energy/loudness 走 U 型、tempo 走倒 U 型
                valence 走 Man in a hole（先落再起）
  结构约束      分组顺序固定（"有意思"那一层不能为了顺耳牺牲掉）

输入文件两种写法都支持：

  # ① 分组（推荐：保留主题/叙事结构，只在组内重排）
  {"blocks": [ {"id": "A", "title": "起", "tracks": ["1648868895", "..."]},
               {"id": "B", "title": "承", "tracks": ["..."]} ]}

  # ② 平铺（整张自由重排）
  {"tracks": ["1648868895", "1648869409", "..."]}

特征数据从 `playlist_flow.py` 生成的特征缓存里读（按 catalog id 索引）。

用法：
    python playlist_optimize.py <清单.json> [-o 输出.json] [--features 缓存.json]
    python playlist_optimize.py            # 不给参数时打印本说明
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from playlist_flow import camelot, fold_tempo, harmonic_ok  # noqa: E402

ROOT = Path(__file__).resolve().parent
REF_DIR = ROOT / "refs"


def resolve_feature_cache(explicit=None) -> Path | None:
    """特征缓存文件：显式路径优先，否则取 refs/ 下**最新写入**的那个。

    （原来写的是 glob 取第一个，多张歌单的缓存放在一起就会拿错。）
    """
    if explicit and Path(explicit).exists():
        return Path(explicit)
    if not REF_DIR.exists():
        return None
    files = sorted(REF_DIR.glob("features-*.json"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def parse_spec(spec: dict) -> list[dict]:
    """把输入清单规整成 [{id, title, tracks}]。平铺格式会包成一个匿名组。"""
    if "blocks" in spec and spec["blocks"]:
        return [{"id": b.get("id") or f"B{i}", "title": b.get("title", ""),
                 "tracks": list(b["tracks"])}
                for i, b in enumerate(spec["blocks"], 1)]
    if "tracks" in spec and spec["tracks"]:
        return [{"id": "ALL", "title": "（未分组）", "tracks": list(spec["tracks"])}]
    raise ValueError("清单里既没有 blocks 也没有 tracks")

# ---- 权重（调这些就能改"更在意顺耳还是更在意弧线"） ----
W_TWO_SLOW = 6.0
W_SMALL_DROP = 3.0
W_BOTH_SIMILAR = 3.0
W_BIG_TEMPO_JUMP = 1.5
W_ENERGY_CLASH = 2.0
W_ARC = 12.0


def load_tracks(spec_file, features_file=None):
    cache = resolve_feature_cache(features_file)
    if cache is None:
        raise FileNotFoundError(
            "找不到特征缓存。先跑一次：python playlist_flow.py \"歌单名\"")
    feats = json.loads(cache.read_text(encoding="utf-8"))
    # 按 catalog id 建索引（特征缓存里每条都带 _cid）
    by_cid = {}
    for v in feats.values():
        if isinstance(v, dict) and v.get("_cid"):
            by_cid[str(v["_cid"])] = v

    spec = parse_spec(json.loads(Path(spec_file).read_text(encoding="utf-8")))
    tracks = []
    for blk in spec:
        for cid in blk["tracks"]:
            cid = str(cid)
            f = by_cid.get(cid)
            if not f or "tempo" not in f:
                tracks.append({"cid": cid, "block": blk["id"],
                               "name": (f or {}).get("_name", cid), "f": None})
                continue
            tracks.append({
                "cid": cid, "block": blk["id"],
                "name": f.get("_name", cid),
                "f": f,
                "bpm": fold_tempo(f.get("tempo", 0)),
                "key": camelot(f.get("key", 0), f.get("mode", 0)),
                "energy": f.get("energy", 0.0),
                "valence": f.get("valence", 0.0),
                "loud": f.get("loudness", -20.0),
            })
    return spec, tracks


def adjacency_cost(seq):
    c = 0.0
    for a, b in zip(seq, seq[1:]):
        if not a["f"] or not b["f"]:
            continue
        ta, tb = a["bpm"], b["bpm"]
        ka, kb = a["key"], b["key"]
        ea, eb = a["energy"], b["energy"]
        pct = (tb - ta) / ta * 100 if ta else 0
        if ta < 100 and tb < 100:
            c += W_TWO_SLOW
        if ta > tb and 0 < -pct < 12:
            c += W_SMALL_DROP
        if abs(pct) < 6 and harmonic_ok(ka, kb):
            c += W_BOTH_SIMILAR
        if abs(pct) > 40:
            c += W_BIG_TEMPO_JUMP
        if abs(ea - eb) > 0.35 and not harmonic_ok(ka, kb):
            c += W_ENERGY_CLASH
    return c


def arc_cost(seq):
    """
    整体形状约束（§3.1 + §4）：
      valence  → Man in a hole：谷底在 60% 处（先落再起）
      energy   → U 型：谷底在中间
      loudness → U 型：谷底在中间
      tempo    → 倒 U 型：峰值在中间
    """
    known = [(i, t) for i, t in enumerate(seq) if t["f"]]
    if len(known) < 5:
        return 0.0
    n = len(seq)
    specs = [("valence", "V", 0.60), ("energy", "U", 0.50),
             ("loud", "U", 0.50), ("bpm", "A", 0.50)]
    total = 0.0
    for key, kind, center in specs:
        vs = [t[key] for _, t in known]
        lo, hi = min(vs), max(vs)
        rng = (hi - lo) or 1.0
        for i, t in known:
            p = i / (n - 1)
            d = abs(p - center)
            scale = center if p <= center else (1 - center)
            r = (d / scale) if scale else 0.0          # 中心=0，两端=1
            target = (1.0 - r) if kind == "A" else r    # A = 倒 U（中间高）
            actual = (t[key] - lo) / rng
            total += (actual - target) ** 2
    return W_ARC * total / (len(known) * len(specs))


def total_cost(seq):
    return adjacency_cost(seq) + arc_cost(seq)


def anneal(blocks, iters=60000, seed=7):
    rng = random.Random(seed)
    seq = [t for blk in blocks for t in blk]
    cur = total_cost(seq)
    best, best_cost = list(seq), cur
    for k in range(iters):
        T = 2.0 * (1 - k / iters) + 0.01
        # 只块内交换 —— 保证主题分块顺序不被破坏
        bi = rng.randrange(len(blocks))
        if len(blocks[bi]) < 2:
            continue
        i, j = rng.sample(range(len(blocks[bi])), 2)
        start = sum(len(blocks[x]) for x in range(bi))
        a, b = start + i, start + j
        seq[a], seq[b] = seq[b], seq[a]
        new = total_cost(seq)
        if new < cur or rng.random() < math.exp((cur - new) / T):
            cur = new
            if new < best_cost:
                best, best_cost = list(seq), new
        else:
            seq[a], seq[b] = seq[b], seq[a]
    return best, best_cost


def report(seq, blocks_spec):
    ids = [t["cid"] for t in seq]
    order_in_block = {}
    for t in seq:
        order_in_block.setdefault(t["block"], []).append(t["cid"])
    print(f"\n{'='*96}")
    print("优化后的曲序")
    print(f"{'='*96}")
    idx = 0
    for blk in blocks_spec:
        bid = blk["id"]
        print(f"\n── {bid} ──")
        for cid in order_in_block.get(bid, []):
            idx += 1
            t = next(x for x in seq if x["cid"] == cid)
            if t["f"]:
                print(f"{idx:>3}. {str(t['name'])[:34]:<36} {t['bpm']:6.1f}BPM {t['key']:>4} "
                      f"E={t['energy']:.2f} V={t['valence']:.2f}")
            else:
                print(f"{idx:>3}. {str(t['name'])[:34]:<36}   （无特征数据）")
    return ids


def optimize(spec_file, features_file=None, out_file=None):
    """跑模拟退火，返回 (ids, 报告文本)。

    分组清单只做组内重排（保留分组顺序）；平铺清单整张自由重排。
    """
    import contextlib
    import io

    spec, tracks = load_tracks(spec_file, features_file)
    blocks = [[t for t in tracks if t["block"] == blk["id"]] for blk in spec]

    before = [t for blk in blocks for t in blk]
    seq, cost = anneal(blocks)

    head = (f"载入 {len(tracks)} 首（{sum(1 for t in tracks if t['f'])} 首有特征）\n"
            f"原始顺序 cost = {total_cost(before):.2f} "
            f"(相邻 {adjacency_cost(before):.2f} + 弧线 {arc_cost(before):.2f})\n"
            f"优化后   cost = {cost:.2f} "
            f"(相邻 {adjacency_cost(seq):.2f} + 弧线 {arc_cost(seq):.2f})")

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ids = report(seq, spec)
    body = buf.getvalue()

    if out_file:
        Path(out_file).write_text(json.dumps({"tracks": ids}, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
        body += f"\n曲序已存: {out_file}"
    return ids, head + body


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2
    spec_file = argv[0]
    features_file = out_file = None
    i = 1
    while i < len(argv):
        if argv[i] in ("-o", "--out") and i + 1 < len(argv):
            out_file = argv[i + 1]; i += 2
        elif argv[i] == "--features" and i + 1 < len(argv):
            features_file = argv[i + 1]; i += 2
        else:
            i += 1
    if out_file is None:
        out_file = Path(spec_file).with_name(Path(spec_file).stem + "-order.json")
    try:
        _, text = optimize(spec_file, features_file, out_file)
    except (FileNotFoundError, ValueError) as e:
        print(f"错误: {e}")
        return 1
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
