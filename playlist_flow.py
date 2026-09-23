#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
playlist_flow.py — 给歌单做「好听度」体检（BPM / 调性 / 响度 / 能量 / 情绪）

数据链路（全部免费、无需任何密钥）：
    Apple Music 曲目  →  ISRC  →  reccobeats.com /v1/track?ids=<ISRC>  →  UUID
                                →  /v1/audio-features?ids=<UUID>
                                →  tempo, key, mode, loudness, energy, valence,
                                   danceability, acousticness, instrumentalness,
                                   liveness, speechiness

为什么要绕这一圈：**Apple Music 的 catalog API 不提供任何音频特征字段**
（实测字段只有 genreNames/durationInMillis/trackNumber/releaseDate/composerName/
albumName/isrc/artwork...）。而 Spotify 的 audio-features 已于 2024-11-27 对新应用关闭。
ReccoBeats 是当前可用的免费替代，**且直接支持用 ISRC 查询**——ISRC 正好是 Apple 会给的字段。

体检依据（见 docs/how-to-build-a-good-playlist.md）：
  §2.1 不要两首慢歌相邻；不要"只慢一点"（会让慢歌显得拖）
  §2.3 相邻两首不该在 tempo 和 key 上「同时」相似
  §2.4/§3.1 响度前重后轻；valence/arousal/loudness 呈 U 型，tempo 呈倒 U 型
  §3.2 第一首是共识最高、最该单独打磨的位置
  §4   整体弧线形状（man in a hole = 先落再起）

用法：
    python playlist_flow.py "歌单名或 p.xxxx"          # 抓特征（带缓存）+ 体检
    python playlist_flow.py "歌单名" --refresh         # 忽略缓存重抓
