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
import playlist_optimize as opt_mod  # noqa: E402
from am_meta import catalog_meta  # noqa: E402
from playlist_core import SHAPE_ALIASES  # noqa: E402

PROTOCOL_VERSION = "2025-11-25"
SUPPORTED_PROTOCOL_VERSIONS = {
    "2024-11-05",
    "2025-03-26",
    "2025-06-18",
    "2025-11-25",
}
SERVER_INFO = {"name": "apple-music-playlists", "version": am.VERSION}
SERVER_INSTRUCTIONS = (
    "Turn natural-language playlist descriptions into Apple Music playlists: interpret the "
    "brief, call am_status, propose a generous candidate pool, ground it with "
    "am_resolve_candidates, and let the host LLM compare candidates directly against the user's "
    "words. Do not invent scalar theme scores. Then call am_create_playlist with dry_run=true "
    "before the final write. The host client's LLM does the curation; this server validates tracks "
    "against Apple Music and performs account operations. "
    "am_delete_playlist is destructive and requires confirm=true. Only playlists created by this "
    "API client can be modified. / 根据用户的自然语言描述策划 Apple Music 歌单：先理解需求并调用 "
    "am_status，由客户端模型提出充足的候选曲目，用 am_resolve_candidates 批量校验后直接比较"
    "候选与用户文字的契合度，不要虚构主题分数；再以 dry_run=true 调用 "
    "am_create_playlist 预演后正式创建。删除必须 confirm=true；只有本 API 客户端创建的歌单可修改。"
)

