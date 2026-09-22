"""发布前硬化回归测试：分页、顺序、空响应与空歌单。"""

from __future__ import annotations

import contextlib
import io
import json
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


if __name__ == "__main__":
    unittest.main()
