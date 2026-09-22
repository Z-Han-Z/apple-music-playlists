#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
am_mcp_server.py — 把 am_playlist.py 包装成一个 MCP (Model Context Protocol) stdio 服务，
让 DSH / Claude / Cursor 等 MCP 客户端可以直接调用"创建 Apple Music 歌单"。

零第三方依赖：手写 JSON-RPC 2.0 over stdio（MCP 的传输格式就是按行分隔的 JSON）。

手动测试：
    echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | python am_mcp_server.py
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import am_playlist as am  # noqa: E402
import playlist_audit as audit_mod  # noqa: E402
import playlist_flow as flow_mod  # noqa: E402
import listening_stats as listening  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "apple-music-playlists", "version": am.VERSION}

TOOLS = [
    {
        "name": "am_status",
        "description": "查看 Apple Music 自动化状态：developer token 是否有效、是否已登录（music-user-token）。"
                       "任何写歌单操作前都应先确认已登录。",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "am_search_songs",
        "description": "在 Apple Music catalog 搜索歌曲/专辑/艺人，返回可用于建歌单的歌曲 ID。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "term": {"type": "string", "description": "搜索词，例如 '晴天 周杰伦' 或 'Bohemian Rhapsody'"},
                "storefront": {"type": "string", "description": "地区代码（如 us / jp / cn）。不给则用配置里记住的账号地区，再兜底 us"},
                "types": {"type": "string", "description": "songs / albums / artists，默认 songs"},
                "limit": {"type": "integer", "description": "返回条数，默认 5"},
            },
            "required": ["term"],
            "additionalProperties": False,
        },
    },
    {
        "name": "am_list_playlists",
        "description": "列出当前账号音乐库里的所有歌单（含 ID）。",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "am_show_playlist",
        "description": "查看某个歌单的曲目列表。",
        "inputSchema": {
            "type": "object",
            "properties": {"playlist": {"type": "string", "description": "歌单名或 p.xxxx 形式的 ID"}},
            "required": ["playlist"],
            "additionalProperties": False,
        },
    },
    {
        "name": "am_create_playlist",
        "description": "创建一个新的 Apple Music 歌单，并一次性写入曲目。曲目用 '歌名 - 艺人' 形式的字符串数组给出，"
                       "服务端会自动在 catalog 里匹配；若有 ISRC 码则更精确。这是全自动建歌单的主入口。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "歌单名称"},
                "description": {"type": "string", "description": "歌单描述，可选"},
                "tracks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "曲目列表，每项形如 '歌名 - 艺人'；或用 --isrcs 时填 ISRC",
                },
                "isrcs": {"type": "boolean", "description": "tracks 是否按 ISRC 精确匹配（更快、更准）"},
                "storefront": {"type": "string", "description": "地区代码。不给则用配置里记住的账号地区，再兜底 us"},
                "dry_run": {"type": "boolean", "description": "只解析曲目不写入，用于预览匹配结果"},
            },
            "required": ["name", "tracks"],
            "additionalProperties": False,
        },
    },
    {
        "name": "am_add_tracks",
        "description": "向已有歌单追加曲目。注意 Apple 的限制：只有创建该歌单的那个客户端才能写入它。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "playlist": {"type": "string", "description": "歌单名或 p.xxxx ID"},
                "tracks": {"type": "array", "items": {"type": "string"}, "description": "'歌名 - 艺人' 列表"},
                "isrcs": {"type": "boolean"},
                "storefront": {"type": "string", "description": "地区代码。不给则用配置里记住的账号地区，再兜底 us"},
                "dry_run": {"type": "boolean"},
            },
            "required": ["playlist", "tracks"],
            "additionalProperties": False,
        },
    },
    {
        "name": "am_delete_playlist",
        "description": "删除一个歌单。这是破坏性操作，必须先把歌单名和它当前的内容展示给用户并得到确认；"
                       "只删本工具创建的演示/临时歌单，不要删用户自己整理的歌单。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "playlist": {"type": "string", "description": "歌单名或 p.xxxx ID"},
                "confirm": {"type": "boolean", "description": "必须显式传 true 才会真正删除"},
            },
            "required": ["playlist", "confirm"],
            "additionalProperties": False,
        },
    },
    {
        "name": "am_audit_playlist",
        "description": "歌单结构化体检（元数据层）：曲目数、总时长、艺人集中度（同一艺人是否超过 2 首）、"
                       "流派分布、年代分布、时长分布、重复曲目、<2:00 的疑似间奏。"
                       "只读，用于判断歌单是否符合策展规范（长度 20–30 首最佳、单一主题等）。",
        "inputSchema": {
            "type": "object",
            "properties": {"playlist": {"type": "string", "description": "歌单名或 p.xxxx ID"}},
            "required": ["playlist"],
            "additionalProperties": False,
        },
    },
    {
        "name": "am_analyze_flow",
        "description": "歌单「好听度」体检（音频特征层）：抓取每首的 BPM/调性/响度/能量/情绪值"
                       "（经 ISRC→ReccoBeats，首次会慢，之后走缓存），然后检查四项相邻衔接"
                       "（两首慢歌相邻 / 「只慢一点」/ tempo 与 key 同时相似 / 能量骤变）"
                       "和整体弧线形状（Man in a hole、Icarus、Tragedy 等）。只读但会联网抓数据，可能耗时较久。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "playlist": {"type": "string", "description": "歌单名或 p.xxxx ID"},
                "refresh": {"type": "boolean", "description": "忽略特征缓存重新抓取，默认 false"},
            },
            "required": ["playlist"],
            "additionalProperties": False,
        },
    },
    {
        "name": "am_recently_played",
        "description": "查最近播放。kind=tracks 是最近播放的曲目；played 是最近播放的歌单/专辑；"
                       "stations 是最近听的电台；added 是最近加入音乐库的内容。"
                       "注意：Apple 的这个接口**不返回播放次数**。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["tracks", "played", "stations", "added"],
                         "description": "默认 tracks"},
                "limit": {"type": "integer", "description": "条数，默认 30"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "am_top_played",
        "description": "查**播放次数**排行（数据来自 Apple Music Replay / 音乐回忆的后端）。"
                       "可以查 songs / albums / artists，按年份或 all-time。"
                       "返回每项的播放次数、首次播放日期、最近播放日期。"
                       "注意：只有 amp-api 主机可用；all-time 期间不一定存在，失败时先试具体年份。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["songs", "albums", "artists"],
                         "description": "默认 songs"},
                "year": {"type": "integer", "description": "如 2026；不给则用 all-time"},
                "limit": {"type": "integer", "description": "条数，默认 30"},
            },
            "additionalProperties": False,
        },
    },
]