PLAYLIST_PROMPT_NAME = "create_playlist_from_description"
PROMPTS = [
    {
        "name": PLAYLIST_PROMPT_NAME,
        "title": "Create a playlist from a description / 根据描述创建歌单",
        "description": (
            "Curate, validate, preview, and create an Apple Music playlist from a natural-language "
            "brief. The MCP host's model chooses and compares candidates; Apple Music catalog "
            "grounding verifies them. / "
            "根据自然语言需求策划、校验、预演并创建 Apple Music 歌单。"
        ),
        "arguments": [
            {
                "name": "description",
                "description": (
                    "The playlist brief: mood, scene, genres, artists, era, language, exclusions, "
                    "and any sequencing preferences. / 歌单需求描述。"
                ),
                "required": True,
            },
            {
                "name": "name",
                "description": "Optional playlist name; otherwise propose one. / 可选歌单名称。",
                "required": False,
            },
            {
                "name": "track_count",
                "description": "Desired track count as text; defaults to 25. / 期望曲目数，默认 25。",
                "required": False,
            },
            {
                "name": "language",
                "description": "Language for the plan and final report. / 计划与结果所用语言。",
                "required": False,
            },
        ],
    }
]

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
                "term": {"type": "string", "minLength": 1, "description": "搜索词，例如 '晴天 周杰伦' 或 'Bohemian Rhapsody'"},
                "storefront": {"type": "string", "description": "地区代码（如 us / jp / cn）。不给则用配置里记住的账号地区，再兜底 us"},
                "types": {"type": "string", "enum": ["songs", "albums", "artists"],
                          "description": "songs / albums / artists，默认 songs"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "description": "返回条数，默认 5"},
            },
            "required": ["term"],
            "additionalProperties": False,
        },
    },
    {
        "name": "am_resolve_candidates",
        "description": "批量校验 LLM 提出的候选曲目，并返回 Apple Music 的真实曲名、艺人、专辑、"
                       "发行日期、流派、时长、歌词可用性、版本标记和 catalog ID。还会指出重复录音与"
                       "艺人集中度，但**不替模型做主题评分或选曲**。模型应直接根据用户描述与这些"
                       "真实信息比较候选，保留理由充分的曲目。只读，不修改音乐库。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tracks": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "minItems": 1,
                    "maxItems": 60,
                    "description": "候选曲目，每项形如 '歌名 - 艺人'。建议先给目标数量的 1.5–2 倍。",
                },
                "storefront": {"type": "string", "description": "可选地区代码；默认使用账号地区"},
            },
            "required": ["tracks"],
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
            "properties": {"playlist": {"type": "string", "minLength": 1, "description": "歌单名或 p.xxxx 形式的 ID"}},
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
                "name": {"type": "string", "minLength": 1, "description": "歌单名称"},
                "description": {"type": "string", "description": "歌单描述，可选"},
                "tracks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
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
                "playlist": {"type": "string", "minLength": 1, "description": "歌单名或 p.xxxx ID"},
                "tracks": {"type": "array", "items": {"type": "string"}, "minItems": 1, "description": "'歌名 - 艺人' 列表"},
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
                "playlist": {"type": "string", "minLength": 1, "description": "歌单名或 p.xxxx ID"},
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
            "properties": {"playlist": {"type": "string", "minLength": 1, "description": "歌单名或 p.xxxx ID"}},
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
                "playlist": {"type": "string", "minLength": 1, "description": "歌单名或 p.xxxx ID"},
                "refresh": {"type": "boolean", "description": "忽略特征缓存重新抓取，默认 false"},
            },
            "required": ["playlist"],
            "additionalProperties": False,
        },
    },
    {
        "name": "am_optimize_order",
        "description": "为一批曲目**算出更好的顺序**。这是本项目唯一会排序的工具——"
                       "am_analyze_flow 只诊断（告诉你哪里有 2 处慢歌相邻、形状是 Icarus），"
                       "不提供修法。这里用模拟退火在四条相邻硬规则（不要两首慢歌相邻 / "
                       "不要「只慢一点」/ 相邻不该在 tempo 与 key 上同时相似 / 不要 BPM 无理由大跳、"
                       "能量骤变）与选定叙事弧之间取平衡。**只读**：只返回建议顺序，不动任何歌单；"
                       "把返回列表按原顺序交给 am_create_playlist 即可。因为需要每首的 BPM/调性，"
                       "首次会联网抓特征（之后走缓存）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tracks": {"type": "array", "items": {"type": "string"}, "minItems": 2,
                           "description": "要排序的曲目，每项 '歌名 - 艺人'（配 isrcs=true 时填 ISRC）"},
                "blocks": {"type": "array", "items": {"type": "array", "items": {"type": "string"}},
                           "description": "分组排序：每个子数组是一个乐章/段落，"
                                          "**段落之间的先后顺序保持不动**，只在段落内部重排。"
                                          "想保留叙事结构时用它（与 tracks 二选一）"},
                "playlist": {"type": "string", "minLength": 1,
                             "description": "要重排的现有歌单名或 p.xxxx ID（与 tracks/blocks 二选一）"},
                "arc": {"type": "string", "enum": list(SHAPE_ALIASES),
                        "description": "目标叙事弧，默认 man-in-a-hole（先落再起）。"
                                       "用 cinderella 表示起-落-起，等等"},
                "isrcs": {"type": "boolean", "description": "tracks/blocks 是否按 ISRC 精确匹配，默认 false"},
                "refresh": {"type": "boolean", "description": "忽略音频特征缓存重抓，默认 false"},
            },
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
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "description": "条数，默认 30"},
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
                "year": {"type": "integer", "minimum": 2015, "maximum": 2100, "description": "如 2026；不给则用 all-time"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "description": "条数，默认 30"},
            },
            "additionalProperties": False,
        },
    },
]

