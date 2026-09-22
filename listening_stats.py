#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
listening_stats.py — 收听历史：最近播放 + 播放次数

Apple 把「最近播放」和「播放次数」放在两套不同的接口里：

  最近播放   /v1/me/recent/played           歌单 / 专辑等
             /v1/me/recent/played/tracks    最近播放的曲目（带 catalog id）
             /v1/me/recent/radio-stations   最近听的电台
             /v1/me/library/recently-added  最近加入音乐库
            —— 这些**不含播放次数**。

  播放次数   /v1/me/music-summaries/...     ← Apple Music Replay（音乐回忆）的后端
             /me/music-summaries/search?period=year,all-time        有哪些期间可查
             /me/music-summaries/year-YYYY/view/top-songs           playCount/firstPlayed/lastPlayed
             /me/music-summaries/year-YYYY/view/top-albums
             /me/music-summaries/year-YYYY/view/top-artists
            —— 这是**唯一**能拿到播放次数的地方（官方文档里没写，是从网页播放器的
               Replay 组件 bundle 里挖出来的）。

⚠️ 两个注意点：
  · music-summaries 只在 **amp-api.music.apple.com** 上稳定可用（官方主机对部分期间返回 404）。
  · `all-time` 期间不一定存在（实测某个账号 404）；用 `periods` 子命令先看有哪些。

用法：
    python listening_stats.py recent [--limit 30]
    python listening_stats.py top --kind songs [--year 2026] [--limit 30]
    python listening_stats.py top --kind albums|artists [--year 2026]
    python listening_stats.py periods
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import am_paths as ap  # noqa: E402
import am_playlist as am  # noqa: E402

# Windows 控制台默认 GBK；唯一实现在 am_paths
ap.enable_utf8_stdout()

# music-summaries 走 web 主机更稳
ROOT = am.AMP_ROOT


def b64(s: str) -> str:
    """music-summaries 的 id 是 base64 编码的可读串，如 year-2026-song-1657318884。"""
    try:
        return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)).decode("utf-8", "replace")
    except Exception:
        return ""


def _rel(it: dict, name: str) -> dict:
    """取关系里的第一条资源（data 可能是对象也可能是数组）。"""
    r = (it.get("relationships") or {}).get(name) or {}
    d = r.get("data")
    if isinstance(d, list):
        return d[0] if d else {}
    return d or {}


def summarize(items: list[dict], kind: str, sf: str, dev: str) -> list[dict]:
    """把 song/album/artist-period-summaries 解析成 {name, artist, playCount, ...}。"""
    ids, parsed = [], []
    for it in items:
        a = it.get("attributes", {})
        res = _rel(it, kind) or _rel(it, kind.rstrip("s"))
        rid = res.get("id")
        if rid:
            ids.append(rid)
        parsed.append({
            "id": rid,
            "playCount": a.get("playCount"),
            "firstPlayed": str(a.get("firstPlayed"))[:10],
            "lastPlayed": str(a.get("lastPlayed"))[:10],
            "_fallback": b64(it.get("id", "")),
        })

    meta = {}
    for i in range(0, len(ids), 100):
        try:
            _, body = am.api("GET", f"/catalog/{sf}/{kind}", dev=dev,
                             query={"ids": ",".join(ids[i:i + 100])})
            for s in json.loads(body).get("data", []):
                meta[s["id"]] = s.get("attributes", {})
        except am.ApiError:
            pass

    for p in parsed:
        a = meta.get(p["id"], {})
        p["name"] = a.get("name") or p["_fallback"]
        p["artist"] = a.get("artistName") or a.get("albumArtistName") or ""
    return parsed


def fetch_top(kind: str, period: str, dev: str, user: str, want: int) -> list[dict]:
    """kind: songs|albums|artists ；period: year-2026 / all-time …"""
    out, offset = [], 0
    while len(out) < want:
        try:
            _, body = am.api("GET", f"/me/music-summaries/{period}/view/top-{kind}",
                             dev=dev, user=user, root=ROOT,
                             query={"limit": min(100, want - len(out)), "offset": offset})
        except am.ApiError as e:
            if offset == 0:
                raise
            break
        page = json.loads(body).get("data", [])
        if not page:
            break
        out += page
        offset += len(page)
        if len(page) < 10:
            break
    return out[:want]


def cmd_periods(args) -> int:
    cfg = am.load_config()
    dev = am.get_developer_token(cfg)
    user = am.require_user(cfg)
    _, body = am.api("GET", "/me/music-summaries/search", dev=dev, user=user, root=ROOT,
                     query={"period": "year,all-time", "omit[resource]": "autos"})
    print("=== 可查询的期间 ===")
    for s in json.loads(body).get("data", []):
        a = s.get("attributes", {})
        print(f"  {s['id']:<16} period={a.get('period'):<9} name={a.get('name')}")
    return 0