# ---------------------------------------------------------------- 工具实现

def t_status(_args: dict) -> str:
    cfg = am.load_config()
    out = [f"配置文件: {am.CONFIG_PATH}"]
    tok = cfg.get("developer_token")
    if tok:
        try:
            c = am.jwt_claims(tok)
            left = c["exp"] - __import__("time").time()
            out.append(f"developer token: {'有效' if left > 0 else '已过期'} "
                       f"(iss={c.get('iss')}, 剩余 {left/86400:.1f} 天)")
        except Exception:
            out.append("developer token: 解析失败")
    else:
        out.append("developer token: 未缓存（首次调用时自动抓取）")

    user = am.get_user_token(cfg)
    out.append(f"music-user-token: {'已保存' if user else '无 —— 需要先在终端运行一次 python am_playlist.py login'}")
    if tok and user:
        try:
            st, body = am.api("GET", "/me/storefront", dev=tok, user=user)
            sf = json.loads(body).get("data", [{}])[0].get("id")
            out.append(f"在线校验: OK, storefront={sf}")
        except am.ApiError as e:
            out.append(f"在线校验: 失败 → HTTP {e.status} {e.body[:150]}")
    return "\n".join(out)


def t_search(args: dict) -> str:
    cfg = am.load_config()
    dev = am.get_developer_token(cfg)
    st, body = am.api("GET", f"/catalog/{am.resolve_storefront(args.get('storefront'), cfg, dev, am.get_user_token(cfg))}/search", dev=dev,
                      query={"term": args["term"], "types": args.get("types", "songs"),
                             "limit": int(args.get("limit", 5))})
    lines = []
    for kind, payload in json.loads(body).get("results", {}).items():
        for item in payload.get("data", []):
            a = item.get("attributes", {})
            lines.append(f"{item['id']}\t{a.get('name')} — {a.get('artistName') or a.get('curatorName','')}")
    return "\n".join(lines) or "无结果"


