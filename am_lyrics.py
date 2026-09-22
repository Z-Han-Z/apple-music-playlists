#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
am_lyrics.py — 第二个歌词源（LRCLIB），补 Apple 缺的那部分。

为什么需要第二个源：实测 Apple 的歌词覆盖只有 **65%**（1029/1581）。缺口有两块：
  · 186 首根本没有 ISRC → catalog 拿不到任何属性（这个源也救不了）
  · **217 首有元数据但 Apple 没歌词** ← 这才是这个模块的目标
LRCLIB 免费、无需 key。手动实测：模糊搜索在本库命中 **8/12**。

⚠️ 两条契约细节是**实测**出来的，不是从文档抄的：
  1. `/api/search` 是模糊匹配，命中率明显高于 `/api/get`。
  2. `/api/get` 要求 artist/track/album/**duration 全部精确**——差一秒就 404
     （实测 0/8）。所以默认走 search，`get` 只在有 duration 时做补充尝试。

⚠️ 歌词正文是授权内容。本模块的 `lookup()` **只返回结构**（有没有歌词、是不是器乐），
   不返回正文；要正文得显式调 `fetch_text()`。无论哪条路，**都不要把正文写进仓库**；
   缓存写在用户目录（已 gitignore）。
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import am_paths as ap  # noqa: E402

BASE = "https://lrclib.net"
USER_AGENT = ("am-playlist/%s (+https://github.com/Z-Han-Z/apple-music-playlists)"
              % ap.VERSION)
TIMEOUT = 15
CACHE_NAME = "lyrics-signals.json"


def _opener(proxy: str | None = None):
    """默认走 urllib 的环境代理（HTTPS_PROXY 等）；显式给 proxy 时覆盖。"""
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    return urllib.request.build_opener(*handlers)


def _get_json(url: str, opener, timeout: int):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with opener.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def signals(record: dict) -> dict:
    """从一个 LRCLIB 记录里只提取**结构**——不碰歌词正文。"""
    return {
        "instrumental": bool(record.get("instrumental")),
        "has_plain": bool((record.get("plainLyrics") or "").strip()),
        "has_synced": bool((record.get("syncedLyrics") or "").strip()),
    }


def _cache_path() -> Path:
    return ap.cache_dir() / CACHE_NAME


def _load_cache() -> dict:
    for d in ap.read_dirs():
        p = d / CACHE_NAME
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
    return {}


def _save_cache(cache: dict) -> None:
    p = _cache_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


def _key(track_name: str, artist_name: str) -> str:
    return f"{(track_name or '').strip().lower()}|{(artist_name or '').strip().lower()}"


def lookup(track_name: str, artist_name: str, *, duration_ms: int | None = None,
           album_name: str | None = None, opener=None, timeout: int = TIMEOUT,
           use_cache: bool = True) -> dict:
    """查一首曲目在 LRCLIB 的情况，返回**结构**（绝不含歌词正文）：

        {"found": bool, "instrumental": bool, "has_plain": bool,
         "has_synced": bool, "match": "search"|"get"|"cache"|"none"}

    查不到时 `found=False` —— 这是**弱证据**：LRCLIB 没收录，不等于这首是器乐。
    """
    key = _key(track_name, artist_name)
    cache = _load_cache() if use_cache else {}
    if use_cache and key in cache:
        return {**cache[key], "match": "cache"}

    op = opener or _opener()
    result = {"found": False, "instrumental": False, "has_plain": False,
              "has_synced": False, "match": "none"}

    # 1) 模糊搜索优先——实测命中率明显高于 get
    try:
        q = urllib.parse.urlencode({"track_name": track_name, "artist_name": artist_name})
        hits = _get_json(f"{BASE}/api/search?{q}", op, timeout)
        if isinstance(hits, list) and hits:
            best = hits[0]
            # 有 duration 时优先挑时长最接近的那条，避免同名的现场版/翻唱
            if duration_ms:
                want = duration_ms / 1000
                best = min(hits, key=lambda h: abs((h.get("duration") or 0) - want))
            result = {**signals(best), "found": True, "match": "search"}
    except urllib.error.HTTPError as e:
        if e.code != 404:
            result["match"] = f"http-{e.code}"
    except Exception:
        result["match"] = "unreachable"

    # 2) 还没命中且有 duration，才试精确接口
    if not result["found"] and duration_ms:
        try:
            q = urllib.parse.urlencode({
                "track_name": track_name, "artist_name": artist_name,
                "album_name": album_name or "", "duration": int(duration_ms / 1000)})
            rec = _get_json(f"{BASE}/api/get?{q}", op, timeout)
            if isinstance(rec, dict):
                result = {**signals(rec), "found": True, "match": "get"}
        except Exception:
            pass

    if use_cache and result.get("found"):
        cache[key] = {k: v for k, v in result.items() if k != "match"}
        try:
            _save_cache(cache)
        except Exception:
            pass
    return result


def fetch_text(track_name: str, artist_name: str, *, prefer_synced: bool = True,
               opener=None, timeout: int = TIMEOUT) -> str | None:
    """取歌词**正文**（拿不到返回 None）。调用方负责不要把它落到仓库里。

    同步歌词（LRC）带时间轴，和 Apple 的 TTML 一样可以按行定位。
    """
    op = opener or _opener()
    try:
        q = urllib.parse.urlencode({"track_name": track_name, "artist_name": artist_name})
        hits = _get_json(f"{BASE}/api/search?{q}", op, timeout)
    except Exception:
        return None
    if not isinstance(hits, list) or not hits:
        return None
    best = hits[0]
    if prefer_synced:
        return best.get("syncedLyrics") or best.get("plainLyrics")
    return best.get("plainLyrics") or best.get("syncedLyrics")
