"""Beta regression suite: synthetic sessions/data only, every network call mocked."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import am_paths
import catalog_matching
import mcp_common
import netease_api as api
import netease_login as login
import netease_mcp_server as nc
import netease_session as sessions


def raw(i):
    return {"id": int(i), "name": "fixture", "ar": [{"name": "fixture artist"}], "al": {"name": "fixture album"}}


def row(i):
    return api.normalize_song(raw(i))


def fixture():
    c = api.NeteaseClient(cookie="MUSIC_U=synthetic", gateway="")
    c.account_id = Mock(return_value="9")
    c.request = Mock()
    c.metadata = Mock(side_effect=lambda ids: {str(i): row(i) for i in ids})
    return c


def call(name, args):
    return nc.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}})


class BetaTests(unittest.TestCase):
    def setUp(self):
        p = patch.dict(os.environ, {"NETEASE_COOKIE": "", "NETEASE_CSRF": "", "NETEASE_API_URL": "", "NETEASE_ENABLE_WRITES": "0"})
        p.start()
        self.addCleanup(p.stop)
        p = patch.object(sessions, "load", return_value={})
        p.start()
        self.addCleanup(p.stop)

    def test_large_playlist_fetches_only_selected_metadata(self):
        c = fixture()
        c.request.return_value = {"playlist": {"id": 22, "trackCount": 2000,
            "trackIds": [{"id": i} for i in range(1, 2001)]}}
        data = c.playlist("22", offset=100, limit=20)
        self.assertEqual(data["track_count"], 2000)
        self.assertEqual(data["returned"], 20)
        self.assertEqual(data["next_offset"], 120)
        c.metadata.assert_called_once_with([str(i) for i in range(101, 121)])
        self.assertEqual(data["tracks"][0]["song_id"], "101")

    def test_playlist_snapshot_detects_order_or_member_mutation(self):
        c = fixture()
        c.request.return_value = {"playlist": {"id": 22, "trackCount": 2, "trackIds": [{"id": 1}, {"id": 2}]}}
        first = c.playlist("22", limit=1)
        second = c.playlist("22", offset=1, limit=1, snapshot=first["snapshot"])
        self.assertEqual(second["tracks"][0]["song_id"], "2")
        c.request.return_value["playlist"]["trackIds"].reverse()
        with self.assertRaises(api.NeteaseError) as caught:
            c.playlist("22", offset=1, limit=1, snapshot=first["snapshot"])
        self.assertEqual(caught.exception.kind, "snapshot-changed")

    def test_missing_trackids_is_not_empty_playlist(self):
        c = fixture()
        c.request.return_value = {"playlist": {"id": 22, "trackCount": 0}}
        with self.assertRaises(api.NeteaseError):
            c.playlist("22", limit=20)

    def test_likes_snapshot_membership_and_missing_positions(self):
        c = fixture()
        c.request.return_value = {"ids": [3, 2, 1, 1]}
        c.metadata.side_effect = lambda ids: {i: row(i) for i in ids if i != "2"}
        data = c.liked_songs_page(limit=2)
        self.assertEqual(data["total"], 3)
        self.assertEqual(data["metadata_missing"], ["2"])
        self.assertEqual([r["song_id"] for r in data["songs"]], ["1", "2"])
        self.assertIn("NOT play count", data["note"])
        c.request.return_value = {"ids": [4, 2, 1]}
        with self.assertRaises(api.NeteaseError):
            c.liked_songs_page(2, 2, data["snapshot"])

    def test_likes_empty_vs_missing(self):
        c = fixture()
        c.request.return_value = {"ids": []}
        self.assertEqual(c.liked_songs_page()["total"], 0)
        c.request.return_value = {}
        with self.assertRaises(api.NeteaseError):
            c.liked_songs_page()

    def test_album_artist_counts_and_markers(self):
        for kind in ("albums", "artists"):
            c = fixture()
            c.request.return_value = {"data": [{"id": 1, "name": "fixture", "cookie": "DO-NOT-EXPOSE"}], "count": 3}
            data = c.collection_page(kind, 0, 1)
            self.assertEqual(data["next_offset"], 1)
            self.assertEqual(data["total"], 3)
            self.assertNotIn("DO-NOT-EXPOSE", json.dumps(data))
            c.request.return_value = {"data": [], "hasMore": False}
            self.assertTrue(c.collection_page(kind)["complete"])
            for invalid in ({"data": []}, {"data": [], "hasMore": True}, {"data": [], "hasMore": "false"}):
                c.request.return_value = invalid
                with self.assertRaises(api.NeteaseError):
                    c.collection_page(kind)

    def test_account_playlist_page_bounded_when_server_ignores_limit(self):
        c = fixture()
        c.request.return_value = {"playlist": [{"id": i} for i in range(1, 87)], "more": False}
        data = c.playlists_page(10, 3)
        self.assertEqual(data["total"], 86)
        self.assertEqual([p["id"] for p in data["playlists"]], ["11", "12", "13"])
        self.assertEqual(data["next_offset"], 13)
        self.assertFalse(data["complete"])
        c.request.return_value["playlist"].reverse()
        with self.assertRaises(api.NeteaseError):
            c.playlists_page(13, 3, data["snapshot"])
        c.request.return_value = {"playlist": []}
        with self.assertRaises(api.NeteaseError):
            c.playlists_page()
        with self.assertRaises(api.NeteaseError):
            c.playlists()

    def test_readonly_post_transports_pagination_without_write_gate(self):
        for route, params in (("playlists", {"uid": "9", "offset": 3, "limit": 3}), ("recent", {"limit": 100})):
            c = api.NeteaseClient(cookie="MUSIC_U=synthetic", gateway="")
            c.opener = MagicMock()
            c.opener.open.return_value.__enter__.return_value.read.return_value = b'{"code":200}'
            c.ensure_csrf = Mock()
            c.request(route, params)
            c.ensure_csrf.assert_not_called()
            req = c.opener.open.call_args.args[0]
            self.assertEqual(req.get_method(), "POST")
            self.assertIn("limit=", req.data.decode())
            self.assertNotIn("synthetic", req.full_url)

    def test_recent_server_overdelivery_bounded_and_playtime_preserved(self):
        c = fixture()
        c.request.return_value = {"data": {"total": 300, "list": [{"playTime": 1000*i, "data": {"id": i}} for i in range(1, 301)]}}
        data = nc.run_tool("nc_recently_played", {"limit": 3}, c)
        self.assertEqual(len(data["events"]), 3)
        self.assertEqual(data["events"][0]["time_ms"], 1000)
        self.assertEqual(data["total"], 100)
        self.assertEqual(data["server_reported_total"], 300)
        self.assertFalse(data["complete_history"])

    def test_get_songs_preserves_duplicates_order_and_missing(self):
        c = fixture()
        c.metadata.side_effect = lambda ids: {"1": row(1)}
        data = c.get_songs(["netease:2", "1", "1"])
        self.assertEqual([r["song_id"] for r in data["songs"]], ["2", "1", "1"])
        self.assertEqual(data["metadata_missing"], ["2"])
        with self.assertRaises(ValueError):
            c.get_songs(["1"] * 101)

    def test_bad_page_arguments_rejected_locally(self):
        for offset, limit in ((-1, 20), (True, 20), (0, 0), (0, 101), (0, True)):
            c = fixture()
            with self.assertRaises(ValueError):
                c.liked_songs_page(offset, limit)
            c.request.assert_not_called()

    def test_bounded_tools_and_new_collections_reachable_via_mcp(self):
        c = fixture()
        c.request.side_effect = lambda route, params=None: {
            "likes": {"ids": [1, 2]}, "albums": {"data": [{"id": 1}], "count": 1},
            "artists": {"data": [{"id": 1}], "count": 1},
            "playlists": {"playlist": [{"id": 22}], "more": False},
            "playlist": {"playlist": {"id": 22, "trackCount": 2, "trackIds": [{"id": 1}, {"id": 2}]}}
        }[route]
        with patch.object(nc, "NeteaseClient", return_value=c):
            for name, args in (("nc_liked_songs", {}), ("nc_collected_albums", {}),
                               ("nc_followed_artists", {}), ("nc_get_songs", {"ids": ["1", "2"]}),
                               ("nc_list_playlists", {}), ("nc_show_playlist", {"playlist": "22"})):
                result = call(name, args)["result"]
                self.assertFalse(result["isError"], name)
                self.assertIn("structuredContent", result)
                self.assertNotEqual(result["content"][0]["text"], json.dumps(result["structuredContent"]))
        c.metadata.assert_called_with(["1", "2"])

    def test_recent_window_not_lifetime_history_and_page_metadata_only(self):
        c = fixture()
        c.request.return_value = {"data": {"list": [{"time": 1000*i, "data": {"id": i}} for i in range(1, 8)]}}
        data = nc.run_tool("nc_recently_played", {"offset": 3, "limit": 2}, c)
        c.metadata.assert_called_once_with([4, 5])
        self.assertEqual([e["time_ms"] for e in data["events"]], [4000, 5000])
        self.assertFalse(data["complete_history"])
        self.assertEqual(data["next_offset"], 5)
        with self.assertRaises(ValueError):
            nc.run_tool("nc_recently_played", {"offset": 100}, c)

    def test_rankings_keep_count_zero_distinct_from_absent_and_score(self):
        c = fixture()
        c.request.return_value = {"allData": [{"song": raw(1), "playCount": 0, "score": 100}, {"song": raw(2), "score": 90}]}
        data = nc.run_tool("nc_top_played", {"limit": 1}, c)
        self.assertEqual(data["records"][0]["play_count"], 0)
        self.assertEqual(data["records"][0]["ranking_score"], 100)
        self.assertTrue(data["has_more"])
        c.metadata.assert_called_once_with([1])
        data = nc.run_tool("nc_top_played", {"offset": 1}, c)
        self.assertIsNone(data["records"][0]["play_count"])

    def test_missing_evidence_payload_not_silent_empty_history(self):
        c = fixture()
        c.request.return_value = {}
        for name in ("nc_recently_played", "nc_top_played"):
            with self.assertRaises(api.NeteaseError):
                nc.run_tool(name, {}, c)

    def test_netease_tag_chains_do_not_claim_song_plays_from_follows(self):
        args = {"brief": "original", "tags": [{"label": "recent", "axis": "context", "evidence":
            {"basis": "play-count", "call": "nc_followed_artists", "ref": "artist=1"}}]}
        data = nc.run_tool("nc_tag_directions", args)
        self.assertTrue(any("撑不住" in p for p in data["problems"]))
        args["tags"][0]["evidence"] = {"basis": "play-count", "call": "nc_top_played", "ref": "period=week"}
        args["adjustments"] = [{"op": "add", "label": "in liked", "axis": "context", "evidence":
            {"basis": "playlist-membership", "call": "nc_liked_songs", "ref": "offset=0 snapshot=fixture"}}]
        data = nc.run_tool("nc_tag_directions", args)
        self.assertFalse(any("撑不住" in p for p in data["problems"]))
        self.assertEqual(data["tags"][1]["evidence"]["call"], "nc_liked_songs")
        self.assertIn("声明", data["adjustments"][0]["detail"])

    def test_append_never_verifies_lost_original_or_reorder(self):
        for after_ids in ([3], [2, 1, 3], [3, 1, 2], [1, 2, 3, 4]):
            c = fixture()
            c.playlist = Mock(side_effect=[{"id": "22", "creator_id": "9", "tracks": [row(1), row(2)]},
                {"id": "22", "creator_id": "9", "tracks": [row(i) for i in after_ids]}])
            with patch.dict(os.environ, {"NETEASE_ENABLE_WRITES": "1"}), patch.object(nc, "NeteaseClient", return_value=c):
                result = call("nc_add_tracks", {"playlist": "22", "tracks": ["3"], "dry_run": False, "confirm": True})["result"]
            self.assertTrue(result["isError"])
            self.assertEqual(result["structuredContent"]["status"], "needs-review")
            self.assertEqual(c.request.call_count, 1)

    def test_append_existing_id_blocked_without_write(self):
        c = fixture()
        c.playlist = Mock(return_value={"id": "22", "creator_id": "9", "tracks": [row(1)]})
        with patch.dict(os.environ, {"NETEASE_ENABLE_WRITES": "1"}):
            with self.assertRaises(ValueError):
                nc.run_tool("nc_add_tracks", {"playlist": "22", "tracks": ["1"], "dry_run": False, "confirm": True}, c)
        c.request.assert_not_called()

    def test_delete_preview_does_not_dump_or_modify_large_playlist(self):
        c = fixture()
        c.playlist = Mock(return_value={"id": "22", "creator_id": "9", "track_count": 2000,
                                      "tracks": [row(i) for i in range(1, 2001)]})
        result = nc.run_tool("nc_delete_playlist", {"playlist": "22"}, c)
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["playlist"]["track_count"], 2000)
        self.assertNotIn("tracks", result["playlist"])
        c.request.assert_not_called()

    def test_large_append_readback_bounded_without_weakened_verification(self):
        c = fixture()
        original = [row(i) for i in range(1, 501)]
        c.playlist = Mock(side_effect=[{"id": "22", "creator_id": "9", "tracks": original},
            {"id": "22", "creator_id": "9", "tracks": original + [row(501)]}])
        with patch.dict(os.environ, {"NETEASE_ENABLE_WRITES": "1"}):
            result = nc.run_tool("nc_add_tracks", {"playlist": "22", "tracks": ["501"], "dry_run": False, "confirm": True}, c)
        self.assertTrue(result["verified"])
        self.assertEqual(result["actual_id_count"], 501)
        self.assertTrue(result["actual_ids_truncated"])
        self.assertEqual(len(result["actual_ids"]), 100)

    def test_create_verifies_privacy_description_order_and_owner(self):
        for changes, verified in (({}, True), ({"privacy": 0}, False), ({"description": "different"}, False), ({"creator_id": "10"}, False)):
            c = fixture()
            c.request.return_value = {"id": 22}
            c.playlist = Mock(return_value={"id": "22", "creator_id": "9", "tracks": [row(1)], "privacy": 10, "description": "fixture description", **changes})
            with patch.object(nc, "record_created"), patch.dict(os.environ, {"NETEASE_ENABLE_WRITES": "1"}):
                result = nc.run_tool("nc_create_playlist", {"name": "fixture", "tracks": ["1"], "description": "fixture description", "dry_run": False, "confirm": True}, c)
            self.assertEqual(result["verified"], verified)
            self.assertEqual(result["is_error"], not verified)

    def test_unknown_write_outcome_has_no_retry_and_retains_id(self):
        c = fixture()
        c.request.side_effect = [{"id": 22}, api.NeteaseError("secret", kind="network", outcome="unknown")]
        with patch.object(nc, "record_created"), patch.dict(os.environ, {"NETEASE_ENABLE_WRITES": "1"}):
            result = nc.run_tool("nc_create_playlist", {"name": "fixture", "tracks": ["1"], "dry_run": False, "confirm": True}, c)
        self.assertEqual(result["playlist_id"], "22")
        self.assertEqual(result["error"]["write_outcome"], "unknown")
        self.assertFalse(result["error"]["retry_create"])
        self.assertNotIn("secret", json.dumps(result))
        self.assertEqual(c.request.call_count, 2)

    def test_invalid_request_ids_never_crash_stdio(self):
        text = '\n'.join(['{"jsonrpc":"2.0","id":1e400,"method":"ping"}',
            '{"jsonrpc":"2.0","id":true,"method":"ping"}',
            '{"jsonrpc":"2.0","id":{},"method":"ping"}',
            '{"jsonrpc":"2.0","id":"\\ud800","method":"ping"}',
            '{"jsonrpc":"2.0","id":5,"method":"ping"}'])+'\n'
        result = subprocess.run([sys.executable, "-B", nc.__file__], input=text, encoding="utf-8", capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = list(map(json.loads, result.stdout.splitlines()))
        self.assertEqual(len(rows), 5)
        for response in rows[:4]:
            self.assertEqual(response["error"]["code"], -32600)
            self.assertIsNone(response["id"])
        self.assertEqual(rows[4]["result"], {})

    def test_public_errors_typed_and_secret_free(self):
        with patch.object(nc, "run_tool", side_effect=api.NeteaseError("MUSIC_U=SECRET", kind="login-expired", code=301)):
            result = call("nc_liked_songs", {})["result"]
        self.assertTrue(result["isError"])
        self.assertEqual(result["structuredContent"]["error"]["kind"], "login-expired")
        self.assertNotIn("SECRET", json.dumps(result))

    def test_local_session_corruption_reports_reimportable_error(self):
        with patch.object(nc, "NeteaseClient", side_effect=sessions.SessionError("SECRET")):
            result = call("nc_status", {})["result"]
        self.assertTrue(result["isError"])
        self.assertEqual(result["structuredContent"]["error"]["kind"], "local-session-unavailable")
        self.assertNotIn("SECRET", json.dumps(result))

    def test_stdio_utf8_and_bad_byte_recovery(self):
        brief = "深夜的海边、日本語、한국어"
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "nc_tag_directions", "arguments": {"brief": brief, "tags": ["sonic:quiet"]}}}
        source = b"\xff\n" + json.dumps(request, ensure_ascii=False).encode("utf-8") + b"\n"
        p = subprocess.run([sys.executable, "-B", nc.__file__], input=source, capture_output=True, timeout=15)
        self.assertEqual(p.returncode, 0, p.stderr)
        output = list(map(json.loads, p.stdout.decode("utf-8").splitlines()))
        self.assertEqual(output[0]["error"]["code"], -32700)
        self.assertEqual(output[1]["result"]["structuredContent"]["brief"], brief)

    def test_oversized_request_rejected_before_operation(self):
        line = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "nc_status", "padding": "x" * (1024 * 1024)}})
        source = line + '\n{"jsonrpc":"2.0","id":2,"method":"ping"}\n'
        p = subprocess.run([sys.executable, "-B", nc.__file__], input=source, encoding="utf-8", capture_output=True, timeout=15)
        self.assertEqual(p.returncode, 0, p.stderr)
        output = list(map(json.loads, p.stdout.splitlines()))
        self.assertEqual(output[0]["error"]["code"], -32700)
        self.assertEqual(output[1]["result"], {})

    def test_automatic_csrf_uses_server_header_only(self):
        c = api.NeteaseClient(cookie="MUSIC_U=synthetic", gateway="")
        response = Mock()
        response.headers = Message()
        response.headers.add_header("Set-Cookie", "MUSIC_U=do-not-import; Path=/")
        response.headers.add_header("Set-Cookie", "__csrf=server-value; Path=/; HttpOnly")
        response.read.return_value = b'{"code":200,"id":22}'
        c.opener = MagicMock()
        c.opener.open.return_value.__enter__.return_value = response
        c.request("create", {"name": "fixture"})
        self.assertEqual(c.csrf, "server-value")
        self.assertNotIn("do-not-import", c.cookie)
        self.assertEqual(c.opener.open.call_count, 2)
        req = c.opener.open.call_args.args[0]
        self.assertNotIn("synthetic", req.full_url)
        self.assertIn("csrf_token=server-value", req.data.decode())

    def test_csrf_failure_does_not_send_write(self):
        c = api.NeteaseClient(cookie="MUSIC_U=synthetic", gateway="")
        c.opener = MagicMock()
        c.opener.open.return_value.__enter__.return_value.headers = Message()
        with self.assertRaises(api.NeteaseError) as caught:
            c.request("create", {"name": "fixture"})
        self.assertEqual(caught.exception.kind, "csrf-required")
        for args in c.opener.open.call_args_list:
            self.assertIsNone(args.args[0].data)

    def test_expiry_and_rate_limiting_never_retry(self):
        for code, kind in ((301, "login-expired"), (429, "rate-limited")):
            c = api.NeteaseClient(cookie="MUSIC_U=synthetic; __csrf=fake", gateway="")
            c.opener = MagicMock()
            response = c.opener.open.return_value.__enter__.return_value
            response.read.return_value = json.dumps({"code": code, "cookie": "SECRET"}).encode()
            with self.assertRaises(api.NeteaseError) as caught:
                c.request("create", {"name": "fixture"})
            self.assertEqual(caught.exception.kind, kind)
            self.assertEqual(caught.exception.outcome, "rejected")
            self.assertEqual(c.opener.open.call_count, 1)
            self.assertNotIn("SECRET", str(caught.exception))

    def test_transport_bounds_oversized_response(self):
        c = api.NeteaseClient(cookie="", gateway="")
        c.opener = MagicMock()
        c.opener.open.return_value.__enter__.return_value.read.return_value = b" " * (8 * 1024 * 1024 + 1)
        with self.assertRaises(api.NeteaseError):
            c.request("songs", {"ids": "1"})
        c.opener.open.return_value.__enter__.return_value.read.assert_called_once_with(8 * 1024 * 1024 + 1)

    def test_import_is_hidden_tty_only_and_save_is_explicit(self):
        with patch.object(sys.stdin, "isatty", return_value=False), patch.object(login.getpass, "getpass") as get:
            with self.assertRaises(sessions.SessionError):
                login.hidden_cookie()
            get.assert_not_called()
        c = fixture()
        c.ensure_csrf = Mock()
        c.csrf = "synthetic"
        with patch.object(login, "NeteaseClient", return_value=c), patch.object(sessions, "save") as save:
            self.assertFalse(login.validate_and_save("synthetic")["saved"])
            save.assert_not_called()
            self.assertTrue(login.validate_and_save("synthetic", persist=True)["saved"])
            save.assert_called_once()

    def test_hidden_input_never_falls_back_to_echo(self):
        with patch.object(sys.stdin, "isatty", return_value=True), patch.object(login.getpass, "getpass", side_effect=login.getpass.GetPassWarning):
            with self.assertRaises(sessions.SessionError):
                login.hidden_cookie()

    def test_gateway_qr_auth_flow_cookie_never_printed_and_image_removed(self):
        c = fixture()
        c.gateway = "http://127.0.0.1:3000"
        c.request.side_effect = [{"data": {"unikey": "synthetic-key"}},
            {"data": {"qrimg": "data:image/png;base64,AA=="}},
            {"code": 801}, {"code": 802}, {"code": 803, "cookie": "MUSIC_U=SECRET"}]
        with tempfile.TemporaryDirectory() as tmp, patch.object(am_paths, "cache_dir", return_value=Path(tmp)), patch.object(login, "NeteaseClient", return_value=c), patch.object(login, "validate_and_save", return_value={"logged_in": True}) as validate, patch.object(login.time, "sleep"), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertTrue(login.qr_login()["logged_in"])
            self.assertFalse(list(Path(tmp).rglob("*.html")))
            validate.assert_called_once_with("MUSIC_U=SECRET", persist=False, allow_plaintext=False, gateway=c.gateway)
        self.assertNotIn("SECRET", output.getvalue())

    def test_qr_without_gateway_or_expired_rejected(self):
        c = fixture()
        with patch.object(login, "NeteaseClient", return_value=c):
            with self.assertRaises(sessions.SessionError):
                login.qr_login()
            c.request.assert_not_called()
            c.gateway = "http://127.0.0.1:3000"
            c.request.side_effect = [{"data": {"unikey": "fixture"}}, {"data": {"qrimg": "data:image/png;base64,AA=="}}, {"code": 800}]
            with tempfile.TemporaryDirectory() as tmp, patch.object(am_paths, "cache_dir", return_value=Path(tmp)), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(sessions.SessionError):
                    login.qr_login()
                self.assertFalse(list(Path(tmp).rglob("*.html")))

    def test_environment_session_overrides_saved_session(self):
        with patch.object(sessions, "load", return_value={"cookie": "MUSIC_U=saved", "csrf": "stored"}) as load:
            c = api.NeteaseClient(gateway="")
            self.assertEqual(c.session_source, "local-store")
            self.assertEqual(c.csrf, "stored")
            with patch.dict(os.environ, {"NETEASE_COOKIE": "MUSIC_U=environment"}):
                c = api.NeteaseClient(gateway="")
                self.assertEqual(c.session_source, "environment")
                self.assertEqual(c.cookie, "MUSIC_U=environment")
            self.assertEqual(load.call_count, 1)
            api.NeteaseClient(cookie="", gateway="")
            self.assertEqual(load.call_count, 1)

    def test_shared_imports_do_not_load_apple_adapter(self):
        script = """import builtins