# Keep the wire catalogue useful to English and Chinese agents without making clients
# infer behaviour from translated prose. Tool annotations are hints, not an authorization
# mechanism; the server still enforces confirm=true for deletion.
_ENGLISH_TOOL_DESCRIPTIONS = {
    "am_status": "Check developer-token validity and Apple Music login status. Use before any library write; this check changes nothing.",
    "am_search_songs": "Search the Apple Music catalog for a small exploratory lookup and return stable catalog IDs. For an LLM-proposed playlist-sized pool, use am_resolve_candidates instead.",
    "am_resolve_candidates": "Ground an LLM-curated candidate pool in Apple Music metadata before final selection or creation. It flags unresolved tracks, duplicate recordings, artist concentration, and version markers; it never scores theme fit or writes to the library.",
    "am_list_playlists": "List every playlist in the current user's library, including IDs. Use am_show_playlist when the tracks of one playlist are needed.",
    "am_show_playlist": "Show the tracks in one playlist selected by name or ID. Use am_list_playlists first when the exact playlist is unknown.",
    "am_create_playlist": "Create a new playlist from 'Title - Artist' strings or ISRCs. Use dry_run=true to verify catalog matching without writing; use am_add_tracks for an existing playlist.",
    "am_add_tracks": "Append resolved tracks to an existing playlist created by this API client. Use dry_run=true to preview matching; use am_create_playlist for a new playlist.",
    "am_delete_playlist": "Delete one playlist permanently after it has been shown to the user. This is destructive, requires confirm=true, and does not delete the underlying songs from the library.",
    "am_audit_playlist": "Read-only metadata audit of playlist length, artist concentration, genres, eras, duplicates, and possible interludes. For BPM, key, energy, and transitions, use am_analyze_flow.",
    "am_analyze_flow": "Read-only diagnosis of BPM, key, loudness, energy, mood, adjacent transitions, and overall arc. It may fetch and cache remote feature data; use am_optimize_order only when a proposed replacement order is wanted.",
    "am_optimize_order": "Compute a proposed order after the LLM has selected the songs and narrative blocks. It balances adjacent audio transitions with a chosen qualitative arc, returns an order without writing, and may fetch cached remote features; it must not choose songs or judge theme fit.",
    "am_recently_played": "Read recent listening or recently added Apple Music content when recency matters. This API does not provide play counts; use am_top_played for Replay rankings.",
    "am_top_played": "Read Apple Music Replay play-count rankings by song, album, or artist when frequency matters. Use am_recently_played for latest listening; all-time data may be unavailable, so retry with a specific year.",
}
_TOOL_TITLES = {
    "am_status": "Check Apple Music Status",
    "am_search_songs": "Search Apple Music Catalog",
    "am_resolve_candidates": "Resolve Playlist Candidates",
    "am_list_playlists": "List Library Playlists",
    "am_show_playlist": "Show Playlist Tracks",
    "am_create_playlist": "Create Playlist",
    "am_add_tracks": "Add Tracks to Playlist",
    "am_delete_playlist": "Delete Playlist",
    "am_audit_playlist": "Audit Playlist Metadata",
    "am_analyze_flow": "Analyze Playlist Flow",
    "am_optimize_order": "Optimize Track Order",
    "am_recently_played": "Get Recent Listening",
    "am_top_played": "Get Replay Rankings",
}
_READ_ONLY_TOOLS = {
    "am_status", "am_search_songs", "am_resolve_candidates", "am_list_playlists", "am_show_playlist",
    "am_audit_playlist", "am_analyze_flow", "am_optimize_order",
    "am_recently_played", "am_top_played",
}
for _tool in TOOLS:
    _name = _tool["name"]
    _tool["title"] = _TOOL_TITLES[_name]
    _tool["description"] = f"{_ENGLISH_TOOL_DESCRIPTIONS[_name]} / 中文：{_tool['description']}"
    _tool["annotations"] = {
        "readOnlyHint": _name in _READ_ONLY_TOOLS,
        "destructiveHint": _name == "am_delete_playlist",
        "idempotentHint": _name in _READ_ONLY_TOOLS,
        "openWorldHint": True,
    }


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