def t_list(_args: dict) -> str:
    cfg = am.load_config()
    dev = am.get_developer_token(cfg)
    user = am.require_user(cfg)
    lines = []
    for p in am.list_playlists(dev, user):
        a = p.get("attributes", {})
        lines.append(f"{p['id']}\t{a.get('name')}\t{a.get('dateAdded','')[:10]}")
    return "\n".join(lines) or "音乐库里还没有歌单"


def t_show(args: dict) -> str:
    cfg = am.load_config()
    dev = am.get_developer_token(cfg)
    user = am.require_user(cfg)
    p = am.find_playlist(args["playlist"], dev, user)
    if not p:
        return f"找不到歌单: {args['playlist']}"
    lines = [f"{p['attributes'].get('name')} ({p['id']})"]
    for i, t in enumerate(am.playlist_tracks(p["id"], dev, user), 1):
        a = t.get("attributes", {})
        lines.append(f"{i:>3}. {a.get('name')} — {a.get('artistName')}")
    return "\n".join(lines)


def _resolve(tracks: list[str], storefront: str, isrcs: bool) -> tuple[list[str], list[str]]:
    cfg = am.load_config()
    dev = am.get_developer_token(cfg)
    return am.resolve_tracks(tracks, dev, storefront, isrcs=isrcs)


def t_create(args: dict) -> str:
    cfg = am.load_config()
    dev = am.get_developer_token(cfg)
    storefront = am.resolve_storefront(args.get("storefront"), cfg, dev, am.get_user_token(cfg))
    tracks = [str(x) for x in args["tracks"]]
    isrcs = bool(args.get("isrcs"))

    ids, missed = am.resolve_tracks(tracks, dev, storefront, isrcs=isrcs)
    head = f"匹配到 {len(ids)}/{len(tracks)} 首"
    if missed:
        head += f"；未匹配: {', '.join(missed[:8])}"
    if args.get("dry_run"):
        return head + "（dry_run，未写入）"
    if not ids:
        return head + " —— 没有可写入的曲目"

    user = am.require_user(cfg)
    payload: dict = {"attributes": {"name": args["name"]}}
    if args.get("description"):
        payload["attributes"]["description"] = args["description"]
    batch, rest = ids[:am.MAX_TRACKS_PER_REQUEST], ids[am.MAX_TRACKS_PER_REQUEST:]
    payload["relationships"] = {"tracks": {"data": [{"id": i, "type": "songs"} for i in batch]}}

    st, body = am.api("POST", "/me/library/playlists", dev=dev, user=user, body=payload)
    created, waited = am.created_playlist_from_response(body, args["name"], dev, user)
    if not created:
        suffix = (f"；首批 {len(batch)} 首很可能已写入，"
                  f"但剩余 {len(rest)} 首因无法确定歌单 ID 而未追加"
                  if rest else "；请稍后在客户端确认")
        return f"{head}\n创建请求已成功返回，但 30s 内没能回查到新歌单{suffix}"
    pid = created.get("id")
    for i in range(0, len(rest), am.MAX_TRACKS_PER_REQUEST):
        chunk = rest[i:i + am.MAX_TRACKS_PER_REQUEST]
        am.api("POST", f"/me/library/playlists/{pid}/tracks", dev=dev, user=user,
               body={"data": [{"id": x, "type": "songs"} for x in chunk]})
    synced = f"（等待 {waited:.0f}s 同步后回查到）" if waited else ""
    return (f"{head}\n✓ 已创建歌单「{created.get('attributes',{}).get('name')}」"
            f" id={pid}，写入 {len(ids)} 首。{synced}\n"
            f"（客户端/iCloud 同步可能有几十秒延迟）")


