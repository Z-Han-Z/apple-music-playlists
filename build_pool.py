#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_pool.py — 把近期收听与多个 Replay 时期合并成供 LLM 阅读的证据池。

这个脚本只做事实层工作：拉取、归一化、去重和补齐 catalog 元数据。它不按艺人
扩展曲目、不为了“多样性”抽样，也不判断哪些歌符合用户描述。最终选曲应由 LLM
结合用户原话和这里保留的收听证据完成，再交给 am_resolve_candidates 落地校验。

例子（“最近爱听和以前爱听”）：
    python build_pool.py --tag recent-and-old --years 2026 2023 2021
    python build_pool.py --tag compact --years 2026 2024 --recent-limit 20 --top-per-year 30

输出：用户缓存目录中的 history-evidence-<tag>.json。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import am_paths as ap  # noqa: E402
import am_playlist as am  # noqa: E402
import listening_stats as stats  # noqa: E402
from am_meta import catalog_meta  # noqa: E402

ap.enable_utf8_stdout()


def _catalog_id(item: dict) -> str | None:
    """Extract a catalog song id from a recent-play resource."""
    attrs = item.get("attributes") or {}
    play = attrs.get("playParams") or {}
    cid = play.get("catalogId") or play.get("id") or item.get("id")
    return str(cid) if cid else None


def _date_bounds(values: list[str | None]) -> tuple[str | None, str | None]:
    clean = sorted(v for v in values if v)
    return (clean[0], clean[-1]) if clean else (None, None)


def merge_history_evidence(
        recent_items: list[dict],
        period_rows: dict[str, list[dict]]) -> list[dict]:
    """Merge listening facts by catalog id, preserving source-specific evidence.

    Output order is stable: recent-play order first, followed by each Replay period's
    returned order. The order is only provenance; it is not a recommendation score.
    """
    merged: dict[str, dict] = {}

    def row_for(cid: str) -> dict:
        if cid not in merged:
            merged[cid] = {
                "cid": cid,
                "name": None,
                "artist": None,
                "album": None,
                "isrc": None,
                "release_year": None,
                "genre": [],
                "evidence": {
                    "recent_rank": None,
                    "periods": {},
                    "first_played": None,
                    "last_played": None,
                },
            }
        return merged[cid]

    for rank, item in enumerate(recent_items, 1):
        cid = _catalog_id(item)
        if not cid:
            continue
        row = row_for(cid)
        attrs = item.get("attributes") or {}
        row["name"] = row["name"] or attrs.get("name")
        row["artist"] = row["artist"] or attrs.get("artistName")
        current = row["evidence"]["recent_rank"]
        row["evidence"]["recent_rank"] = rank if current is None else min(current, rank)

    for period, rows in period_rows.items():
        for rank, source in enumerate(rows, 1):
            cid = source.get("id") or source.get("cid")
            if not cid:
                continue
            cid = str(cid)
            row = row_for(cid)
            row["name"] = row["name"] or source.get("name")
            row["artist"] = row["artist"] or source.get("artist")
            row["evidence"]["periods"][period] = {
                "rank": rank,
                "play_count": source.get("playCount", source.get("plays")),
                "first_played": source.get("firstPlayed", source.get("first")) or None,
                "last_played": source.get("lastPlayed", source.get("last")) or None,
            }

    for row in merged.values():
        periods = row["evidence"]["periods"].values()
        first, _ = _date_bounds([p.get("first_played") for p in periods])
        _, last = _date_bounds([p.get("last_played") for p in periods])
        row["evidence"]["first_played"] = first
        row["evidence"]["last_played"] = last
    return list(merged.values())


def _enrich(rows: list[dict], dev: str, storefront: str) -> None:
    meta = catalog_meta([r["cid"] for r in rows], dev, storefront)
    for row in rows:
        attrs = meta.get(row["cid"]) or {}
        row["name"] = attrs.get("name") or row["name"]
        row["artist"] = attrs.get("artistName") or row["artist"]
        row["album"] = attrs.get("albumName")
        row["isrc"] = attrs.get("isrc")
        row["release_year"] = (attrs.get("releaseDate") or "")[:4] or None
        row["genre"] = attrs.get("genreNames") or []


def build(tag: str, years: list[int], recent_limit: int, top_per_year: int) -> int:
    cfg = am.load_config()
    dev = am.get_developer_token(cfg)
    user = am.require_user(cfg)
    storefront = am.resolve_storefront(None, cfg, dev, user)

    print(f"取最近播放 {recent_limit} 首…")
    recent = stats.fetch_recent("tracks", dev, user, recent_limit)

    period_rows: dict[str, list[dict]] = {}
    for year in dict.fromkeys(years):
        period = f"year-{year}"
        print(f"取 {period} Replay Top {top_per_year}…")
        try:
            items = stats.fetch_top("songs", period, dev, user, top_per_year)
        except am.ApiError as exc:
            print(f"  ! {period} 不可用（HTTP {exc.status}），跳过", file=sys.stderr)
            continue
        # Metadata is enriched once for the merged set below; do not repeat one catalog
        # request per Replay year.
        rows = stats.parse_summaries(items, "songs")
        rows.sort(key=lambda r: (r.get("playCount") or 0), reverse=True)
        period_rows[period] = rows

    evidence = merge_history_evidence(recent, period_rows)
    _enrich(evidence, dev, storefront)
    dest = ap.cache_dir() / f"history-evidence-{tag}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "apple-music-listening-evidence/v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "sources": {"recent_limit": recent_limit, "periods": list(period_rows)},
        "tracks": evidence,
    }
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"收听证据池: {len(evidence)} 首 → {dest}")
    print("下一步：由 LLM 对照用户描述比较这些证据，再用 am_resolve_candidates 校验候选。")
    return 0


def main(argv: list[str] | None = None) -> int:
    current = time.localtime().tm_year
    parser = argparse.ArgumentParser(
        description="合并近期收听与多个 Replay 时期，生成供 LLM 阅读的事实证据池")
    parser.add_argument("--tag", default="history", help="输出标签（默认 history）")
    parser.add_argument("--years", nargs="+", type=int, default=[current, current - 1],
                        help="要纳入的 Replay 年份，可给多个（默认今年和去年）")
    parser.add_argument("--recent-limit", type=int, default=30,
                        help="最近播放取多少首（默认 30，最多 100）")
    parser.add_argument("--top-per-year", type=int, default=50,
                        help="每个 Replay 年份取多少首（默认 50）")
    args = parser.parse_args(argv)
    if not 1 <= args.recent_limit <= 100:
        parser.error("--recent-limit 必须在 1 到 100 之间")
    if args.top_per_year < 1:
        parser.error("--top-per-year 必须大于 0")
    try:
        return build(args.tag, args.years, args.recent_limit, args.top_per_year)
    except am.NeedLogin:
        print("尚未登录：请先运行 python am_playlist.py login")
        return 2


if __name__ == "__main__":
    sys.exit(main())
