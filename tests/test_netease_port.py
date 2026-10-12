"""Offline NetEase regressions; no account, network or live writes."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import netease_api as api
import netease_mcp_server as nc


def raw(i, name="Get Lucky", artist="Daft Punk"):
    return {"id": int(i), "name": name, "ar": [{"name": artist}], "al": {"name": "RAM"}, "dt": 369000}


def song(i, name="Get Lucky", artist="Daft Punk"):
    return api.normalize_song(raw(i, name, artist))


def client():
    c = Mock(spec=api.NeteaseClient)
    c.cookie, c.gateway = "FAKE", ""
    c.account_id.return_value = "9"
    c.metadata.side_effect = lambda ids: {str(i): song(i) for i in ids}
    c.search.return_value = {"items": [song(1)]}
    c.playlist.return_value = {"id": "22", "name": "test", "creator_id": "9",
                              "tracks": [song(1), song(2)], "metadata_missing": []}
    return c


class NetEasePortTests(unittest.TestCase):
    def setUp(self):
        stored = patch.object(api.sessions, "load", return_value={})
        stored.start()
        self.addCleanup(stored.stop)
        env = patch.dict(os.environ, {"NETEASE_COOKIE": "", "NETEASE_CSRF": "", "NETEASE_API_URL": "", "NETEASE_ENABLE_WRITES": "0"})
        env.start()
        self.addCleanup(env.stop)

    def test_ids_and_gateway_reject_foreign_origins(self):
        self.assertEqual(api.song_id("netease:123"), "123")
        for value in ("apple:123", "１２３", "0", "1?token=secret"):
            with self.assertRaises(ValueError):
                api.song_id(value)
        for value in ("http://evil.example", "http://localhost@evil.example", "http://localhost/path"):
            with self.assertRaises(ValueError):
                api.NeteaseClient(gateway=value)
        with self.assertRaises(api.NeteaseError):
            api.NoRedirect().redirect_request(None, None, None, None, None, None)

    def test_unknown_metadata_is_not_invented(self):
        s = song(1)
        for key in ("isrc", "genres", "has_lyrics", "release_date"):
            self.assertIsNone(s[key])
        self.assertEqual(s["availability"], "unknown")

    def test_metadata_batching(self):
        c = api.NeteaseClient(cookie="")
        c.request = Mock(side_effect=[{"songs": [raw(i) for i in range(100, 0, -1)]}, {"songs": [raw(101)]}])
        self.assertEqual(len(c.metadata([str(i) for i in range(1, 102)])), 101)
        self.assertEqual(c.request.call_count, 2)

    def test_full_ids_not_truncated_tracks_and_missing_metadata_preserved(self):
        c = api.NeteaseClient(cookie="")
        c.request = Mock(return_value={"playlist": {"id": 22, "trackCount": 3,
            "trackIds": [{"id": 3}, {"id": 1}, {"id": 2}], "tracks": [raw(3)]}})
        c.metadata = Mock(return_value={"1": song(1), "3": song(3)})
        result = c.playlist("22")
        self.assertEqual([s["song_id"] for s in result["tracks"]], ["3", "1", "2"])
        self.assertEqual(result["metadata_missing"], ["2"])
        c.request.return_value["playlist"]["trackCount"] = 200
        with self.assertRaises(api.NeteaseError):
            c.playlist("22")

    def test_playlist_pagination_and_stall(self):
        c = api.NeteaseClient(cookie="FAKE")
        c.account_id = Mock(return_value="9")
        c.request = Mock(side_effect=[{"playlist": [{"id": 1}], "more": True},
                                     {"playlist": [{"id": 2}], "more": False}])
        self.assertEqual([p["id"] for p in c.playlists()], [1, 2])
        self.assertEqual(c.request.call_args_list[1].args[1]["offset"], 1)
        c.request = Mock(side_effect=[{"playlist": [{"id": 1}], "more": True}] * 2)
        with self.assertRaises(api.NeteaseError):
            c.playlists()

    def test_gateway_cookie_in_body_and_order_json(self):
        c = api.NeteaseClient(cookie="SECRET", gateway="http://localhost:3000")
        c.csrf = "TEST-CSRF"
        response = Mock()
        response.read.return_value = b'{"code":200}'
        c.opener = MagicMock()
        c.opener.open.return_value.__enter__.return_value = response
        c.request("order", {"pid": "22", "ids": "1,2"})
        req = c.opener.open.call_args.args[0]
        self.assertNotIn("SECRET", req.full_url)
        data = api.urllib.parse.parse_qs(req.data.decode())
        self.assertEqual(data["cookie"], ["SECRET; __csrf=TEST-CSRF"])
        self.assertEqual(json.loads(data["ids"][0]), ["1", "2"])
        response.read.return_value = b'{"code":301,"message":"secret"}'
        with self.assertRaises(api.NeteaseError) as caught:
            c.request("songs", {"ids": "1"})
        self.assertNotIn("secret", str(caught.exception))

    def test_direct_write_requires_csrf_before_network(self):
        c = api.NeteaseClient(cookie="FAKE")
        c.ensure_csrf = Mock(side_effect=api.NeteaseError("CSRF unavailable", kind="csrf-required"))
        c.opener = Mock()
        with self.assertRaises(api.NeteaseError):
            c.request("create", {"name": "x"})
        c.opener.open.assert_not_called()

    def test_failed_match_position_wrong_artist_and_ambiguity(self):
        c = client()
        c.search.return_value = {"items": [song(1, artist="Wrong") ]}
        result = nc.resolve(c, ["Get Lucky - Daft Punk", "netease:2"])
        self.assertEqual([s["status"] for s in result["candidates"]], ["unmatched", "resolved"])
        c.search.return_value = {"items": [song(1), song(2)]}
        result = nc.resolve(c, ["Get Lucky - Daft Punk"])
        self.assertEqual(result["candidates"][0]["status"], "needs-review")
        with self.assertRaises(ValueError):
            nc.approved_ids(result)

    def test_live_version_requires_review(self):
        c = client()
        c.search.return_value = {"items": [song(1, "Get Lucky (Live)")]}
        c.metadata.side_effect = lambda ids: {str(i): song(i, "Get Lucky (Live)") for i in ids}
        self.assertEqual(nc.resolve(c, ["Get Lucky - Daft Punk"])["candidates"][0]["status"], "needs-review")

    def test_preview_never_accesses_account_and_write_requires_both_gates(self):
        c = client()
        args = {"name": "x", "tracks": ["netease:1"]}
        self.assertTrue(nc.run_tool("nc_create_playlist", args, c)["dry_run"])
        c.account_id.assert_not_called()
        args.update(dry_run=False, confirm=True)
        with self.assertRaises(ValueError):
            nc.run_tool("nc_create_playlist", args, c)
        with patch.dict(os.environ, {"NETEASE_ENABLE_WRITES": "1"}):
            args["confirm"] = False
            with self.assertRaises(ValueError):
                nc.run_tool("nc_create_playlist", args, c)
        c.request.assert_not_called()

    def test_create_readback_order_and_cache_journal(self):
        c = client()
        c.request.return_value = {"code": 200, "id": 22}
        with tempfile.TemporaryDirectory() as tmp, patch.object(nc, "journal_path", return_value=Path(tmp) / "created.json"), patch.dict(os.environ, {"NETEASE_ENABLE_WRITES": "1"}):
            result = nc.run_tool("nc_create_playlist", {"name": "x", "tracks": ["netease:2", "netease:1"], "dry_run": False, "confirm": True}, c)
            self.assertEqual(nc.journal(), {"22": "9"})
        self.assertFalse(result["verified"])
        self.assertEqual(result["requested_ids"], ["2", "1"])
        self.assertEqual([x.args[0] for x in c.request.call_args_list], ["create", "tracks", "order"])

    def test_partial_write_no_rollback_or_retry(self):
        c = client()
        c.request.side_effect = [{"code": 200, "id": 22}, api.NeteaseError("failure")]
        with patch.object(nc, "record_created"), patch.dict(os.environ, {"NETEASE_ENABLE_WRITES": "1"}):
            result = nc.run_tool("nc_create_playlist", {"name": "x", "tracks": ["netease:1"], "dry_run": False, "confirm": True}, c)
        self.assertEqual(result["status"], "partial-or-unknown")
        self.assertEqual(result["playlist_id"], "22")
        self.assertEqual(c.request.call_count, 2)

    def test_foreign_owner_add_and_untracked_delete_blocked(self):
        c = client()
        c.playlist.return_value["creator_id"] = "10"
        with patch.dict(os.environ, {"NETEASE_ENABLE_WRITES": "1"}):
            with self.assertRaises(ValueError):
                nc.run_tool("nc_add_tracks", {"playlist": "22", "tracks": ["netease:1"], "dry_run": False, "confirm": True}, c)
            c.playlist.return_value["creator_id"] = "9"
            with patch.object(nc, "journal", return_value={}):
                with self.assertRaises(ValueError):
                    nc.run_tool("nc_delete_playlist", {"playlist": "22", "dry_run": False, "confirm": True}, c)
        c.request.assert_not_called()

    def test_no_feature_coverage_preserves_order_and_omits_cost(self):
        result = nc.run_tool("nc_optimize_order", {"playlist": "22"}, client())
        self.assertEqual(result["ordered_ids"], ["netease:1", "netease:2"])
        self.assertEqual(result["coverage"]["measured"], 0)
        self.assertEqual(result["unevaluated_pairs"], 1)
        self.assertNotIn("cost", result)

    def test_supplied_features_use_shared_rules_no_default_arc(self):
        features = [{"id": str(i), "source": "offline fixture", "tempo": 120+i, "key": i, "mode": 1, "energy": .5, "valence": .5, "loudness": -10} for i in (1, 2)]
        with patch.object(nc.core, "check_pair", wraps=nc.core.check_pair) as check, patch.object(nc.optimizer, "anneal", side_effect=lambda blocks, **kw: (blocks[0], 3)) as anneal:
            result = nc.run_tool("nc_optimize_order", {"playlist": "22", "features": features}, client())
        check.assert_called_once()
        self.assertTrue(result["optimized"])
        self.assertIsNone(anneal.call_args.kwargs["shape"])
        with self.assertRaises(ValueError):
            nc.audio([song(1)], [features[0], features[0]])

    def test_rank_score_is_not_playcount_and_uid_is_passed(self):
        c = client()
        c.request.return_value = {"weekData": [{"song": raw(1), "score": 100}]}
        result = nc.run_tool("nc_top_played", {"period": "week"}, c)
        self.assertIsNone(result["records"][0]["play_count"])
        self.assertEqual(result["records"][0]["ranking_score"], 100)
        self.assertEqual(c.request.call_args.args[1]["uid"], "9")

    def test_tags_keep_original_brief_and_sources_as_declarations(self):
        args = {"brief": "keep this brief", "tags": [{"label": "funk", "axis": "sonic"}, {"label": "recent", "axis": "context", "evidence": {"basis": "recent-listening", "call": "nc_recently_played", "ref": "limit=30"}}], "adjustments": ["more funk"]}
        result = nc.run_tool("nc_tag_directions", args, client())
        self.assertEqual(result["brief"], args["brief"])
        self.assertEqual(result["tags"][0]["emphasis"], "boost")
        self.assertEqual(result["tags"][1]["evidence"]["kind"], "structured")
        self.assertFalse(any("撑不住" in p for p in result["problems"]))

    def test_all_fourteen_current_tool_ports_present(self):
        import am_mcp_server
        self.assertTrue({t["name"].replace("am_", "nc_", 1) for t in am_mcp_server.TOOLS}.issubset({t["name"] for t in nc.TOOLS}))

    def test_rpc_schema_notifications_and_secret_errors(self):
        def call(name, args):
            return nc.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}})
        for name, args in (("nc_top_played", {"year": 2026}), ("nc_recently_played", {"kind": "added"}), ("nc_optimize_order", {"tracks": ["1"], "playlist": "22"})):
            self.assertIn("error", call(name, args))
        with patch.object(nc, "run_tool") as run:
            self.assertIsNone(nc.handle({"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "nc_status"}}))
            run.assert_not_called()
        with patch.object(nc, "run_tool", side_effect=api.NeteaseError("Cookie=SECRET")):
            result = call("nc_status", {})
        self.assertTrue(result["result"]["isError"])
        self.assertNotIn("SECRET", json.dumps(result))

    def test_stdio_smoke(self):
        requests = [{"jsonrpc": "2.0", "id": i, "method": method, "params": {}} for i, method in enumerate(("initialize", "tools/list", "prompts/list"), 1)]
        proc = subprocess.run([sys.executable, "-B", nc.__file__], input="\n".join(map(json.dumps, requests))+"\n", text=True, encoding="utf-8", capture_output=True, timeout=15)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(json.loads(proc.stdout.splitlines()[1])["result"]["tools"]), 20)

    def test_nonfinite_invalid_feature_numbers_rejected_before_network(self):
        f = {"id": "1", "source": "test", "tempo": 120, "key": 1, "mode": 1,
             "energy": .5, "valence": .5, "loudness": -10}
        for field, bad in (("key", True), ("mode", 3), ("tempo", 0), ("energy", 2), ("energy", float("nan"))):
            with patch.object(nc, "run_tool") as run:
                result = nc.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                    "name": "nc_analyze_flow", "arguments": {"playlist": "22", "features": [{**f, field: bad}]}}})
            self.assertIn("error", result)
            run.assert_not_called()

    def test_offline_tags_ignore_invalid_network_configuration(self):
        with patch.dict(os.environ, {"NETEASE_API_URL": "http://not-allowed.example"}):
            result = nc.run_tool("nc_tag_directions", {"brief": "funk", "tags": ["sonic:funk"]})
        self.assertEqual(result["tags"][0]["label"], "funk")

    def test_recent_events_batch_metadata_and_preserve_unavailable_song_id(self):
        c = client()
        c.request.return_value = {"data": {"list": [{"time": 1000, "data": {"id": 1}},
                                                    {"time": 2000, "data": {"id": 2}}]}}
        c.metadata.side_effect = None
        c.metadata.return_value = {"1": song(1)}
        result = nc.run_tool("nc_recently_played", {}, c)
        c.metadata.assert_called_once_with([1, 2])
        self.assertEqual(result["events"][1]["song_id"], "2")
        self.assertIsNone(result["events"][1]["song"])

    def test_blank_prompt_and_invalid_protocol_version(self):
        result = nc.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": []}})
        self.assertIn("error", result)
        result = nc.handle({"jsonrpc": "2.0", "id": 1, "method": "prompts/get", "params": {
            "name": "create_playlist_from_description", "arguments": {"description": "   "}}})
        self.assertIn("error", result)

    def test_delete_routes_match_upstream_contract_and_csrf_reaches_gateway(self):
        for gateway in ("", "http://localhost:3000"):
            c = api.NeteaseClient(cookie="MUSIC_U=FAKE; __csrf=FAKE-CSRF", gateway=gateway)
            response = Mock()
            response.read.return_value = b'{"code":200}'
            c.opener = MagicMock()
            c.opener.open.return_value.__enter__.return_value = response
            c.request("delete", {"ids": "22"})
            req = c.opener.open.call_args.args[0]
            data = api.urllib.parse.parse_qs(req.data.decode())
            if gateway:
                self.assertTrue(req.full_url.endswith("/playlist/delete"))
                self.assertEqual(data["id"], ["22"])
                self.assertIn("__csrf=FAKE-CSRF", data["cookie"][0])
            else:
                self.assertTrue(req.full_url.endswith("/api/playlist/remove"))
                self.assertEqual(json.loads(data["ids"][0]), [22])

    def test_packaging_guard_includes_unstaged_modules_but_not_tests_or_private_script(self):
        import test_guards
        with patch.object(test_guards.subprocess, "run", return_value=Mock(stdout="am_paths.py\nnetease_api.py\ntests/test_netease_port.py\nmake_day_playlist.py\n")) as run:
            self.assertEqual(test_guards._tracked_modules(), {"am_paths", "netease_api"})
        self.assertIn("--others", run.call_args.args[0])
        self.assertIn("--exclude-standard", run.call_args.args[0])

    def test_repeated_recording_coverage_counts_positions_not_unique_features(self):
        f = {"id": "1", "source": "test", "tempo": 120, "key": 1, "mode": 1,
             "energy": .5, "valence": .5, "loudness": -10}
        tracks, report = nc.audio([song(1), song(1)], [f])
        self.assertEqual(report["coverage"]["measured"], 2)
        self.assertEqual(report["coverage"]["unique_measurements"], 1)
        self.assertEqual(report["unevaluated_pairs"], 0)

    def test_duplicate_recordings_do_not_silently_disappear_on_write(self):
        preview = nc.resolve(client(), ["netease:1", "netease:01"])
        self.assertEqual(preview["candidates"][1]["duplicate_of_input_index"], 0)
        with self.assertRaises(ValueError):
            nc.approved_ids(preview)

    def test_blank_search_is_rejected_and_prompt_contains_steering_contract(self):
        result = nc.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "nc_search_songs", "arguments": {"term": "   "}}})
        self.assertIn("error", result)
        self.assertIn("nc_tag_directions", nc.INSTRUCTIONS)

    def test_status_list_append_and_recorded_delete_handlers(self):
        c = client()
        status = nc.run_tool("nc_status", {}, c)
        self.assertTrue(status["logged_in"])
        self.assertNotIn("FAKE", json.dumps(status))
        c.playlists_page.return_value = {"playlists": [{"id": "22"}], "complete": True}
        self.assertTrue(nc.run_tool("nc_list_playlists", {}, c)["complete"])
        with patch.dict(os.environ, {"NETEASE_ENABLE_WRITES": "1"}):
            before = c.playlist.return_value
            c.playlist.side_effect = [before, {**before, "tracks": before["tracks"] + [song(3)]}, before]
            appended = nc.run_tool("nc_add_tracks", {"playlist": "22", "tracks": ["netease:3"], "dry_run": False, "confirm": True}, c)
            self.assertTrue(appended["verified"])
            with patch.object(nc, "journal", return_value={"22": "9"}):
                deleted = nc.run_tool("nc_delete_playlist", {"playlist": "22", "dry_run": False, "confirm": True}, c)
        self.assertEqual(deleted["status"], "delete-accepted")
        self.assertEqual([x.args[0] for x in c.request.call_args_list], ["tracks", "delete"])

    def test_real_shared_optimizer_keeps_block_order(self):
        features = [{"id": str(i), "source": "offline measured fixture", "tempo": 110+i*3,
                     "key": i, "mode": 1, "energy": .5, "valence": .5, "loudness": -10} for i in range(1, 5)]
        result = nc.run_tool("nc_optimize_order", {"blocks": [["netease:1", "netease:2"],
                       ["netease:3", "netease:4"]], "features": features}, client())
        self.assertTrue(result["optimized"])
        self.assertEqual(set(result["ordered_ids"][:2]), {"netease:1", "netease:2"})
        self.assertEqual(set(result["ordered_ids"][2:]), {"netease:3", "netease:4"})
        self.assertIsNone(result["arc"])


if __name__ == "__main__":
    unittest.main()