def t_resolve_candidates(args: dict) -> str:
    """把模型提出的候选批量落到真实 catalog 元数据上，不做语义评分。"""
    cfg = am.load_config()
    dev = am.get_developer_token(cfg)
    sf = am.resolve_storefront(args.get("storefront"), cfg, dev, am.get_user_token(cfg))
    queries = [item.strip() for item in args["tracks"]]

    matched: list[tuple[int, str, str]] = []
    candidates_by_index: dict[int, dict] = {}
    for index, query in enumerate(queries):
        ids, gone = am.resolve_tracks([query], dev, sf, quiet=True)
        if gone or not ids:
            candidates_by_index[index] = {
                "input_index": index, "input": query, "status": "unmatched",
            }
        else:
            matched.append((index, query, ids[0]))

    metadata = catalog_meta([catalog_id for _, _, catalog_id in matched], dev, sf)
    first_input_by_id: dict[str, int] = {}
    artist_recordings: dict[str, set[str]] = {}
    duplicate_count = 0
    for index, query, catalog_id in matched:
        item = metadata.get(catalog_id) or {}
        artist = item.get("artistName") or ""
        if artist:
            artist_recordings.setdefault(artist, set()).add(catalog_id)
        duplicate_of = first_input_by_id.get(catalog_id)
        if duplicate_of is None:
            first_input_by_id[catalog_id] = index
        else:
            duplicate_count += 1
        duration_ms = item.get("durationInMillis")
        row = {
            "input_index": index,
            "input": query,
            "status": "resolved",
            "catalog_id": catalog_id,
            "name": item.get("name"),
            "artist": artist or None,
            "album": item.get("albumName"),
            "release_date": item.get("releaseDate"),
            "genres": item.get("genreNames") or [],
            "duration_seconds": round(duration_ms / 1000, 1) if duration_ms else None,
            "content_rating": item.get("contentRating"),
            "has_lyrics": item.get("hasLyrics") if "hasLyrics" in item else None,
            "isrc": item.get("isrc"),
            "version_markers": am.version_noise_hits(item.get("name") or ""),
        }
        if duplicate_of is not None:
            row["duplicate_of_input_index"] = duplicate_of
        candidates_by_index[index] = row

    concentrated = [
        {"artist": artist, "count": len(recordings)}
        for artist, recordings in sorted(
            artist_recordings.items(), key=lambda pair: (-len(pair[1]), pair[0]))
        if len(recordings) > 2
    ]
    candidates = [candidates_by_index[index] for index in range(len(queries))]
    result = {
        "storefront": sf,
        "summary": {
            "input_count": len(queries),
            "resolved_count": len(matched),
            "unmatched_count": len(queries) - len(matched),
            "duplicate_recordings": duplicate_count,
            "artists_over_two_tracks": concentrated,
        },
        "candidates": candidates,
        "selection_note": (
            "Use the user's original words to compare these grounded candidates directly. "
            "Treat has_lyrics=false as unknown, not proof of an instrumental. Prefer explicit "
            "reasons and playlist roles over scalar theme-fit scores."
        ),
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


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


def t_optimize(args: dict) -> str:
    """算出更好的曲序。**只读**——不改动任何歌单。

    输入三选一：`tracks`（自由重排）/ `blocks`（段落顺序不动，段内重排）/ `playlist`（重排现有歌单）。
    返回的报告里带一份可直接交给 am_create_playlist 的曲目列表。
    """
    cfg = am.load_config()
    dev = am.get_developer_token(cfg)
    user = am.require_user(cfg)
    sf = am.resolve_storefront(None, cfg, dev, user)
    arc = args.get("arc") or opt_mod.DEFAULT_SHAPE
    refresh = bool(args.get("refresh"))
    isrcs = bool(args.get("isrcs"))

    missed: list[str] = []
    entries: list[dict] = []

    if args.get("playlist"):
        if args.get("tracks") or args.get("blocks"):
            return "playlist 与 tracks/blocks 只能给一个。"
        p = am.find_playlist(args["playlist"], dev, user)
        if not p:
            return f"找不到歌单: {args['playlist']}"
        cids = []
        for t in am.playlist_tracks(p["id"], dev, user):
            pp = (t.get("attributes") or {}).get("playParams") or {}
            cid = pp.get("catalogId") or pp.get("id")
            if cid:
                cids.append(str(cid))
        cm = catalog_meta(cids, dev, sf)
        entries = [{"cid": c, "name": (cm.get(c) or {}).get("name"),
                    "artist": (cm.get(c) or {}).get("artistName"),
                    "isrc": (cm.get(c) or {}).get("isrc")} for c in cids]
        source = f"现有歌单「{p['attributes'].get('name')}」：{len(entries)} 首"
    else:
        groups = args.get("blocks") or ([args["tracks"]] if args.get("tracks") else [])
        groups = [g for g in groups if g]
        if not groups:
            return "请给出 tracks、blocks 或 playlist 之一。"
        multi = len(groups) > 1
        for gi, group in enumerate(groups, 1):
            ids, gone = am.resolve_tracks(list(group), dev, sf, isrcs=isrcs)
            missed += gone
            cm = catalog_meta(ids, dev, sf)
            for c in ids:
                m = cm.get(c) or {}
                entries.append({"cid": c, "name": m.get("name"), "artist": m.get("artistName"),
                                "isrc": m.get("isrc"), "block": f"B{gi}" if multi else None})
        source = (f"给定 {len(groups)} 组共 {sum(len(g) for g in groups)} 项："
                  f"{len(entries)} 首匹配成功")

    if not entries:
        return f"{source}，但没有解析出任何可排序的曲目。未匹配：{missed or '（无）'}"

    # 只有拿到 ISRC 才查得到音频特征；没有的那些会被标记出来而不是静默丢掉。
    feature_input = [(e["cid"], e.get("name") or e["cid"], e.get("artist") or "", e.get("isrc"))
                     for e in entries if e.get("isrc")]
    features = flow_mod.fetch_features("mcp-order", feature_input, refresh)

    _, report = opt_mod.order_from_features(entries, features, arc=arc)

    lines = [source]
    if missed:
        lines.append(f"未匹配、已排除（{len(missed)}）：{', '.join(missed)}")
    lines.append("")
    lines.append(report)
    return "\n".join(lines)


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
    "am_resolve_candidates": t_resolve_candidates,
    "am_list_playlists": t_list,
    "am_show_playlist": t_show,
    "am_create_playlist": t_create,
    "am_add_tracks": t_add,
    "am_delete_playlist": t_delete,
    "am_audit_playlist": t_audit,
    "am_analyze_flow": t_flow,
    "am_optimize_order": t_optimize,
    "am_recently_played": t_recent,
    "am_top_played": t_top,
}