original=builtins.__import__
def guard(name,*a,**kw):
 if name in {'am_playlist','am_mcp_server','am_meta','am_library'}: raise AssertionError(name)
 return original(name,*a,**kw)
builtins.__import__=guard
import netease_mcp_server, netease_login
assert len(netease_mcp_server.TOOLS)==20
"""
        result = subprocess.run([sys.executable, "-B", "-c", script], capture_output=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_existing_apple_matching_exports_still_same_function(self):
        import am_playlist
        import am_mcp_server
        self.assertIs(am_playlist.best_song_match, catalog_matching.best_song_match)
        self.assertIs(am_mcp_server._validate_schema_value, mcp_common._validate_schema_value)


class SessionStorageTests(unittest.TestCase):
    def test_sdk_concatenated_setcookie_unknown_flags_do_not_hide_authentication(self):
        header = ('MUSIC_U=synthetic; Path=/; Expires=Fri, 08 Oct 2027 03:00:00 GMT; '
                  'HttpOnly; Secure; Partitioned; __csrf=fixture; Path=/; SameSite=None; '
                  'NMTID=analytics; Path=/; NewFlag')
        self.assertEqual(sessions.clean_cookie(header), 'MUSIC_U=synthetic; __csrf=fixture')
        self.assertEqual(sessions.clean_cookie('Cookie: MUSIC_U=synthetic'), 'MUSIC_U=synthetic')
        with self.assertRaises(sessions.SessionError):
            sessions.clean_cookie('MUSIC_U=first; MUSIC_U=second')
    def test_clean_cookie_imports_only_authentication_fields(self):
        self.assertEqual(sessions.clean_cookie("synthetic"), "MUSIC_U=synthetic")
        self.assertEqual(sessions.clean_cookie("MUSIC_U=synthetic; __csrf=fake; WM_NI=analytics"), "MUSIC_U=synthetic; __csrf=fake")
        for text in ("", "foo=bar", "MUSIC_U=x\r\nCookie:y", "MUSIC_U=" + "x" * 17000,
                     'MUSIC_U="x; injected=y"', 'MUSIC_U="has spaces"'):
            with self.assertRaises(sessions.SessionError):
                sessions.clean_cookie(text)

    def test_roundtrip_current_platform_synthetic_only(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(sessions, "session_path", return_value=Path(tmp) / "nc" / "session.bin"):
            sessions.save("MUSIC_U=synthetic-test-token", "fixture-csrf", allow_plaintext=os.name != "nt")
            # In Windows, ciphertext must not contain the token. POSIX requires explicit consent.
            stored = sessions.session_path().read_bytes()
            if os.name == "nt":
                self.assertNotIn(b"synthetic-test-token", stored)
            else:
                self.assertEqual(sessions.session_path().stat().st_mode & 0o777, 0o600)
            loaded = sessions.load()
            self.assertEqual(loaded["csrf"], "fixture-csrf")
            self.assertEqual(loaded["cookie"], "MUSIC_U=synthetic-test-token")
            with self.assertRaises(sessions.SessionError):
                sessions.forget()
            self.assertTrue(sessions.describe()["saved"])
            sessions.forget(confirm=True)
            self.assertEqual(sessions.load(), {})

    @unittest.skipIf(os.name == "nt", "POSIX file-permission boundary")
    def test_posix_consent_and_permissions(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(sessions, "session_path", return_value=Path(tmp) / "session.bin"):
            with self.assertRaises(sessions.SessionError):
                sessions.save("synthetic")
            sessions.save("synthetic", allow_plaintext=True)
            sessions.session_path().chmod(0o644)
            with self.assertRaises(sessions.SessionError):
                sessions.load()

    def test_repository_paths_and_corrupt_protection_are_rejected(self):
        with patch.object(sessions, "session_path", return_value=am_paths.REPO_DIR / "never-written-session.bin"):
            with self.assertRaises(sessions.SessionError):
                sessions.save("synthetic", allow_plaintext=True)
        with tempfile.TemporaryDirectory() as tmp, patch.object(sessions, "session_path", return_value=Path(tmp) / "session.bin"):
            sessions.session_path().write_bytes(b"corrupt synthetic fixture")
            with self.assertRaises(sessions.SessionError):
                sessions.load()


if __name__ == "__main__":
    unittest.main()