def cmd_recent(args) -> int:
    cfg = am.load_config()
    dev = am.get_developer_token(cfg)
    user = am.require_user(cfg)
    what = args.kind
    paths = {
        "tracks": ("/me/recent/played/tracks", ROOT),
        "played": ("/me/recent/played", ROOT),
        "stations": ("/me/recent/radio-stations", ROOT),
        "added": ("/me/library/recently-added", ROOT),
    }
    path, root = paths[what]
    _, body = am.api("GET", path, dev=dev, user=user, root=root,
                     query={"limit": min(100, args.limit)})
    data = json.loads(body).get("data", [])
    print(f"=== 最近{'播放的曲目' if what=='tracks' else {'played':'播放','stations':'电台','added':'加入音乐库'}[what]}"
          f"（{len(data)} 条，接口不提供播放次数）===")
    for i, t in enumerate(data, 1):
        a = t.get("attributes", {})
        nm = a.get("name") or a.get("curatorName") or t.get("id")
        extra = a.get("artistName") or a.get("curatorName") or t.get("type", "")
        print(f"  {i:>3}. {str(nm)[:44]:<46} {str(extra)[:26]}")
    return 0


def cmd_top(args) -> int:
    cfg = am.load_config()
    dev = am.get_developer_token(cfg)
    user = am.require_user(cfg)
    kind = args.kind
    period = f"year-{args.year}" if args.year else "all-time"
    sf = am.resolve_storefront(None, cfg, dev, user)
    print(f"=== {period} · 播放次数排行（{kind}）===")
    items = fetch_top(kind, period, dev, user, args.limit)
    if not items:
        print("  （没有数据。先跑 `periods` 看有哪些期间可查）")
        return 0
    rows = summarize(items, kind, sf, dev)
    # Apple 自己返回的顺序和 playCount 并非严格一致，这里按次数重排，避免展示出自相矛盾的表
    rows.sort(key=lambda r: (r.get("playCount") or 0), reverse=True)
    print(f"  {'#':>3}  {'名称':<40} {'艺人':<24} {'次数':>6}   首次 → 最近")
    for i, r in enumerate(rows, 1):
        print(f"  {i:>3}  {str(r['name'])[:38]:<40} {str(r['artist'])[:22]:<24} "
              f"{str(r['playCount']):>6}   {r['firstPlayed']} → {r['lastPlayed']}")
    return 0


def top_report(kind: str = "songs", year: int | None = None, limit: int = 30) -> str:
    """给 MCP / 其他脚本用：返回播放次数排行的文本。"""
    import contextlib
    import io
    buf = io.StringIO()
    class A:
        pass
    a = A(); a.kind = kind; a.year = year; a.limit = limit
    with contextlib.redirect_stdout(buf):
        try:
            cmd_top(a)
        except am.NeedLogin:
            return "尚未登录 Apple Music：请先运行 python am_playlist.py login"
        except am.ApiError as e:
            return (f"API 错误 HTTP {e.status}: {e.body[:200]}\n"
                    f"提示：music-summaries 只在 amp-api 上稳定可用；`all-time` 期间可能不存在，"
                    f"先用 periods 查有哪些。")
    return buf.getvalue().strip() or "（没有数据）"


def recent_report(kind: str = "tracks", limit: int = 30) -> str:
    """给 MCP / 其他脚本用：返回最近播放的文本。"""
    import contextlib
    import io
    buf = io.StringIO()
    class A:
        pass
    a = A(); a.kind = kind; a.limit = limit
    with contextlib.redirect_stdout(buf):
        try:
            cmd_recent(a)
        except am.NeedLogin:
            return "尚未登录 Apple Music：请先运行 python am_playlist.py login"
        except am.ApiError as e:
            return f"API 错误 HTTP {e.status}: {e.body[:200]}"
    return buf.getvalue().strip() or "（没有数据）"


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="收听历史：最近播放 + 播放次数")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("recent", help="最近播放")
    r.add_argument("--kind", default="tracks",
                   choices=["tracks", "played", "stations", "added"])
    r.add_argument("--limit", type=int, default=30)
    r.set_defaults(fn=cmd_recent)

    t = sub.add_parser("top", help="播放次数排行（来自 Apple Music Replay 后端）")
    t.add_argument("--kind", default="songs", choices=["songs", "albums", "artists"])
    t.add_argument("--year", type=int, default=None, help="默认 all-time")
    t.add_argument("--limit", type=int, default=30)
    t.set_defaults(fn=cmd_top)

    s = sub.add_parser("periods", help="有哪些期间可查")
    s.set_defaults(fn=cmd_periods)

    args = p.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