# ---------------------------------------------------------------- JSON-RPC 循环

def send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _invalid_arguments(rid, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32602, "message": message}}


def _contains_lone_surrogate(value) -> bool:
    """Return whether decoded JSON contains text that cannot be encoded as UTF-8.

    Standards-compliant MCP clients send UTF-8.  Some manual Windows shell pipelines can decode
    bytes with the wrong code page and leave lone surrogate characters in an otherwise valid JSON
    string.  Reject that input at the protocol boundary instead of discovering it during an Apple
    Music write and reporting an internal error.
    """
    if isinstance(value, str):
        return any(0xD800 <= ord(char) <= 0xDFFF for char in value)
    if isinstance(value, list):
        return any(_contains_lone_surrogate(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_lone_surrogate(key) or _contains_lone_surrogate(item)
                   for key, item in value.items())
    return False


def _render_playlist_prompt(arguments: dict) -> str:
    description = arguments["description"].strip()
    name = arguments.get("name", "").strip() or "Propose a concise name that fits the brief"
    track_count = arguments.get("track_count", "").strip() or "25"
    language = arguments.get("language", "").strip() or "the user's language"
    return f"""Create an Apple Music playlist from this brief:

{description}

Requested name: {name}
Requested size: {track_count} tracks
Response language: {language}

Use the Apple Music MCP tools to complete the task, not merely to suggest a list:
1. Interpret the brief. Make reasonable assumptions instead of asking many questions; ask only if a missing choice would materially change the result.
2. Call am_status before any write. If the user asks for personalization, use am_recently_played or am_top_played as supporting taste signals.
3. Curate a candidate pool about 1.5–2 times the requested size. Use your direct understanding of the user's words, musical context, and relationships between songs. Do not turn theme fit into arbitrary 0–1 scores.
4. Call am_resolve_candidates on that pool. Apple catalog data is the source of truth for availability and versions; do not invent catalog IDs. Treat has_lyrics=false as unknown, never as proof that a track is instrumental.
5. Compare candidates directly within the role they could play: opening, development, peak, release, or landing. Prefer explicit natural-language reasons (essential / strong / bridge / optional / reject) over point scores. Unless the brief says otherwise, prefer original studio versions, avoid duplicates, and normally keep no more than two tracks per artist.
6. Select the final set and arrange those narrative roles into ordered blocks. am_optimize_order is optional and may refine transitions inside blocks; it must not decide which songs fit the theme.
7. Call am_create_playlist with dry_run=true using "Title - Artist" strings. Review misses and suspicious matches, revise candidates, and dry-run again when needed.
8. Once the preview is sound, create the playlist with dry_run=false. If the user explicitly asked only for a plan or preview, stop before this write.
9. Report the playlist name, ID, track count, unmatched tracks, and the most important curation choices briefly.

The language model in the MCP client performs the curation. This MCP server does not call or require a separate LLM provider."""


def _validate_prompt_arguments(arguments) -> str | None:
    if not isinstance(arguments, dict):
        return "prompt arguments must be a JSON object"
    if _contains_lone_surrogate(arguments):
        return "prompt arguments must contain valid Unicode text encoded as UTF-8"
    allowed = {item["name"] for item in PROMPTS[0]["arguments"]}
    unknown = sorted(set(arguments) - allowed)
    if unknown:
        return f"unknown prompt argument(s): {', '.join(unknown)}"
    if "description" not in arguments:
        return "missing required prompt argument: description"
    for key, value in arguments.items():
        if not isinstance(value, str):
            return f"prompt argument '{key}' must be string"
    if not arguments["description"].strip():
        return "prompt argument 'description' must not be empty"
    return None


def _validate_tool_arguments(name: str, arguments) -> str | None:
    if not isinstance(arguments, dict):
        return "tool arguments must be a JSON object"
    if _contains_lone_surrogate(arguments):
        return "tool arguments must contain valid Unicode text encoded as UTF-8"
    tool = next((item for item in TOOLS if item["name"] == name), None)
    if tool is None:
        return None
    missing = [key for key in tool["inputSchema"].get("required", [])
               if key not in arguments]
    if missing:
        return f"missing required argument(s): {', '.join(missing)}"
    properties = tool["inputSchema"].get("properties", {})
    unknown = sorted(set(arguments) - set(properties))
    if unknown and tool["inputSchema"].get("additionalProperties") is False:
        return f"unknown argument(s): {', '.join(unknown)}"
    expected_types = {
        "string": lambda value: isinstance(value, str),
        "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
        "boolean": lambda value: isinstance(value, bool),
        "array": lambda value: isinstance(value, list),
    }
    for key, value in arguments.items():
        schema = properties.get(key, {})
        expected = schema.get("type")
        checker = expected_types.get(expected)
        if checker and not checker(value):
            return f"argument '{key}' must be {expected}"
        if "enum" in schema and value not in schema["enum"]:
            return f"argument '{key}' must be one of: {', '.join(map(str, schema['enum']))}"
        if isinstance(value, str) and len(value) < schema.get("minLength", 0):
            return f"argument '{key}' must not be empty"
        if isinstance(value, int) and not isinstance(value, bool):
            if "minimum" in schema and value < schema["minimum"]:
                return f"argument '{key}' must be >= {schema['minimum']}"
            if "maximum" in schema and value > schema["maximum"]:
                return f"argument '{key}' must be <= {schema['maximum']}"
        if isinstance(value, list):
            if len(value) < schema.get("minItems", 0):
                return f"argument '{key}' must not be empty"
            if "maxItems" in schema and len(value) > schema["maxItems"]:
                return f"argument '{key}' must contain at most {schema['maxItems']} items"
            item_type = schema.get("items", {}).get("type")
            item_checker = expected_types.get(item_type)
            if item_checker and any(not item_checker(item) for item in value):
                return f"every item in argument '{key}' must be {item_type}"
            item_min_length = schema.get("items", {}).get("minLength", 0)
            if item_type == "string" and any(len(item.strip()) < item_min_length for item in value):
                return f"every item in argument '{key}' must not be empty"
    return None


def handle(req: dict):
    if not isinstance(req, dict):
        return {"jsonrpc": "2.0", "id": None,
                "error": {"code": -32600, "message": "invalid request"}}
    if req.get("jsonrpc") != "2.0" or not isinstance(req.get("method"), str):
        return {"jsonrpc": "2.0", "id": req.get("id"),
                "error": {"code": -32600, "message": "invalid request"}}
    method = req.get("method")
    rid = req.get("id")
    params = req.get("params") or {}
    if not isinstance(params, dict):
        return _invalid_arguments(rid, "params must be a JSON object")

    if method == "initialize":
        want = params.get("protocolVersion") or PROTOCOL_VERSION
        selected = want if want in SUPPORTED_PROTOCOL_VERSIONS else PROTOCOL_VERSION
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": selected,
            "capabilities": {
                "tools": {"listChanged": False},
                "prompts": {"listChanged": False},
            },
            "serverInfo": SERVER_INFO,
            "instructions": SERVER_INSTRUCTIONS,
        }}
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    if method == "prompts/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"prompts": PROMPTS}}
    if method == "prompts/get":
        name = params.get("name")
        if name != PLAYLIST_PROMPT_NAME:
            return _invalid_arguments(rid, f"unknown prompt: {name}")
        arguments = params.get("arguments", {})
        error = _validate_prompt_arguments(arguments)
        if error:
            return _invalid_arguments(rid, error)
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "description": PROMPTS[0]["description"],
            "messages": [{
                "role": "user",
                "content": {"type": "text", "text": _render_playlist_prompt(arguments)},
            }],
        }}
    if method == "tools/call":
        name = params.get("name")
        fn = HANDLERS.get(name)
        if fn is None:
            return {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32602, "message": f"unknown tool: {name}"}}
        arguments = params.get("arguments", {})
        error = _validate_tool_arguments(name, arguments)
        if error:
            return _invalid_arguments(rid, error)
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):     # 绝不能污染协议通道
                text = fn(arguments)
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
            send({"jsonrpc": "2.0", "id": None,
                  "error": {"code": -32700, "message": "parse error"}})
            continue
        resp = handle(req)
        if resp is not None:
            send(resp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
