#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
am_library.py — 读取并缓存**用户自己的音乐库**。

为什么需要这个模块
------------------
`build_pool.py` 一直依赖 `refs/library-songs.json`，但**仓库里没有任何代码
生成过这个文件**（而且 refs/ 被 gitignore 了）。也就是说那个脚本对任何新
克隆的人都是必然的 FileNotFoundError —— 它不是"没写好"，是缺了一整环。

顺带说，"库里有什么"本身就是通用能力：它是"材料要够杂、气质要统一"这条
策展原则的原料。没有它，选曲只能从外部搜索来，做不出"从你自己的收藏里选"。

缓存与网络
----------
分页拉 `/me/library/songs`（单页上限 100），再用 am_meta.catalog_meta 补
ISRC / 年代 / 流派——**库里返回的属性没有 ISRC**，而音频特征只能按 ISRC 查，
所以这一步补不上，后面的特征链就断了。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import am_paths as ap  # noqa: E402
import am_playlist as am  # noqa: E402
from am_meta import catalog_meta  # noqa: E402

PAGE = 100                      # /me/library/songs 单页上限
CACHE_NAME = "library-songs.json"
MAX_PAGES = 200                 # 保险丝：防止分页逻辑出错时无限循环

# 缓存必须有的字段。旧的 refs/library-songs.json **没有 isrc** ——那是另一套
# schema，不能拿来当本模块的缓存用：下游的音频特征只认 ISRC，缺了它整条
# 特征链就断了，而且不会报错，只会让"有特征"的比例变成 0%。
CACHE_SCHEMA_KEYS = ("cid", "name", "artist", "isrc")


def cache_path() -> Path:
    return ap.cache_dir() / CACHE_NAME


def _cache_is_usable(items) -> bool:
    return bool(items) and isinstance(items, list) and all(
        k in items[0] for k in CACHE_SCHEMA_KEYS)


def load_cached_library(*, quiet: bool = False) -> list[dict] | None:
    """读库缓存：先用户目录，再回退到旧版的仓库内 refs/。

    回退时会**校验 schema**：旧缓存没有 isrc，直接沿用会让特征链静默失效，
    所以要明确拒绝并重拉，而不是装作读到了。
    """
    for d in ap.read_dirs():
        p = d / CACHE_NAME
        if not p.exists():
            continue
        try:
            items = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if _cache_is_usable(items):
            return items
        if not quiet:
            print(f"（忽略 {p}：缺少 {'/'.join(CACHE_SCHEMA_KEYS)} 中的字段，"
                  f"是旧 schema。音频特征只能按 ISRC 查，所以重新拉一次。）",
                  file=sys.stderr)
    return None


def _page(dev: str, user: str, want: int, offset: int) -> tuple[list[dict], bool]:
    """取一页库内曲目。返回 (规整后的条目, 是否还有下一页)。"""
    _, body = am.api("GET", "/me/library/songs", dev=dev, user=user,
                     query={"limit": want, "offset": offset})
    j = json.loads(body)
    page = j.get("data", [])
    out = []
    for it in page:
        a = it.get("attributes", {})
        pp = a.get("playParams") or {}
        # catalogId 才是"这首曲子在 catalog 里的身份"。库内 id（i.xxx）
        # 不能用来建歌单、也不能用来查特征。
        cid = pp.get("catalogId") or pp.get("id")
        if not cid:
            continue
        out.append({
            "cid": str(cid),
            "name": a.get("name"),
            "artist": a.get("artistName"),
            "album": a.get("albumName"),
            "dur_ms": a.get("durationInMillis", 0),
        })
    return out, len(page) >= want


def fetch_library_songs(dev: str, user: str, sf: str, *, limit: int | None = None,
                        enrich: bool = True, quiet: bool = False) -> list[dict]:
    """分页拉整个音乐库，返回 [{cid, name, artist, album, dur_ms, isrc, year, genre}]。

    sf: 地区码，**必填**，用于补 catalog 元数据（拿 ISRC）。
    """
    items: list[dict] = []
    offset = 0
    for _ in range(MAX_PAGES):
        want = PAGE if limit is None else min(PAGE, limit - len(items))
        if want <= 0:
            break
        batch, more = _page(dev, user, want, offset)
        items.extend(batch)
        offset += want
        if not more:
            break
        if not quiet:
            print(f"  · 已取 {len(items)} 首…", file=sys.stderr)

    if enrich and items:
        if not quiet:
            print(f"  · 补 catalog 元数据（ISRC/年代/流派），共 {len(items)} 首…",
                  file=sys.stderr)
        meta = catalog_meta([it["cid"] for it in items], dev, sf)
        for it in items:
            m = meta.get(it["cid"]) or {}
            it["isrc"] = m.get("isrc")
            it["year"] = (m.get("releaseDate") or "")[:4] or None
            it["genre"] = m.get("genreNames") or []
            it["name"] = m.get("name") or it["name"]
            it["artist"] = m.get("artistName") or it["artist"]
    return items


def ensure_library_songs(dev: str, user: str, sf: str, *, refresh: bool = False,
                         limit: int | None = None, quiet: bool = False) -> list[dict]:
    """有缓存就用缓存，否则拉一次并落盘。"""
    if not refresh:
        cached = load_cached_library(quiet=quiet)
        if cached:
            if not quiet:
                print(f"读库缓存 {cache_path()}（{len(cached)} 首）—— 加 --refresh 可重抓",
                      file=sys.stderr)
            return cached

    if not quiet:
        print("拉取音乐库…", file=sys.stderr)
    items = fetch_library_songs(dev, user, sf, limit=limit, quiet=quiet)
    if limit is not None:
        # 部分拉取**不能**写缓存：否则一份残缺的库会覆盖完整缓存，
        # 之后 build_pool 会以为你的库只有这么多歌，而且它不会报错。
        if not quiet:
            print(f"（--limit {limit} 是部分拉取，按约定不写缓存）", file=sys.stderr)
        return items
    p = cache_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    if not quiet:
        print(f"已存 {len(items)} 首 → {p}", file=sys.stderr)
    return items


def library_report(items: list[dict], top: int = 15) -> str:
    """给一个可读的库概览，便于快速判断"素材够不够杂"。"""
    from collections import Counter
    if not items:
        return "音乐库是空的（或没能读到）。"
    lines = [f"音乐库：{len(items)} 首"]
    with_isrc = sum(1 for it in items if it.get("isrc"))
    lines.append(f"  有 ISRC（可用于查音频特征）：{with_isrc} 首 "
                 f"= {with_isrc / len(items) * 100:.0f}%")
    years = Counter(it.get("year") for it in items if it.get("year"))
    if years:
        span = sorted(years)
        lines.append(f"  年代跨度：{span[0]}–{span[-1]}（{len(span)} 个年份）")
    lines.append("  艺人 Top：")
    for ar, c in Counter(it.get("artist") for it in items if it.get("artist")).most_common(top):
        lines.append(f"    {c:>4} 首  {ar}")
    genres = Counter(g for it in items for g in (it.get("genre") or []))
    if genres:
        lines.append("  流派 Top：" + "，".join(f"{g}({c})" for g, c in genres.most_common(8)))
    return "\n".join(lines)
