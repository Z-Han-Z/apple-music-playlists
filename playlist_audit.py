#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
playlist_audit.py — 按调研到的策展原则给歌单做体检。

只检查「用 Apple Music 元数据**能**检查的」规则。BPM/调性/能量那类
（dj.studio 的能量曲线、Mixed In Key 的 Camelot）Apple 不提供字段，
本工具**不会假装能查**（这些字段 Apple 确实不提供，见 docs/how-to-build-a-good-playlist.md §9.1）。

依据：
  - Apple 官方策展规范：15–50 首、单一主题、开头放爆款
  - OneStopWatch 七步法：20–30 首最佳、同一艺人 ≤2 首、三分钟规则、维护节奏
  - Erasmus 论文（Bilibók 2024）：session 越长，每首跳过率越高
  - Esquire / High Fidelity：结尾决定记忆，不要结束在静音里

用法：
    python playlist_audit.py "歌单名或 p.xxxx"
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import am_paths as ap  # noqa: E402
import am_playlist as am  # noqa: E402
from am_meta import catalog_meta  # noqa: E402

# Windows 控制台默认 GBK；唯一实现在 am_paths
ap.enable_utf8_stdout()


def mmss(ms: int) -> str:
    s = ms // 1000
    return f"{s//60}:{s%60:02d}"