def t_add(args: dict) -> str:
    cfg = am.load_config()
    dev = am.get_developer_token(cfg)
    storefront = am.resolve_storefront(args.get("storefront"), cfg, dev, am.get_user_token(cfg))
    user = am.require_user(cfg)
    p = am.find_playlist(args["playlist"], dev, user)
    if not p:
        return f"找不到歌单: {args['playlist']}"
    tracks = [str(x) for x in args["tracks"]]
    ids, missed = am.resolve_tracks(tracks, dev, storefront, isrcs=bool(args.get("isrcs")))
    head = f"匹配到 {len(ids)}/{len(tracks)} 首"
    if missed:
        head += f"；未匹配: {', '.join(missed[:8])}"
    if args.get("dry_run"):
        return head + "（dry_run，未写入）"
    for i in range(0, len(ids), am.MAX_TRACKS_PER_REQUEST):
        chunk = ids[i:i + am.MAX_TRACKS_PER_REQUEST]
        am.api("POST", f"/me/library/playlists/{p['id']}/tracks", dev=dev, user=user,
               body={"data": [{"id": x, "type": "songs"} for x in chunk]})
    return f"{head}\n✓ 已向「{p['attributes'].get('name')}」写入 {len(ids)} 首"


def t_delete(args: dict) -> str:
    if not args.get("confirm"):
        return "拒绝执行：删除是破坏性操作，需要 confirm=true。请先向用户确认要删的是哪个歌单。"
    cfg = am.load_config()
    dev = am.get_developer_token(cfg)
    user = am.require_user(cfg)
    p = am.find_playlist(args["playlist"], dev, user)
    if not p:
        return f"找不到歌单: {args['playlist']}"
    name = p.get("attributes", {}).get("name")
    # 实测：DELETE 在 api.music.apple.com 上固定 401，amp-api 上正常
    st, _ = am.api("DELETE", f"/me/library/playlists/{p['id']}", dev=dev, user=user,
                   root=am.AMP_ROOT)
    if st in (200, 202, 204):
        return f"✓ 已删除歌单「{name}」({p['id']})"
    return f"✗ 删除失败 HTTP {st}（Apple 已知问题：官方主机 DELETE 返回 401）"


def t_audit(args: dict) -> str:
    return audit_mod.audit_report(args["playlist"])


def t_flow(args: dict) -> str:
    return flow_mod.flow_report(args["playlist"], bool(args.get("refresh")))


def t_recent(args: dict) -> str:
    return listening.recent_report(args.get("kind", "tracks"), int(args.get("limit", 30)))


def t_top(args: dict) -> str:
    year = args.get("year")
    return listening.top_report(args.get("kind", "songs"),
                                int(year) if year else None,
                                int(args.get("limit", 30)))


HANDLERS = {
    "am_status": t_status,
    "am_search_songs": t_search,
    "am_list_playlists": t_list,
    "am_show_playlist": t_show,
    "am_create_playlist": t_create,
    "am_add_tracks": t_add,
    "am_delete_playlist": t_delete,
    "am_audit_playlist": t_audit,
    "am_analyze_flow": t_flow,
    "am_recently_played": t_recent,
    "am_top_played": t_top,
}


# ---------------------------------------------------------------- JSON-RPC 循环

def send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle(req: dict):
    method = req.get("method")
    rid = req.get("id")
    params = req.get("params") or {}

    if method == "initialize":
        want = params.get("protocolVersion") or PROTOCOL_VERSION
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": want,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
        }}
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name")
        fn = HANDLERS.get(name)
        if fn is None:
            return {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32602, "message": f"unknown tool: {name}"}}
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):     # 绝不能污染协议通道
                text = fn(params.get("arguments") or {})
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": text}], "isError": False}}
        except am.NeedLogin:
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text":
                             "尚未登录 Apple Music。请让用户在终端运行一次："
                             "python am_playlist.py login（会打开浏览器登录 Apple ID）；"
                             "之后所有建歌单操作都是全自动的。"}], "isError": True}}
        except am.ApiError as e:
            hint = ""
            if e.status == 403:
                hint = "（403：music-user-token 可能已失效，需重新 login；或该歌单不是本工具创建的）"
            elif e.status == 429:
                hint = "（429：网页 token 配额共享，批量导入请改用自己的开发者密钥 am_playlist.py devtoken）"
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": f"API 错误 HTTP {e.status}: {e.body[:400]} {hint}"}],
                "isError": True}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": f"内部错误: {e}\n{traceback.format_exc()[-800:]}"}],
                "isError": True}}
    if rid is None:
        return None
    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": f"method not found: {method}"}}


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(req)
        if resp is not None:
            send(resp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
