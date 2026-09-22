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
  软性（整体）  valence/energy/loudness 朝**选定的叙事弧**（--arc，默认 man-in-a-hole）
                tempo 走倒 U 型（快的放中段；排序惯例，不随形状变）
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
                                [--arc man-in-a-hole|cinderella|icarus|...]
    python playlist_optimize.py --list-shapes   # 列出六个可选形状
    python playlist_optimize.py                 # 不给参数时打印本说明
"""

from __future__ import annotations

import json
import math
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import am_paths as ap  # noqa: E402

# Windows 控制台默认 GBK；唯一实现在 am_paths
ap.enable_utf8_stdout()
# 从**平台无关**的 core 取乐理与规则判定，而不是从 playlist_flow。
# playlist_flow 会 import am_playlist（Apple 层），从它取会让这个纯算法模块
# 间接依赖某个音乐平台——接第二个平台时算法层不该认识任何平台的代码。
from playlist_core import (  # noqa: E402
    DEFAULT_SHAPE,
    SHAPE_ALIASES,
    camelot,
    check_pair,
    classify_coverage,
    coverage_report,
    fold_tempo,
    resolve_shape,
    shape_target,
    tempo_target,
)


def resolve_feature_cache(explicit=None) -> Path | None:
    """特征缓存文件：显式路径优先，否则取缓存目录下**最新写入**的那个。

    这终究是"猜"——多张歌单的缓存混在一起时会拿错，所以调用方应该把
    选中的文件路径打出来。缓存目录顺序见 am_paths.read_dirs()
    （先用户目录，再旧版的仓库内 refs/）。
    """
    if explicit and Path(explicit).exists():
        return Path(explicit)
    files: list[Path] = []
    for d in ap.read_dirs():
        if d.exists():
            files.extend(d.glob("features-*.json"))
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


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
# 键名与 playlist_core.RULES 一一对应：这样"哪条规则被触发"和"它有多重"
# 用的是同一套词汇，不会再出现两处各写一份判定。
WEIGHTS = {
    "two_slow": 6.0,
    "small_drop": 3.0,
    "both_similar": 3.0,
    "big_jump": 1.5,
    "energy_clash": 2.0,
}

# 旧名字保留成别名（文档和既有脚本里在用）
W_TWO_SLOW = WEIGHTS["two_slow"]
W_SMALL_DROP = WEIGHTS["small_drop"]
W_BOTH_SIMILAR = WEIGHTS["both_similar"]
W_BIG_TEMPO_JUMP = WEIGHTS["big_jump"]
W_ENERGY_CLASH = WEIGHTS["energy_clash"]

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
                # 记下**为什么**没特征。优化器只看得见特征缓存，所以它能分清
                # "源没收录"和"压根没抓过"，但说不出"没有 ISRC"——那是上游的事。
                # 关键是不再压成一个笼统的 None：覆盖率报告要据此给出可行动的分解。
                stage = ("source-miss" if (f or {}).get("_miss")
                         else "not-in-cache" if not f
                         else "no-features")
                tracks.append({"cid": cid, "block": blk["id"],
                               "name": (f or {}).get("_name", cid), "f": None,
                               "stage": stage})
                continue
            tracks.append({
                "cid": cid, "block": blk["id"],
                "name": f.get("_name", cid),
                "f": f,
                "stage": "ok",
                "bpm": fold_tempo(f.get("tempo", 0)),
                "key": camelot(f.get("key", 0), f.get("mode", 0)),
                "energy": f.get("energy", 0.0),
                "valence": f.get("valence", 0.0),
                "loud": f.get("loudness", -20.0),
            })
    return spec, tracks


def adjacency_cost(seq):
    """相邻衔接的惩罚之和。

    **判定全部走 playlist_core.check_pair** —— 与体检器同源。
    这里只负责把命中的规则折算成权重，不再自己判一遍。
    """
    return sum(WEIGHTS[r]
               for a, b in zip(seq, seq[1:])
               if a.get("f") and b.get("f")
               for r in check_pair(a, b))


def arc_cost(seq, shape=DEFAULT_SHAPE):
    """整体形状约束（§3.1 + §4）。

    目标曲线来自 `playlist_core.ARCHETYPES` —— 与体检器"认出你是什么形状"用的是
    **同一份**曲线定义。这里以前硬编码 man-in-a-hole（valence 谷底在 60%），
    而策划文档把"先选一个形状"列为第一步：那一步当时只有诊断价值，工具并没有
    按你选的形状去排。

      valence / energy / loudness → 选定的叙事弧（情绪走向）
      tempo                       → 倒 U（快的放中段；排序惯例，不随形状变）
    """
    known = [(i, t) for i, t in enumerate(seq) if t["f"]]
    if len(known) < 5:
        return 0.0
    n = len(seq)
    mood = shape_target(shape, n)
    specs = [("valence", mood), ("energy", mood), ("loud", mood),
             ("bpm", tempo_target(n))]
    total = 0.0
    for key, target in specs:
        vs = [t[key] for _, t in known]
        lo, hi = min(vs), max(vs)
        rng = (hi - lo) or 1.0
        for i, t in known:
            actual = (t[key] - lo) / rng
            total += (actual - target[i]) ** 2
    return W_ARC * total / (len(known) * len(specs))


def total_cost(seq, shape=DEFAULT_SHAPE):
    return adjacency_cost(seq) + arc_cost(seq, shape)


def anneal(blocks, iters=60000, seed=7, shape=DEFAULT_SHAPE):
    rng = random.Random(seed)
    seq = [t for blk in blocks for t in blk]
    cur = total_cost(seq, shape)
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
        new = total_cost(seq, shape)
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


def optimize(spec_file, features_file=None, out_file=None, shape=DEFAULT_SHAPE):
    """跑模拟退火，返回 (ids, 报告文本)。

    分组清单只做组内重排（保留分组顺序）；平铺清单整张自由重排。
    shape 是目标叙事弧（见 playlist_core.SHAPE_ALIASES）。
    """
    import contextlib
    import io

    spec, tracks = load_tracks(spec_file, features_file)
    blocks = [[t for t in tracks if t["block"] == blk["id"]] for blk in spec]

    before = [t for blk in blocks for t in blk]
    seq, cost = anneal(blocks, shape=shape)

    # 把解析后的完整形状名打出来：报告里要能看出"朝哪个形状排的"，
    # 否则体检说"你是 Cinderella、而排序目标是 man-in-a-hole"时没法发现。
    # 覆盖率必须打在最前面。它决定了后面那些 cost 数字到底描述了多少曲目——
    # 覆盖率 60% 时"优化后 cost = 1.15"只说明四成位置没被评估过，
    # 而报告以前完全不提这件事。
    counts = Counter(t.get("stage", "ok") for t in tracks)
    head = (f"目标形状：{resolve_shape(shape)}\n"
            f"载入 {len(tracks)} 首\n"
            f"{coverage_report(counts, len(tracks))}\n"
            f"原始顺序 cost = {total_cost(before, shape):.2f} "
            f"(相邻 {adjacency_cost(before):.2f} + 弧线 {arc_cost(before, shape):.2f})\n"
            f"优化后   cost = {cost:.2f} "
            f"(相邻 {adjacency_cost(seq):.2f} + 弧线 {arc_cost(seq, shape):.2f})")

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ids = report(seq, spec)
    body = buf.getvalue()

    if out_file:
        Path(out_file).write_text(json.dumps({"tracks": ids}, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
        body += f"\n曲序已存: {out_file}"
    return ids, head + body


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv:
        print(__doc__)
        return 2
    if argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    if "--list-shapes" in argv or "--shapes" in argv:
        print("可选的目标形状（--arc <名字>）：")
        for short, full in SHAPE_ALIASES.items():
            print(f"  {short:<16} {full}")
        print(f"\n默认：{DEFAULT_SHAPE}")
        return 0

    spec_file = argv[0]
    features_file = out_file = None
    shape = DEFAULT_SHAPE
    i = 1
    while i < len(argv):
        if argv[i] in ("-o", "--out") and i + 1 < len(argv):
            out_file = argv[i + 1]; i += 2
        elif argv[i] == "--features" and i + 1 < len(argv):
            features_file = argv[i + 1]; i += 2
        elif argv[i] == "--arc" and i + 1 < len(argv):
            shape = argv[i + 1]; i += 2
        else:
            i += 1
    if out_file is None:
        out_file = Path(spec_file).with_name(Path(spec_file).stem + "-order.json")
    try:
        _, text = optimize(spec_file, features_file, out_file, shape=shape)
    except (FileNotFoundError, ValueError) as e:
        print(f"错误: {e}")
        return 1
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
