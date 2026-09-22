"""发布前硬化回归测试：分页、顺序、空响应与空歌单。"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import am_mcp_server as mcp  # noqa: E402
import am_playlist as am  # noqa: E402
import playlist_audit as audit  # noqa: E402


class TestPagination(unittest.TestCase):
    def test_follows_next_and_strips_duplicate_v1(self):
        pages = [
            (200, json.dumps({"data": [{"id": "p.1"}],
                              "next": "/v1/me/library/playlists?offset=100&limit=100"})),
            (200, json.dumps({"data": [{"id": "p.2"}]})),
        ]
        with patch.object(am, "api", side_effect=pages) as api:
            got = am.paged_data("/me/library/playlists", dev="D", user="U")
        self.assertEqual([x["id"] for x in got], ["p.1", "p.2"])
        self.assertEqual(api.call_args_list[1].args[1],
                         "/me/library/playlists?offset=100&limit=100")
        self.assertIsNone(api.call_args_list[1].kwargs["query"])

    def test_result_limit_stops_without_fetching_another_page(self):
        body = json.dumps({"data": [{"id": "p.1"}, {"id": "p.2"}],
                           "next": "/v1/me/library/playlists?offset=2"})
        with patch.object(am, "api", return_value=(200, body)) as api:
            got = am.paged_data("/me/library/playlists", dev="D", user="U", limit=1)
        self.assertEqual([x["id"] for x in got], ["p.1"])
        api.assert_called_once()


class TestTrackInputOrder(unittest.TestCase):
    def test_failed_query_does_not_jump_over_a_pinned_id(self):
        args = SimpleNamespace(json=None, tracks="missed, 999999, found",
                               isrcs=False, storefront="us")
        with patch.object(am, "resolve_tracks", return_value=(["FOUND"], ["missed"])):
            with contextlib.redirect_stdout(io.StringIO()):
                got = am._gather_track_ids(args, "DEV")
        self.assertEqual(got, ["999999", "FOUND"])


class TestCreateEmptyResponse(unittest.TestCase):
    def test_recovers_created_playlist_after_empty_body(self):
        created = {"id": "p.new", "attributes": {"name": "new"}}
        with patch.object(am, "find_playlist", side_effect=[None, created]), \
                patch.object(am.time, "sleep"):
            got, waited = am.created_playlist_from_response(
                "", "new", "DEV", "USER", attempts=2, delay=0.25)
        self.assertEqual(got, created)
        self.assertEqual(waited, 0.25)

    def test_mcp_create_uses_empty_body_recovery(self):
        created = {"id": "p.new", "attributes": {"name": "new"}}
        patches = (
            patch.object(am, "load_config", return_value={}),
            patch.object(am, "get_developer_token", return_value="DEV"),
            patch.object(am, "get_user_token", return_value=None),
            patch.object(am, "resolve_storefront", return_value="us"),
            patch.object(am, "resolve_tracks", return_value=(["1"], [])),
            patch.object(am, "require_user", return_value="USER"),
            patch.object(am, "api", return_value=(201, "")),
            patch.object(am, "created_playlist_from_response", return_value=(created, 4.0)),
        )
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        text = mcp.t_create({"name": "new", "tracks": ["song"]})
        self.assertIn("p.new", text)
        self.assertIn("等待 4s", text)


class TestEmptyPlaylistAudit(unittest.TestCase):
    def test_empty_playlist_returns_a_report_instead_of_crashing(self):
        with patch.object(am, "load_config", return_value={}), \
                patch.object(am, "get_developer_token", return_value="DEV"), \
                patch.object(am, "require_user", return_value="USER"), \
                patch.object(am, "resolve_storefront", return_value="us"), \
                patch.object(am, "find_playlist", return_value={
                    "id": "p.empty", "attributes": {"name": "empty"}}), \
                patch.object(am, "playlist_tracks", return_value=[]):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = audit.audit("empty")
        self.assertEqual(rc, 0)
        self.assertIn("歌单是空的", buf.getvalue())
        self.assertIn("少于 15 首", buf.getvalue())


class TestDeleteFallback(unittest.TestCase):
    def test_http_error_on_amp_host_reaches_official_host_fallback(self):
        first = am.ApiError(503, "unavailable", "https://amp-api.example")
        args = SimpleNamespace(playlist="p.test", yes=True)
        with patch.object(am, "load_config", return_value={}), \
                patch.object(am, "get_developer_token", return_value="DEV"), \
                patch.object(am, "require_user", return_value="USER"), \
                patch.object(am, "find_playlist", return_value={
                    "id": "p.test", "attributes": {"name": "test"}}), \
                patch.object(am, "api", side_effect=[first, (204, "")]) as api:
            with contextlib.redirect_stdout(io.StringIO()):
                rc = am.cmd_delete(args)
        self.assertEqual(rc, 0)
        self.assertEqual(api.call_count, 2)


class TestMcpCompatibility(unittest.TestCase):
    def test_initialize_negotiates_known_and_unknown_protocol_versions(self):
        known = mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                            "params": {"protocolVersion": "2024-11-05"}})
        future = mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "initialize",
                             "params": {"protocolVersion": "2099-01-01"}})
        self.assertEqual(known["result"]["protocolVersion"], "2024-11-05")
        self.assertEqual(future["result"]["protocolVersion"], mcp.PROTOCOL_VERSION)
        self.assertIn("am_status", future["result"]["instructions"])

    def test_tools_expose_bilingual_descriptions_and_risk_annotations(self):
        tools = {tool["name"]: tool for tool in mcp.TOOLS}
        self.assertIn("中文", tools["am_status"]["description"])
        self.assertTrue(tools["am_status"]["annotations"]["readOnlyHint"])
        self.assertTrue(tools["am_delete_playlist"]["annotations"]["destructiveHint"])
        self.assertFalse(tools["am_delete_playlist"]["annotations"]["readOnlyHint"])

    def test_missing_required_tool_argument_is_a_json_rpc_error(self):
        response = mcp.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                               "params": {"name": "am_show_playlist", "arguments": {}}})
        self.assertEqual(response["error"]["code"], -32602)
        self.assertIn("playlist", response["error"]["message"])

    def test_non_object_request_is_rejected(self):
        response = mcp.handle([])
        self.assertEqual(response["error"]["code"], -32600)
        response = mcp.handle({"id": 8, "method": "ping"})
        self.assertEqual(response["error"]["code"], -32600)

    def test_tool_argument_types_ranges_and_unknown_fields_are_validated(self):
        cases = [
            ({"term": "x", "limit": 0}, "must be >= 1"),
            ({"term": "x", "limit": True}, "must be integer"),
            ({"term": "x", "types": "videos"}, "must be one of"),
            ({"term": "x", "surprise": 1}, "unknown argument"),
        ]
        for arguments, message in cases:
            response = mcp.handle({
                "jsonrpc": "2.0", "id": 4, "method": "tools/call",
                "params": {"name": "am_search_songs", "arguments": arguments},
            })
            self.assertEqual(response["error"]["code"], -32602)
            self.assertIn(message, response["error"]["message"])

    def test_stdio_emits_parse_error_then_valid_initialize_response(self):
        request = (
            "not-json\n"
            '{"jsonrpc":"2.0","id":9,"method":"initialize",'
            '"params":{"protocolVersion":"2025-11-25"}}\n'
        )
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent.parent / "am_mcp_server.py")],
            input=request, text=True, encoding="utf-8", capture_output=True, check=True,
            cwd=Path(__file__).resolve().parent.parent,
        )
        messages = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(messages[0]["error"]["code"], -32700)
        self.assertEqual(messages[1]["result"]["serverInfo"]["version"], "1.2.0")
        self.assertEqual(result.stderr, "")


class TestStableReleaseAssets(unittest.TestCase):
    ROOT = Path(__file__).resolve().parent.parent
    LOCALES = (
        "README.md", "README_ZH_CN.md", "README_ZH_TW.md", "README_JP.md",
        "README_KR.md", "README_ES.md", "README_PT_BR.md", "README_DE.md",
        "README_FR.md",
    )

    def test_every_locale_has_complete_operational_entry_points(self):
        for name in self.LOCALES:
            text = (self.ROOT / name).read_text(encoding="utf-8")
            for required in ("pip install", "am-playlist login", "am-mcp",
                             "docker build", "python -m unittest", "SETUP"):
                self.assertIn(required, text, f"{name} is missing {required}")

    def test_every_locale_links_to_every_other_locale(self):
        for name in self.LOCALES:
            text = (self.ROOT / name).read_text(encoding="utf-8")
            for target in self.LOCALES:
                if target != name:
                    self.assertIn(target, text, f"{name} does not link to {target}")

    def test_container_runs_as_non_root_and_excludes_secrets(self):
        dockerfile = (self.ROOT / "Dockerfile").read_text(encoding="utf-8")
        ignore = (self.ROOT / ".dockerignore").read_text(encoding="utf-8")
        self.assertIn("USER app", dockerfile)
        self.assertIn("ENTRYPOINT", dockerfile)
        for secret in ("config.json", "*.p8", ".env"):
            self.assertIn(secret, ignore)

    def test_client_guide_covers_supported_surfaces_and_harness_boundary(self):
        text = (self.ROOT / "docs" / "client-setup.md").read_text(encoding="utf-8")
        for client in ("Codex", "Claude", "Cursor", "VS Code", "Gemini CLI",
                       "Windsurf", "Cordis", "Harness Platform", "Docker"):
            self.assertIn(client, text)
        self.assertIn("require a network URL and API key", text)


if __name__ == "__main__":
    unittest.main()