def audit(name: str) -> int:
    cfg = am.load_config()
    dev = am.get_developer_token(cfg)
    user = am.require_user(cfg)
    sf = am.resolve_storefront(None, cfg, dev, user)

    p = am.find_playlist(name, dev, user)
    if not p:
        print(f"找不到歌单: {name}")
        return 4
    pid = p["id"]
    title = p.get("attributes", {}).get("name")

    # 歌单内曲目：先拿 library-songs 的 catalog id
    st, body = am.api("GET", f"/me/library/playlists/{pid}/tracks", dev=dev, user=user,
                      query={"limit": 100})
    lib = json.loads(body).get("data", [])
    cat_ids, names = [], []
    for t in lib:
        a = t.get("attributes", {})
        names.append((a.get("name"), a.get("artistName"), a.get("durationInMillis", 0)))
        pp = a.get("playParams", {})
        cid = pp.get("catalogId") or pp.get("id")
        if cid:
            cat_ids.append(str(cid))

    meta = catalog_meta(cat_ids, dev, sf) if cat_ids else {}

    print(f"\n{'='*72}\n歌单体检：{title}\n id={pid}   曲目数={len(lib)}\n{'='*72}")

    if not meta:
        print("  ⚠️ 拿不到 catalog 元数据，只能做基础统计")

    # ---------- 1. 长度 ----------
    total_ms = sum(d for _, _, d in names)
    hrs, mins = divmod(total_ms // 1000, 3600)
    n = len(lib)
    print(f"\n【1】长度与体量")
    print(f"     曲目数 {n} 首   总时长 {hrs}h{mins//60:02d}m")
    def verdict(ok, warn, bad, cond_ok, cond_warn):
        return ok if cond_ok else (warn if cond_warn else bad)
    v = verdict("✅ 符合 Apple 官方 15–50 首", "⚠️ 超出 Apple 官方 50 首上限", "❌ 少于 15 首",
                n <= 50, n >= 15)
    print(f"     Apple 官方（15–50 首）：{v}")
    if 20 <= n <= 30:
        print(f"     OneStopWatch（20–30 首最佳）：✅ {n} 首在最佳区间")
    elif n > 30:
        print(f"     OneStopWatch（20–30 首最佳）：⚠️ {n} 首偏长；"
              f"Erasmus 论文亦指出 session 越长，每首跳过率越高")
    else:
        print(f"     OneStopWatch（20–30 首最佳）：⚠️ {n} 首偏短")

    # ---------- 2. 艺人集中度 ----------
    artists = Counter(a for _, a, _ in names if a)
    print(f"\n【2】艺人分布（OneStopWatch：同一艺人 ≤2 首）")
    over = [(a, c) for a, c in artists.most_common() if c > 2]
    for a, c in artists.most_common(8):
        flag = "  ← 超过 2 首" if c > 2 else ""
        print(f"     {c:>3} 首  {a}{flag}")
    if over:
        print(f"     ⚠️ {len(over)} 位艺人超过 2 首。**注意**：这条规则针对「发现型歌单」；")
        print(f"        如果这张是「单一作者/血脉探索型」，集中本身就是立意，不算违规。")
    else:
        print("     ✅ 没有艺人超过 2 首")

    # ---------- 3. 开场三首（三分钟规则） ----------
    print(f"\n【3】前 3 首（OneStopWatch 三分钟规则 / Apple：开头放爆款）")
    for i, (nm, ar, d) in enumerate(names[:3], 1):
        print(f"     {i}. {nm} — {ar}  ({mmss(d)})")
    print("     ⚠️ 「是不是爆款」Apple 不提供播放量字段，无法自动判定，需人工确认。")

    # ---------- 4. 流派一致性（能查的"单一主题"代理指标） ----------
    if meta:
        genres = Counter()
        for m in meta.values():
            for g in (m.get("genreNames") or []):
                genres[g] += 1
        print(f"\n【4】流派分布（「单一主题」的可查代理指标）")
        for g, c in genres.most_common(10):
            print(f"     {c:>3} 首  {g}")
        generic = {g for g, _ in genres.most_common() if g in ("音乐", "Music")}
        if generic:
            print(f"     ⚠️ 有 {genres[list(generic)[0]]} 首只标到最泛的「音乐」——"
                  f"Apple 的流派字段粒度很粗，不能作为主题判据")

    # ---------- 5. 年份跨度 ----------
    if meta:
        years = Counter((m.get("releaseDate") or "")[:4] for m in meta.values())
        span = sorted(y for y in years if y)
        print(f"\n【5】年代分布")
        for y in span:
            bar = "█" * min(40, years[y] * 2)
            print(f"     {y}  {years[y]:>3} 首  {bar}")
        if span:
            print(f"     跨度 {span[0]}–{span[-1]}")
            print("     （年代集中 → 更适合做成「一条时间线」；分散 → 更适合按主题而非年代排）")

    # ---------- 6. 时长曲线（能量曲线的粗糙代理） ----------
    durs = [d for _, _, d in names]
    print(f"\n【6】时长分布（**注意：这只是能量曲线的粗糙代理，不是真的能量曲线**）")
    print(f"     最短 {mmss(min(durs))}   最长 {mmss(max(durs))}   "
          f"平均 {mmss(sum(durs)//len(durs))}")
    short = sum(1 for d in durs if d < 180000)
    print(f"     短于 3 分钟：{short} 首   长于 5 分钟：{sum(1 for d in durs if d > 300000)} 首")
    print("     ⚠️ Apple Music API **不提供** BPM / 调性 / 能量 / 情绪字段（实测），")
    print("        所以 dj.studio 的能量曲线与 Mixed In Key 的 Camelot 无法自动校验。")

    # ---------- 7. 结尾 ----------
    print(f"\n【7】结尾（Esquire：结尾决定记忆，不要结束在静音里）")
    nm, ar, d = names[-1]
    print(f"     最后一首：{nm} — {ar}  ({mmss(d)})")
    print("     ⚠️ 「是否以爆点/淡出结束」需人工判断。")

    # ---------- 8. 机械检查：重复 / 间奏 ----------
    dupes = [k for k, c in Counter(nm for nm, _, _ in names).items() if c > 1]
    print(f"\n【8】机械项")
    print(f"     重复曲目：{('⚠️ ' + ', '.join(dupes)) if dupes else '✅ 无'}")
    inter = [(nm, d) for nm, _, d in names if d < 120000]
    print(f"     疑似间奏(<2:00)：{('⚠️ ' + ', '.join(f'{x}({mmss(y)})' for x, y in inter)) if inter else '✅ 无'}")

    print(f"\n{'='*72}")
    print("体检完毕。标 ⚠️/❌ 的项见 docs/playlist-curation-survey.md §10 的可执行清单。")
    print(f"{'='*72}\n")
    return 0


def audit_report(name: str) -> str:
    """跑结构化体检并把报告当字符串返回（供 MCP 服务 / 其他脚本调用）。

    注意：这是**元数据层**的体检（曲目数/艺人集中度/流派/年代/时长/重复/间奏）。
    音频特征层（BPM/调性/响度/能量/情绪）在 playlist_flow.py 的 flow_report()。
    """
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            audit(name)
        except am.NeedLogin:
            return "尚未登录 Apple Music：请先在终端运行 python am_playlist.py login"
        except am.ApiError as e:
            return f"API 错误 HTTP {e.status}: {e.body[:300]}"
    return buf.getvalue().strip() or "（体检没有输出）"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if argv else 2
    return audit(argv[0])


if __name__ == "__main__":
    sys.exit(main())
