"""Experimental NetEase metadata adapter; no login harvesting or audio downloads.

The direct backend uses undocumented web endpoints. A separately managed loopback
API Enhanced gateway is optional. Neither backend implies official API support.
"""
from __future__ import annotations

import json
import hashlib
import http.cookies
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import catalog_matching as matching
import netease_session as sessions


class NeteaseError(RuntimeError):
    def __init__(self, message, *, kind="api", code=None, outcome="not-started"):
        super().__init__(message)
        self.kind, self.code, self.outcome = kind, code, outcome

    def public(self):
        return {"kind": self.kind, "code": self.code, "write_outcome": self.outcome,
                "retry_create": False}


ROUTES = {
    "search": ("/api/search/get", "/search"),
    "songs": ("/api/v3/song/detail", "/song/detail"),
    "playlist": ("/api/v6/playlist/detail", "/playlist/detail"),
    "playlists": ("/api/user/playlist", "/user/playlist"),
    "account": ("/api/w/nuser/account/get", "/user/account"),
    "recent": ("/api/play-record/song/list", "/record/recent/song"),
    "top": ("/api/v1/play/record", "/user/record"),
    "create": ("/api/playlist/create", "/playlist/create"),
    "tracks": ("/api/playlist/manipulate/tracks", "/playlist/tracks"),
    "order": ("/api/playlist/manipulate/tracks", "/song/order/update"),
    "description": ("/api/playlist/desc/update", "/playlist/desc/update"),
    "delete": ("/api/playlist/remove", "/playlist/delete"),
    "likes": ("/api/song/like/get", "/likelist"),
    "albums": ("/api/album/sublist", "/album/sublist"),
    "artists": ("/api/artist/sublist", "/artist/sublist"),
    "qr_key": ("/api/login/qrcode/unikey", "/login/qr/key"),
    "qr_image": (None, "/login/qr/create"),
    "qr_check": ("/api/login/qrcode/client/login", "/login/qr/check"),
}
WRITES = {"create", "tracks", "order", "description", "delete"}


def song_id(value):
    value = str(value)
    if value.startswith("netease:"):
        value = value.removeprefix("netease:")
    if not value.isascii() or not value.isdecimal() or int(value) <= 0:
        raise ValueError("Expected a positive NetEase ID or netease:<id>")
    return str(int(value))


def page_info(offset, limit, total, *, more=None):
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError("offset must be a nonnegative integer")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be 1..100")
    has_more = offset + limit < total if more is None else more
    return {"offset": offset, "limit": limit, "total": total, "has_more": has_more,
            "next_offset": offset + limit if has_more else None}


def snapshot_ids(ids, supplied=None):
    value = hashlib.sha256(",".join(ids).encode("ascii")).hexdigest()
    if supplied is not None and supplied != value:
        raise NeteaseError("Collection changed between pages; restart at offset=0", kind="snapshot-changed")
    return value


def song_rows(ids, metadata):
    return [metadata.get(i) or {"provider": "netease", "id": f"netease:{i}",
            "song_id": i, "status": "metadata-unavailable"} for i in ids]


def normalize_song(raw):
    sid = song_id(raw["id"])
    artists = raw.get("ar") or raw.get("artists") or []
    album = raw.get("al") or raw.get("album") or {}
    millis = raw.get("dt", raw.get("duration"))
    published = raw.get("publishTime") or 0
    date = None
    if isinstance(published, (int, float)) and published > 0:
        try:
            date = datetime.fromtimestamp(published / 1000, timezone.utc).date().isoformat()
        except (ValueError, OverflowError, OSError):
            pass
    name = raw.get("name") or ""
    return {
        "provider": "netease", "id": f"netease:{sid}", "song_id": sid,
        "name": name, "artists": [a["name"] for a in artists if a.get("name")],
        "artist": " / ".join(a["name"] for a in artists if a.get("name")),
        "album": album.get("name"), "release_date": date,
        "duration_seconds": millis / 1000 if isinstance(millis, (int, float)) else None,
        "artwork_url": album.get("picUrl"),
        "url": f"https://music.163.com/#/song?id={sid}",
        "isrc": raw.get("isrc"), "genres": None, "has_lyrics": None,
        "version_markers": matching.version_noise_hits(name),
        "availability": "unknown", "fee": raw.get("fee"),
    }


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise NeteaseError("Redirect rejected; credentials must stay on the configured origin")


