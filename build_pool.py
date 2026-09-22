#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_pool.py — 从你自己的音乐库里挑出一批候选曲目，并抓好音频特征。

候选池的优先级（全部限定在**你自己的音乐库**内）：
  ① 你实际听得最多的（Replay 播放次数）
  ② 你最爱艺人名下的其他库内曲目 —— 横向铺开
  ③ 不同艺人 / 年代的代表曲 —— 保证"材料够杂"

依赖：
  · 音乐库缓存 —— 本脚本自己会拉（am_library.py）。这一环以前是**缺的**：
    旧版读一个仓库内、被 gitignore 的 JSON，而仓库里没有任何代码生成过它，
    所以对新克隆的人来说必然 FileNotFoundError。
  · 播放画像（可选）—— 想用 ① 就得先跑 `python profile_library.py`。
    没有画像也能跑，只是会跳过 ①。

用法：
    python build_pool.py --tag early-morning --cap 130
    python build_pool.py --tag x --cap 60 --year 2025 --top-artists 12
    python build_pool.py --tag x --refresh-library      # 重拉音乐库
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import am_library as lib  # noqa: E402
import am_paths as ap  # noqa: E402
import am_playlist as am  # noqa: E402
import playlist_flow as pf  # noqa: E402
import profile_library as prof_mod  # noqa: E402
from am_meta import catalog_meta  # noqa: E402
from playlist_core import classify_coverage, coverage_report  # noqa: E402

# Windows 控制台默认 GBK；唯一实现在 am_paths
ap.enable_utf8_stdout()


def build(tag: str, cap: int, year: int, top_n: int,
          refresh_library: bool = False, quiet: bool = False) -> int:
    cfg = am.load_config()
    dev = am.get_developer_token(cfg)
    user = am.require_user(cfg)
    sf = am.resolve_storefront(None, cfg, dev, user)

    songs = [s for s in lib.ensure_library_songs(dev, user, sf, refresh=refresh_library,
                                                 quiet=quiet) if s.get("cid")]
    print(f"库内可用曲目: {len(songs)}")

    profile = prof_mod.load_profile(year)
    if not profile:
        print(f"（没有 {year} 年的播放画像，跳过「最常听」那一档；"
              f"想启用就先跑 python profile_library.py --year {year}）")
        profile = []

    plays: Counter = Counter()
    for p in profile:
        if p.get("artist"):
            plays[p["artist"]] += p.get("plays") or 0
    top_artists = [a for a, _ in plays.most_common(top_n)]
    if top_artists:
        print("最爱艺人 Top:", ", ".join(f"{a}({c})" for a, c in plays.most_common(10)))

    picked: list[dict] = []
    seen: set[str] = set()

    # ① 实际听得最多的
    for p in sorted(profile, key=lambda x: -(x.get("plays") or 0)):
        cid = p.get("cid")
        if cid and cid not in seen:
            picked.append({"cid": cid, "name": p.get("name"), "artist": p.get("artist"),
                           "plays": p.get("plays"), "isrc": p.get("isrc"),
                           "year": p.get("year"), "genre": p.get("genre"),
                           "why": "top-played"})
            seen.add(cid)

    # ② 最爱艺人名下的其他库内曲：横向铺开，但每个艺人不许抢太多名额
    by_artist: dict[str, list[dict]] = defaultdict(list)
    for s in songs:
        if s["artist"] in top_artists and s["cid"] not in seen:
            by_artist[s["artist"]].append(s)
    per = max(3, max(0, cap - len(picked)) // max(1, len(top_artists)) // 2) if top_artists else 0
    for a in top_artists:
        for s in by_artist[a][:per]:
            if s["cid"] in seen or len(picked) >= cap:
                break
            picked.append({"cid": s["cid"], "name": s["name"], "artist": s["artist"],
                           "plays": 0, "isrc": s.get("isrc"), "year": s.get("year"),
                           "genre": s.get("genre"), "why": f"artist:{a}"})
            seen.add(s["cid"])

    # ③ 其他簇：按艺人/年代排序后等距抽样，保证"材料够杂"
    others = [s for s in songs if s["cid"] not in seen and s["artist"] not in top_artists]
    others.sort(key=lambda s: (s.get("artist") or "", str(s.get("year") or "")))
    room = max(0, cap - len(picked))
    if room and others:
        step = max(1, len(others) // room)
        for s in others[::step][:room]:
            if s["cid"] in seen:
                continue
            picked.append({"cid": s["cid"], "name": s["name"], "artist": s["artist"],
                           "plays": 0, "isrc": s.get("isrc"), "year": s.get("year"),
                           "genre": s.get("genre"), "why": "filler"})
            seen.add(s["cid"])

    picked = picked[:cap]
    print(f"候选池: {len(picked)} 首")
    print("  来源分布:", dict(Counter(p["why"].split(":")[0] for p in picked)))

    # 库内条目一般已经带 ISRC；没有的（刚入库还没同步）补一次 catalog 查询。
    # 没有 ISRC 就查不到音频特征，后面的排序就无从谈起。
    missing = [p["cid"] for p in picked if not p.get("isrc")]
    if missing:
        print(f"  补 {len(missing)} 首缺 ISRC 的元数据…")
        meta = catalog_meta(missing, dev, sf)
        for p in picked:
            m = meta.get(p["cid"])
            if m:
                p["isrc"] = p.get("isrc") or m.get("isrc")
                p["year"] = p.get("year") or (m.get("releaseDate") or "")[:4] or None
                p["genre"] = p.get("genre") or m.get("genreNames") or []

    tracks = [(p["cid"], p.get("name") or p["cid"], p.get("artist") or "", p["isrc"])
              for p in picked if p.get("isrc")]
    print(f"抓音频特征（{len(tracks)} 首，有缓存则跳过）…")
    feats = pf.fetch_features(f"pool-{tag}", tracks, refresh=False)

    # 覆盖率按**具体原因**分解，而不是只说"N 首没特征"。
    # "没有 ISRC"和"特征源没收录"是相反的两件事：前者换源无用，后者换源能解决。
    counts = Counter()
    out = []
    for p in picked:
        isrc = p.get("isrc")
        f = feats.get(isrc) if isrc else None
        stage = classify_coverage(isrc=isrc, in_cache=bool(isrc) and isrc in feats, feat=f)
        counts[stage] += 1
        if stage == "ok":
            p["f"] = f
            out.append(p)

    dest = ap.cache_dir() / f"pool-{tag}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n候选池落盘: {len(out)}/{len(picked)} 首有特征 → {dest}")
    print(coverage_report(counts, len(picked)))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="从自己的音乐库挑候选池并抓音频特征",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tag", default="pool", help="候选池名字，决定输出文件名（默认 pool）")
    p.add_argument("--cap", type=int, default=130, help="候选池最多多少首（默认 130）")
    p.add_argument("--year", type=int, default=time.localtime().tm_year,
                   help="用哪一年的播放画像（默认今年）")
    p.add_argument("--top-artists", type=int, default=18,
                   help="取播放次数前几名艺人作为「横向铺开」的起点（默认 18）")
    p.add_argument("--refresh-library", action="store_true", help="忽略库缓存，重拉音乐库")
    p.add_argument("--quiet", action="store_true")
    a = p.parse_args(argv)
    try:
        return build(a.tag, a.cap, a.year, a.top_artists,
                     refresh_library=a.refresh_library, quiet=a.quiet)
    except am.NeedLogin:
        print("尚未登录：请先运行 python am_playlist.py login")
        return 2


if __name__ == "__main__":
    sys.exit(main())