"""

from __future__ import annotations

import json
import statistics
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import am_paths as ap  # noqa: E402
import am_playlist as am  # noqa: E402
from am_meta import catalog_meta  # noqa: E402

# Windows 控制台默认 GBK；唯一实现在 am_paths
ap.enable_utf8_stdout()

RB = "https://api.reccobeats.com"
# 缓存写进**用户目录**，不写进仓库。refs/ 曾经是缓存目录，现在只作只读回退
# （见 am_paths.read_dirs）——否则 clone 下来就在仓库里留一堆个人中间产物。
CACHE_DIR = am.cache_dir()

# 乐理与相邻规则的**唯一**实现在 playlist_core.py（平台无关模块）。
# 这里把名字重新导出，`pf.camelot(...)` 这类既有调用不受影响。
from playlist_core import (  # noqa: E402
    ARCHETYPES,
    CAMELOT_MAJOR,
    CAMELOT_MINOR,
    PITCH,
    RULE_LABELS,
    RULES,
    camelot,
    classify_coverage,
    classify_shape,
    coverage_report,
    fold_crosses_slow_cut,
    fold_tempo,
    harmonic_ok,
    norm,
    scan_adjacency,
    slow_cut,
)


def rb_get(path: str, retries: int = 3) -> dict | None:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(RB + path,
                                         headers={"User-Agent": am.UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            if attempt == retries - 1:
                print(f"    ! {path[:60]} → {type(e).__name__}", file=sys.stderr)
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


def feature_cache_path(pid: str) -> Path:
    """新缓存一律写这里（用户目录）。"""
    return CACHE_DIR / f"features-{pid.replace('.', '_')}.json"


def load_feature_cache(pid: str) -> dict:
    """读特征缓存：先用户目录，再回退到旧版的仓库内 refs/。

    回退是为了不浪费已经抓好的特征——重抓一轮是几十次网络请求。
    """
    name = feature_cache_path(pid).name
    for d in ap.read_dirs():
        p = d / name
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
    return {}


def fetch_features(pid: str, tracks: list[tuple[str, str, str, str]], refresh: bool) -> dict:
    """tracks: [(catalog_id, name, artist, isrc)] → {isrc: features}

    每条特征里会带上 `_cid`（catalog id），这样下游（比如 playlist_optimize.py）
    可以直接按 catalog id 索引，不需要使用者另外手工维护一张 id→ISRC 映射表。
    """
    cache_file = feature_cache_path(pid)
    cache = {} if refresh else load_feature_cache(pid)

    todo = [t for t in tracks if t[3] and t[3] not in cache]
    print(f"特征缓存: 已有 {len(cache)} 条，待抓 {len(todo)} 条")
    for i, (cid, name, artist, isrc) in enumerate(todo, 1):
        j = rb_get(f"/v1/track?ids={isrc}")
        c = (j or {}).get("content") or []
        if not c:
            cache[isrc] = {"_miss": True, "_cid": cid, "_name": name}
            print(f"  [{i}/{len(todo)}] ✗ {name[:34]}（ReccoBeats 未收录）")
            time.sleep(0.3)
            continue
        uuid = c[0]["id"]
        f = rb_get(f"/v1/audio-features?ids={uuid}") or {}
        f = f.get("content", [f])[0] if isinstance(f.get("content"), list) else f
        f["_cid"] = cid
        f["_name"] = name
        f["_artist"] = artist
        f["_reccobeats_title"] = c[0].get("trackTitle")
        cache[isrc] = f
        print(f"  [{i}/{len(todo)}] ✓ {name[:30]:<32} {f.get('tempo',0):6.1f}BPM "
              f"{camelot(f.get('key',0), f.get('mode',0)):>4}  "
              f"E={f.get('energy',0):.2f} V={f.get('valence',0):.2f}")
        time.sleep(0.3)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return cache


# norm / ARCHETYPES / classify_shape 已移到 playlist_core.py 并在文件上方重新导出。
# 段数逻辑（5 段而非 3 段）是"好听"判断的核心，属于平台无关层，不该绑在 Apple 报告代码里。


def analyze(rows: list[dict]) -> None:
    n = len(rows)
    print(f"\n{'='*100}\n好听度体检（{n} 首有特征的曲目）\n{'='*100}")

    print(f"\n{'#':>3} {'曲目':<30} {'BPM':>6} {'≈':>6} {'调':>5} {'响度':>7} {'energy':>7} {'valence':>8} {'时长':>6}")
    for i, r in enumerate(rows, 1):
        f = r["f"]
        raw = f.get("tempo", 0)
        fd = fold_tempo(raw)
        mark = "*" if abs(fd - raw) > 0.5 else " "
        print(f"{i:>3} {str(r['name'])[:28]:<30} {raw:6.1f}{mark}{fd:6.1f} "
              f"{camelot(f.get('key',0), f.get('mode',0)):>5} {f.get('loudness',0):7.1f} "
              f"{f.get('energy',0):7.2f} {f.get('valence',0):8.2f} "
              f"{r['dur_ms']//1000//60}:{r['dur_ms']//1000%60:02d}")
    print("     （* = 原始值被折半/加倍过。BPM 估计的倍频歧义是通病，")
    print("       '≈' 列是折进 [70,160) 后的值，下面的相邻分析用它比较）")

    tempo = [fold_tempo(r["f"].get("tempo", 0)) for r in rows]
    energy = [r["f"].get("energy", 0) for r in rows]
    valence = [r["f"].get("valence", 0) for r in rows]
    loud = [r["f"].get("loudness", -60) for r in rows]
    keys = [camelot(r["f"].get("key", 0), r["f"].get("mode", 0)) for r in rows]

    # ---------- 1. 弧线：跟 PLOS 的 U 型/倒U 对比 ----------
    print(f"\n【1】整体弧线（PLOS 2025：valence/energy/loudness 应为 U 型，tempo 应为倒 U 型）")
    print("     位置分五段，段内取均值（z 化后）")

    def seg(vals):
        k = max(1, len(vals) // 5)
        segs = [vals[i:i + k] for i in range(0, len(vals), k)][:5]
        return [round(statistics.mean(s), 3) for s in segs if s]

    for label, vals, want in [("valence", valence, "U（两端高）"), ("energy", energy, "U（两端高）"),
                              ("loudness", loud, "U（两端高）"), ("tempo", tempo, "倒U（中间高）")]:
        z = norm(vals)
        s = seg(z)
        head = "█" * max(0, int(s[0] * 20))
        mid = "█" * max(0, int(s[len(s)//2] * 20))
        tail = "█" * max(0, int(s[-1] * 20))
        print(f"     {label:<9} 首{head:<21} 中{mid:<21} 末{tail:<21}  期望: {want}")

    # ---------- 2. 首尾（PLOS：首尾都该高 valence/arousal；首 tempo 低） ----------
    print(f"\n【2】首尾（PLOS：开场与收尾都高 valence/arousal；开场 tempo 偏低）")
    print(f"     首曲 {rows[0]['name'][:34]:<36} BPM={tempo[0]:6.1f} E={energy[0]:.2f} V={valence[0]:.2f}")
    print(f"     末曲 {rows[-1]['name'][:34]:<36} BPM={tempo[-1]:6.1f} E={energy[-1]:.2f} V={valence[-1]:.2f}")
    print(f"     全曲中位 BPM={statistics.median(tempo):.1f}  V={statistics.median(valence):.2f}")

    # ---------- 3. 相邻衔接检查 ----------
    # 判定全部走 playlist_core.check_pair —— 体检器与优化器**必须**用同一套规则。
    # 这里曾经自己判一遍，而且"慢歌"用的是 tempo 的 25 分位（优化器用的是固定
    # 100BPM），于是工具用一套定义诊断、用另一套定义修；另外它也从来没检查过
    # BPM 大跳（优化器却会惩罚），导致那一项"能被优化但不会被报告"。
    print(f"\n【3】相邻衔接（规则定义见 playlist_core.check_pair）")
    pair_tracks = [{"name": r["name"], "bpm": tempo[i], "raw_bpm": r["f"].get("tempo", 0),
                    "key": keys[i], "energy": energy[i]}
                   for i, r in enumerate(rows)]
    hits = scan_adjacency(pair_tracks)

    def show(rule, fmt):
        items = hits[rule]
        label = RULE_LABELS[rule]
        if not items:
            print(f"     ✅ {label}：无")
            return
        print(f"     ⚠️  {label}：{len(items)} 处（共 {n-1} 个衔接）")
        for pos, d in items:
            print("          " + fmt(pos, d))

    show("two_slow", lambda p, d: f"#{p-1}→#{p}  {d['a']['name'][:22]} "
                                  f"({d['a']['bpm']:.0f}BPM) → {d['b']['name'][:22]} "
                                  f"({d['b']['bpm']:.0f}BPM)")
    show("small_drop", lambda p, d: f"#{p-1}→#{p}  {d['a']['name'][:20]} "
                                    f"{d['a']['bpm']:.0f}→{d['b']['bpm']:.0f}BPM"
                                    f"（降 {-d['pct']:.0f}%）")
    show("both_similar", lambda p, d: f"#{p-1}→#{p}  {d['a']['name'][:20]} "
                                      f"{d['a']['bpm']:.0f}→{d['b']['bpm']:.0f}BPM "
                                      f"{d['a']['key']}→{d['b']['key']}")
    show("big_jump", lambda p, d: f"#{p-1}→#{p}  {d['a']['name'][:20]} "
                                  f"{d['a']['bpm']:.0f}→{d['b']['bpm']:.0f}BPM"
                                  f"（{d['pct']:+.0f}%）")
    show("energy_clash", lambda p, d: f"#{p-1}→#{p}  {d['a']['name'][:20]} "
                                      f"E {d['a']['energy']:.2f}→{d['b']['energy']:.2f} "
                                      f"({d['a']['key']}→{d['b']['key']})")
    withheld = [i + 1 for i, t in enumerate(pair_tracks) if fold_crosses_slow_cut(t)]
    if withheld:
        print(f"     ℹ️  折叠把 #{'、#'.join(map(str, withheld))} 推过了「慢歌」阈值——"
              f"这几首的『≈』不是它们的真实速度档，涉及它们的衔接不判 tempo 类规则"
              f"（否则报出来的是取模幽灵，不是排序缺陷）")
    print(f"     （「慢歌」阈值 = {slow_cut():.0f}BPM，与优化器同源。"
          f"若某条规则大面积命中，先想清楚是不是定义使然——"
          f"比如整张都是慢歌，two_slow 命中每一对是**真实**的，不是排序失败。）")

    # ---------- 4. 形状 ----------
    # 原来只切 3 段，把"六幕的 Cinderella（起-落-起）"误判成 Icarus。
    # 改成切 5 段，再和六种叙事弧的理想曲线比 MSE，并同时打印段均值供人工判断。
    print(f"\n【4】弧线形状（§4：六种叙事弧）")
    shape, segs, scores = classify_shape(valence)
    print(f"     valence 五段均值：" + " → ".join(f"{s:.3f}" for s in segs))
    print(f"     识别出的形状：**{shape}**")
    top = sorted(scores.items(), key=lambda x: x[1])[:3]
    print("     最接近的三种：" + "，".join(f"{k}({v:.3f})" for k, v in top))
    print(f"     ⚠️ 这是**启发式**判断：段数少或曲线平缓时会误判，请对照上面的段均值自行判断。")

    # ---------- 5. 调性分布 ----------
    print(f"\n【5】调性分布（Camelot）")
    for k, c in Counter(keys).most_common(8):
        print(f"     {k:>4}  {c:>2} 首")


def run(target: str, refresh: bool = False) -> int:
    """给一个歌单名/ID：抓特征（带缓存）并打印体检报告。返回退出码。"""
    cfg = am.load_config()
    dev = am.get_developer_token(cfg)
    user = am.require_user(cfg)
    sf = am.resolve_storefront(None, cfg, dev, user)

    p = am.find_playlist(target, dev, user)
    if not p:
        print(f"找不到歌单: {target}")
        return 4
    pid = p["id"]
    print(f"歌单：{p['attributes'].get('name')}  id={pid}")

    lib = am.playlist_tracks(pid, dev, user)
    cat_ids, dur = [], {}
    no_id = 0
    for t in lib:
        a = t.get("attributes", {})
        cid = (a.get("playParams") or {}).get("catalogId") or (a.get("playParams") or {}).get("id")
        if cid:
            cat_ids.append(str(cid))
            dur[str(cid)] = a.get("durationInMillis", 0)
        else:
            no_id += 1

    # 曾经这里写死 "/catalog/cn/songs"：非 cn 账号会静默拿回空元数据，
    # 于是整个体检降级成"有效曲目太少，无法分析"。地区必须解析出来。
    meta = catalog_meta(cat_ids, dev, sf)

    tracks = [(c,
               meta.get(c, {}).get("name") or f"id:{c}",
               meta.get(c, {}).get("artistName") or "?",
               meta.get(c, {}).get("isrc"))
              for c in cat_ids if c in meta]

    feats = fetch_features(pid, tracks, refresh)

    # 覆盖率漏斗：每一首为什么进不了分析，都要归到**具体某一层**。
    # 以前这里是一个 `if not f or f.get("_miss") or "tempo" not in f: continue`，
    # 三种完全不同的原因被压成同一个"没特征"。
    rows, counts = [], Counter()
    if no_id:
        counts["no-id"] = no_id
    for c in cat_ids:
        m = meta.get(c)
        isrc = (m or {}).get("isrc")
        f = feats.get(isrc) if isrc else None
        stage = classify_coverage(has_meta=m is not None, isrc=isrc,
                                  in_cache=bool(isrc) and isrc in feats, feat=f)
        counts[stage] += 1
        if stage != "ok":
            continue
        rows.append({"cid": c, "name": (m or {}).get("name") or f"id:{c}",
                     "artist": (m or {}).get("artistName") or "?",
                     "f": f, "dur_ms": dur.get(c, 0)})

    print()
    print(coverage_report(counts, len(lib)))
    if len(rows) < 3:
        print("\n有效曲目太少，无法分析")
        return 1
    analyze(rows)
    return 0


def flow_report(target: str, refresh: bool = False) -> str:
    """跑体检并把报告当字符串返回（供 MCP 服务 / 其他脚本调用）。"""
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            run(target, refresh)
        except am.NeedLogin:
            return "尚未登录 Apple Music：请先在终端运行 python am_playlist.py login"
        except am.ApiError as e:
            return f"API 错误 HTTP {e.status}: {e.body[:300]}"
    return buf.getvalue().strip() or "（体检没有输出）"


def main(argv: list[str] | None = None) -> int:
    """CLI 契约与其它入口保持一致：显式 --help 退出 0，什么都不给退出 2。"""
    argv = sys.argv[1:] if argv is None else list(argv)
    args = [a for a in argv if not a.startswith("-")]
    if not args:
        print(__doc__)
        return 0 if any(a in ("-h", "--help") for a in argv) else 2
    return run(args[0], "--refresh" in argv)


if __name__ == "__main__":
    sys.exit(main())