class NeteaseClient:
    def __init__(self, *, cookie=None, gateway=None):
        stored = {}
        if cookie is None and not os.environ.get("NETEASE_COOKIE"):
            stored = sessions.load()
        self.session_source = "explicit" if cookie is not None else "environment" if os.environ.get("NETEASE_COOKIE") else "local-store" if stored else "none"
        self.cookie = (os.environ.get("NETEASE_COOKIE") or stored.get("cookie", "")) if cookie is None else cookie
        self.csrf = os.environ.get("NETEASE_CSRF") or stored.get("csrf", "")
        for part in self.cookie.split(";"):
            if part.strip().startswith("__csrf=") and not self.csrf:
                self.csrf = part.strip().split("=", 1)[1]
        self.gateway = (os.environ.get("NETEASE_API_URL", "") if gateway is None else gateway).rstrip("/")
        if self.gateway:
            parsed = urllib.parse.urlsplit(self.gateway)
            if (parsed.scheme not in {"http", "https"} or parsed.hostname not in
                    {"127.0.0.1", "localhost", "::1"} or parsed.username or
                    parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}):
                raise ValueError("NETEASE_API_URL must be a loopback HTTP(S) origin")
        self.opener = urllib.request.build_opener(NoRedirect())

    def ensure_csrf(self):
        """Read server-issued CSRF cookies only; never fabricate one or refresh MUSIC_U."""
        if self.csrf:
            return True
        if not self.cookie:
            raise NeteaseError("Login required", kind="login-required")
        for url in ("https://music.163.com/", "https://music.163.com/api/w/nuser/account/get"):
            req = urllib.request.Request(url, headers={"Cookie": self.cookie,
                "Referer": "https://music.163.com/", "User-Agent": "Mozilla/5.0"})
            try:
                with self.opener.open(req, timeout=10) as response:
                    for header in response.headers.get_all("Set-Cookie", []):
                        parsed = http.cookies.SimpleCookie()
                        parsed.load(header)
                        if "__csrf" in parsed and parsed["__csrf"].value:
                            self.csrf = parsed["__csrf"].value
                            self.cookie += "; __csrf=" + self.csrf
                            return True
            except Exception:
                continue
        raise NeteaseError("CSRF unavailable; re-import the browser session locally", kind="csrf-required")

    def request(self, route, params=None):
        if route not in ROUTES:
            raise ValueError("Unknown route")
        data = dict(params or {})
        direct, proxy = ROUTES[route]
        if route in WRITES:
            if not self.cookie:
                raise NeteaseError("Login required", kind="login-required")
            self.ensure_csrf()
        if self.gateway:
            url = self.gateway + proxy
            if route == "order":
                data["ids"] = json.dumps(data["ids"].split(","))
            if route == "delete":
                data["id"] = song_id(data.pop("ids"))
            # POST keeps gateway cookies and CSRF tokens out of URLs/access logs.
            if self.cookie:
                cookie = self.cookie
                if self.csrf:
                    cookie = "; ".join(p for p in cookie.split(";")
                                       if not p.strip().startswith("__csrf="))
                    cookie += "; __csrf=" + self.csrf
                data["cookie"] = cookie
            payload = urllib.parse.urlencode(data).encode("utf-8")
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
        else:
            if direct is None:
                raise NeteaseError("QR image rendering requires a local gateway", kind="unsupported")
            url = "https://music.163.com" + direct
            if route == "search":
                data["s"] = data.pop("keywords")
            if route == "songs":
                data["c"] = json.dumps([{"id": int(i)} for i in data.pop("ids").split(",")])
            if route in {"tracks", "order"}:
                data["trackIds"] = json.dumps(data.pop("tracks", data.pop("ids", "")).split(","))
                if route == "order":
                    data["op"] = "update"
            if route == "delete":
                data["ids"] = json.dumps([int(song_id(data["ids"]))])
            headers = {"Referer": "https://music.163.com/", "User-Agent": "Mozilla/5.0"}
            if self.cookie:
                headers["Cookie"] = self.cookie
            if route in WRITES:
                if not self.cookie or not self.csrf:
                    raise NeteaseError("Direct writes require NETEASE_COOKIE and __csrf / NETEASE_CSRF")
                data["csrf_token"] = self.csrf
                payload = urllib.parse.urlencode(data).encode("utf-8")
                headers["Content-Type"] = "application/x-www-form-urlencoded"
            elif route in {"playlists", "recent"}:
                # These web endpoints silently ignore GET query pagination. Read-only POST
                # carries their parameters correctly, without changing account state.
                payload = urllib.parse.urlencode(data).encode("utf-8")
                headers["Content-Type"] = "application/x-www-form-urlencoded"
            else:
                url += "?" + urllib.parse.urlencode(data)
                payload = None
        req = urllib.request.Request(url, data=payload, headers=headers)
        try:
            with self.opener.open(req, timeout=15) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
                if len(raw) > 8 * 1024 * 1024:
                    raise ValueError("Response exceeds beta transport limit")
                body = json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            kind = "login-expired" if exc.code in {401, 403} else "rate-limited" if exc.code == 429 else "http"
            raise NeteaseError("HTTP failure; no automatic retry", kind=kind, code=exc.code,
                               outcome="unknown" if route in WRITES else "not-started") from None
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            raise NeteaseError("Network/JSON failure; no automatic retry", kind="network",
                               outcome="unknown" if route in WRITES else "not-started") from None
        allowed = {200, 201, 800, 801, 802, 803} if route == "qr_check" else {200, 201}
        if not isinstance(body, dict) or body.get("code") not in allowed:
            code = body.get("code") if isinstance(body, dict) else "invalid"
            code = code if isinstance(code, int) and not isinstance(code, bool) else None
            kind = "login-expired" if code in {301, 302, 401} else "rate-limited" if code == 429 else "api"
            raise NeteaseError("NetEase rejected the operation", kind=kind, code=code,
                               outcome="rejected" if route in WRITES else "not-started")
        return body

    def account_id(self):
        if not self.cookie:
            raise NeteaseError("NETEASE_COOKIE is not configured; no credentials are harvested")
        data = self.request("account")
        return song_id((data.get("account") or {}).get("id") or
                       (data.get("profile") or {}).get("userId"))

    def search(self, term, limit=5, kind="songs", offset=0):
        body = self.request("search", {"keywords": term, "type":
                            {"songs": 1, "albums": 10, "artists": 100}[kind],
                            "limit": limit, "offset": offset})
        result = body.get("result") or {}
        rows = result.get({"songs": "songs", "albums": "albums", "artists": "artists"}[kind]) or []
        return {"items": [normalize_song(s) for s in rows] if kind == "songs" else rows,
                "offset": offset, "limit": limit, "total": result.get(
                    {"songs": "songCount", "albums": "albumCount", "artists": "artistCount"}[kind]),
                "note": "A discovery page, not a complete catalog. Availability is not verified."}

    def metadata(self, ids):
        """The only NetEase batch metadata-fetching implementation."""
        ids = list(dict.fromkeys(song_id(i) for i in ids))
        out = {}
        for start in range(0, len(ids), 100):
            body = self.request("songs", {"ids": ",".join(ids[start:start + 100])})
            for raw in body.get("songs") or []:
                row = normalize_song(raw)
                out[row["song_id"]] = row
        return out

    def playlists(self):
        uid, offset, rows, seen = self.account_id(), 0, [], set()
        while True:
            body = self.request("playlists", {"uid": uid, "offset": offset, "limit": 50})
            page = body.get("playlist") or []
            fresh = [p for p in page if str(p["id"]) not in seen]
            rows.extend(fresh)
            seen.update(str(p["id"]) for p in fresh)
            if not isinstance(body.get("more"), bool) or not isinstance(body.get("playlist"), list):
                raise NeteaseError("Incomplete playlist pagination response", kind="incomplete-response")
            if not body["more"]:
                return rows
            if not fresh:
                raise NeteaseError("Playlist pagination stalled; refusing to report a complete library")
            offset += len(page)

    def playlists_page(self, offset=0, limit=20, snapshot=None):
        page_info(offset, limit, 0)
        # Direct web API sometimes ignores limit/offset entirely. Full enumeration also
        # supports gateways that paginate correctly; only bounded summaries reach MCP.
        all_rows = self.playlists()
        current = snapshot_ids([song_id(p["id"]) for p in all_rows], snapshot)
        rows = all_rows[offset:offset + limit]
        return {"playlists": [{"id": song_id(p["id"]), "name": p.get("name"),
                "track_count": p.get("trackCount"), "creator_id":
                str((p.get("creator") or {}).get("userId", ""))} for p in rows],
                **page_info(offset, limit, len(all_rows)), "returned": len(rows), "snapshot": current,
                "complete": offset == 0 and len(rows) == len(all_rows),
                "note": "Bounded summaries after full enumeration; use snapshot on subsequent pages."}

    def playlist(self, value, *, offset=0, limit=None, snapshot=None):
        if limit is not None:
            page_info(offset, limit, 0)
        try:
            pid = song_id(value)
        except ValueError:
            matches = [p for p in self.playlists() if p.get("name") == value]
            if len(matches) != 1:
                raise ValueError("Playlist name missing/ambiguous; use an exact numeric ID")
            pid = song_id(matches[0]["id"])
        info = self.request("playlist", {"id": pid}).get("playlist") or {}
        if str(info.get("id")) != pid:
            raise NeteaseError("Playlist response did not identify the requested playlist")
        if not isinstance(info.get("trackIds"), list):
            raise NeteaseError("Missing trackIds; not an empty playlist", kind="incomplete-response")
        ids = [song_id(t["id"]) for t in info["trackIds"]]
        if info.get("trackCount", len(ids)) != len(ids):
            raise NeteaseError("Incomplete trackIds; playlist content cannot be verified")
        current = snapshot_ids([pid, *ids], snapshot)
        selected = ids if limit is None else ids[offset:offset + limit]
        meta = self.metadata(selected)
        tracks = song_rows(selected, meta)
        return {"id": pid, "name": info.get("name"), "creator_id":
                str((info.get("creator") or {}).get("userId", "")),
                "tracks": tracks, "track_count": len(ids),
                "privacy": info.get("privacy"), "description": info.get("description"),
                "snapshot": current, "returned": len(tracks),
                **(page_info(offset, limit, len(ids)) if limit is not None else
                   {"offset": 0, "total": len(ids), "has_more": False, "next_offset": None}),
                "metadata_missing": [i for i in selected if i not in meta]}

    def get_songs(self, ids):
        if not 1 <= len(ids) <= 100:
            raise ValueError("Provide 1..100 song IDs")
        ids = [song_id(i) for i in ids]
        meta = self.metadata(ids)
        return {"songs": song_rows(ids, meta), "requested": len(ids),
                "metadata_missing": [i for i in ids if i not in meta]}

    def liked_songs_page(self, offset=0, limit=20, snapshot=None):
        page_info(offset, limit, 0)
        body = self.request("likes", {"uid": self.account_id()})
        if not isinstance(body.get("ids"), list):
            raise NeteaseError("Missing liked-song IDs", kind="incomplete-response")
        ids = sorted({song_id(i) for i in body["ids"]}, key=int)
        current = snapshot_ids(ids, snapshot)
        selected = ids[offset:offset + limit]
        meta = self.metadata(selected)
        return {"songs": song_rows(selected, meta), "returned": len(selected),
                **page_info(offset, limit, len(ids)), "snapshot": current,
                "metadata_missing": [i for i in selected if i not in meta],
                "note": "Liked membership, NOT play count, liking date or listening order; numeric ID order only."}

    def collection_page(self, kind, offset=0, limit=20):
        if kind not in {"albums", "artists"}:
            raise ValueError("Unknown collection")
        page_info(offset, limit, 0)
        self.account_id()
        body = self.request(kind, {"offset": offset, "limit": limit, "total": "true"})
        rows, total = body.get("data"), body.get("count")
        marker = body.get("hasMore", body.get("more"))
        if (not isinstance(rows, list) or len(rows) > limit or
                (marker is not None and not isinstance(marker, bool))):
            raise NeteaseError("Invalid collection page", kind="incomplete-response")
        if not isinstance(total, int) or isinstance(total, bool) or total < 0:
            total = None
        if total is None and marker is None:
            raise NeteaseError("Collection lacks pagination evidence", kind="incomplete-response")
        more = marker if marker is not None else offset + len(rows) < total
        if more and not rows:
            raise NeteaseError("Collection pagination stalled", kind="incomplete-response")
        compact = [{"id": song_id(r["id"]), "name": r.get("name"),
                    "artwork_url": r.get("picUrl", r.get("img1v1Url")),
                    "artists": [a.get("name") for a in r.get("artists", []) if a.get("name")]} for r in rows]
        return {kind: compact, "total": total, "offset": offset, "returned": len(rows),
                "has_more": more, "next_offset": offset + len(rows) if more else None,
                "complete": offset == 0 and not more,
                "note": "Collected albums/followed artists are membership, not listening counts; pages may change during traversal."}
