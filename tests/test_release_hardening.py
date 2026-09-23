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
from unittest.mock import Mock, patch

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
        self.assertIn("prompts", future["result"]["capabilities"])

    def test_playlist_prompt_is_listed_with_required_description(self):
        response = mcp.handle({"jsonrpc": "2.0", "id": 10, "method": "prompts/list"})
        prompts = response["result"]["prompts"]
        self.assertEqual([item["name"] for item in prompts],
                         ["create_playlist_from_description"])
        arguments = {item["name"]: item for item in prompts[0]["arguments"]}
        self.assertTrue(arguments["description"]["required"])
        self.assertIn("track_count", arguments)

    def test_playlist_prompt_renders_an_actionable_tool_workflow(self):
        response = mcp.handle({
            "jsonrpc": "2.0", "id": 11, "method": "prompts/get",
            "params": {
                "name": "create_playlist_from_description",
                "arguments": {
                    "description": "雨夜开车，华语独立音乐，不要现场版",
                    "name": "雨幕公路",
                    "track_count": "18",
                    "language": "简体中文",
                },
            },
        })
        text = response["result"]["messages"][0]["content"]["text"]
        self.assertIn("雨夜开车", text)
        self.assertIn("雨幕公路", text)
        self.assertIn("18 tracks", text)
        for tool in ("am_status", "am_resolve_candidates", "am_create_playlist"):
            self.assertIn(tool, text)
        self.assertIn("Do not turn theme fit into arbitrary 0–1 scores", text)
        self.assertIn("has_lyrics=false as unknown", text)
        self.assertIn("dry_run=true", text)

    def test_playlist_prompt_rejects_invalid_arguments(self):
        cases = [
            ({"name": "create_playlist_from_description", "arguments": {}},
             "missing required"),
            ({"name": "create_playlist_from_description",
              "arguments": {"description": " "}}, "must not be empty"),
            ({"name": "create_playlist_from_description",
              "arguments": {"description": "focus", "track_count": 20}}, "must be string"),
            ({"name": "missing", "arguments": {"description": "focus"}}, "unknown prompt"),
            ({"name": "create_playlist_from_description",
              "arguments": {"description": "bad-\udc8e"}}, "valid Unicode"),
        ]
        for params, message in cases:
            response = mcp.handle({"jsonrpc": "2.0", "id": 12,
                                   "method": "prompts/get", "params": params})
            self.assertEqual(response["error"]["code"], -32602)
            self.assertIn(message, response["error"]["message"])

    def test_tools_expose_bilingual_descriptions_and_risk_annotations(self):
        tools = {tool["name"]: tool for tool in mcp.TOOLS}
        self.assertEqual(len(tools), len(mcp.TOOLS))
        self.assertTrue(all(tool.get("title") for tool in tools.values()))
        self.assertEqual(len({tool["title"] for tool in tools.values()}), len(tools))
        self.assertIn("中文", tools["am_status"]["description"])
        self.assertIn("use am_resolve_candidates instead", tools["am_search_songs"]["description"])
        self.assertIn("never scores theme fit", tools["am_resolve_candidates"]["description"])
        self.assertIn("use am_analyze_flow", tools["am_audit_playlist"]["description"])
        self.assertIn("must not choose songs", tools["am_optimize_order"]["description"])
        self.assertIn("does not provide play counts", tools["am_recently_played"]["description"])
        self.assertTrue(tools["am_status"]["annotations"]["readOnlyHint"])
        self.assertTrue(tools["am_delete_playlist"]["annotations"]["destructiveHint"])
        self.assertFalse(tools["am_delete_playlist"]["annotations"]["readOnlyHint"])

    def test_candidate_resolver_grounds_metadata_without_scoring(self):
        metadata = {
            "101": {
                "name": "Midnight Road",
                "artistName": "Night Driver",
                "albumName": "Streetlights",
                "releaseDate": "2024-05-01",
                "genreNames": ["Electronic"],
                "durationInMillis": 201234,
                "hasLyrics": False,
                "isrc": "USAAA2400001",
                "url": "https://music.apple.com/us/song/midnight-road/101",
            },
            "202": {
                "name": "City Glow (Live)",
                "artistName": "Night Driver",
                "albumName": "On Stage",
                "releaseDate": "2023-10-02",
                "genreNames": ["Alternative"],
                "durationInMillis": 180000,
                "hasLyrics": True,
                "isrc": "USAAA2300002",
            },
            "303": {
                "name": "Dawn",
                "artistName": "Night Driver",
                "albumName": "First Light",
                "releaseDate": "2025-01-01",
                "genreNames": ["Ambient"],
                "durationInMillis": 240000,
                "isrc": "USAAA2500003",
            },
        }
        resolutions = [(["101"], []), (["101"], []), ([], ["Missing"]),
                       (["202"], []), (["303"], [])]
        with patch.object(am, "load_config", return_value={}), \
                patch.object(am, "get_developer_token", return_value="DEV"), \
                patch.object(am, "get_user_token", return_value=None), \
                patch.object(am, "resolve_storefront", return_value="us"), \
                patch.object(am, "resolve_tracks", side_effect=resolutions), \
                patch.object(mcp, "catalog_meta", return_value=metadata):
            payload = json.loads(mcp.t_resolve_candidates({
                "tracks": ["Midnight Road - Night Driver", "Midnight Road duplicate",
                           "Missing", "City Glow - Night Driver", "Dawn - Night Driver"]
            }))

        self.assertEqual(payload["summary"]["input_count"], 5)
        self.assertEqual(payload["summary"]["resolved_count"], 4)
        self.assertEqual(payload["summary"]["unmatched_count"], 1)
        self.assertEqual(payload["summary"]["duplicate_recordings"], 1)
        self.assertEqual([row["input_index"] for row in payload["candidates"]],
                         [0, 1, 2, 3, 4])
        self.assertEqual(payload["candidates"][1]["duplicate_of_input_index"], 0)
        self.assertEqual(payload["candidates"][2]["status"], "unmatched")
        self.assertEqual(payload["candidates"][0]["apple_music_url"],
                         "https://music.apple.com/us/song/midnight-road/101")
        self.assertIsNone(payload["candidates"][3]["apple_music_url"])
        self.assertFalse(payload["candidates"][0]["has_lyrics"])
        self.assertIsNone(payload["candidates"][4]["has_lyrics"])
        self.assertIn("live", payload["candidates"][3]["version_markers"])
        self.assertIn("unrequested-suffix", payload["candidates"][3]["version_markers"])
        self.assertEqual(payload["summary"]["artists_over_two_tracks"],
                         [{"artist": "Night Driver", "count": 3}])
        self.assertFalse(any("score" in key.lower()
                             for row in payload["candidates"]
                             for key in row))

    def test_candidate_resolver_schema_rejects_oversized_or_blank_pools(self):
        cases = [
            ({"tracks": ["song"] * 61}, "at most 60"),
            ({"tracks": ["   "]}, "must not be empty"),
        ]
        for arguments, message in cases:
            response = mcp.handle({
                "jsonrpc": "2.0", "id": 13, "method": "tools/call",
                "params": {"name": "am_resolve_candidates", "arguments": arguments},
            })
            self.assertEqual(response["error"]["code"], -32602)
            self.assertIn(message, response["error"]["message"])

    def test_missing_required_tool_argument_is_a_json_rpc_error(self):
        response = mcp.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                               "params": {"name": "am_show_playlist", "arguments": {}}})
        self.assertEqual(response["error"]["code"], -32602)
        self.assertIn("playlist", response["error"]["message"])

    def test_lone_surrogate_is_rejected_before_a_write_handler_runs(self):
        create = Mock()
        with patch.dict(mcp.HANDLERS, {"am_create_playlist": create}):
            response = mcp.handle({
                "jsonrpc": "2.0", "id": 14, "method": "tools/call",
                "params": {"name": "am_create_playlist", "arguments": {
                    "name": "bad-\udc8e", "tracks": ["Song - Artist"],
                }},
            })
        self.assertEqual(response["error"]["code"], -32602)
        self.assertIn("valid Unicode", response["error"]["message"])
        create.assert_not_called()

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
        self.assertEqual(
            messages[1]["result"]["serverInfo"]["version"],
            mcp.SERVER_INFO["version"],
        )
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
                             "docker build", "python -m unittest", "SETUP",
                             "create_playlist_from_description",
                             "uvx --from apple-music-playlists am-mcp"):
                self.assertIn(required, text, f"{name} is missing {required}")
            self.assertRegex(
                text,
                r'"args"\s*:\s*\[\s*"--from"\s*,\s*"apple-music-playlists"\s*,\s*"am-mcp"\s*\]',
                f"{name} is missing the uvx MCP arguments",
            )
            self.assertIn("pip install apple-music-playlists", text)
            self.assertNotIn("git+https://github.com/Z-Han-Z/apple-music-playlists", text)

    def test_every_locale_links_to_every_other_locale(self):
        for name in self.LOCALES:
            text = (self.ROOT / name).read_text(encoding="utf-8")
            for target in self.LOCALES:
                if target != name:
                    self.assertIn(target, text, f"{name} does not link to {target}")

    def test_every_locale_uses_the_shared_social_preview(self):
        preview = self.ROOT / ".github" / "assets" / "social-preview.jpg"
        self.assertTrue(preview.is_file())
        self.assertLess(preview.stat().st_size, 1_000_000)
        for name in self.LOCALES:
            text = (self.ROOT / name).read_text(encoding="utf-8")
            self.assertIn(".github/assets/social-preview.jpg", text,
                          f"{name} does not show the shared project banner")

    def test_container_runs_as_non_root_and_excludes_secrets(self):
        dockerfile = (self.ROOT / "Dockerfile").read_text(encoding="utf-8")
        ignore = (self.ROOT / ".dockerignore").read_text(encoding="utf-8")
        self.assertIn("USER app", dockerfile)
        self.assertIn("ENTRYPOINT", dockerfile)
        for secret in ("config.json", "*.p8", ".env"):
            self.assertIn(secret, ignore)

    def test_client_guide_covers_supported_surfaces_and_harness_boundary(self):
        text = (self.ROOT / "docs" / "client-setup.md").read_text(encoding="utf-8")
        zh_text = (self.ROOT / "docs" / "client-setup.zh-CN.md").read_text(
            encoding="utf-8")
        for client in ("Codex", "Claude", "Cursor", "VS Code", "Gemini CLI",
                       "Windsurf", "Cordis", "Harness Platform", "Docker"):
            self.assertIn(client, text)
        self.assertIn("require a network URL and API key", text)
        for guide in (text, zh_text):
            self.assertIn("uvx", guide)
            self.assertIn('"--from", "apple-music-playlists", "am-mcp"', guide)

    def test_pypi_publishing_is_manual_oidc_and_registry_ready(self):
        readme = (self.ROOT / "README.md").read_text(encoding="utf-8")
        workflow = (self.ROOT / ".github" / "workflows" / "publish-pypi.yml").read_text(
            encoding="utf-8")
        registry_workflow = (
            self.ROOT / ".github" / "workflows" / "publish-mcp-registry.yml"
        ).read_text(encoding="utf-8")
        guide = (self.ROOT / "docs" / "publishing.md").read_text(encoding="utf-8")
        manifest = json.loads((self.ROOT / "server.json").read_text(encoding="utf-8"))

        registry_name = "io.github.Z-Han-Z/apple-music-playlists"
        self.assertIn(f"mcp-name: {registry_name}", readme)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("ref: refs/tags/v${{ inputs.version }}", workflow)
        self.assertIn("without a leading 'v'", workflow)
        self.assertIn('sys.path.insert(0, os.environ["GITHUB_WORKSPACE"])', workflow)
        self.assertNotIn("release:", workflow)
        self.assertNotIn("pull_request_target:", workflow)
        self.assertIn("name: pypi", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn("pypa/gh-action-pypi-publish@release/v1", workflow)
        self.assertNotIn("secrets.", workflow)
        self.assertIn("do not publish that metadata until", guide)
        self.assertIn(registry_name, guide)

        self.assertEqual(manifest["name"], registry_name)
        self.assertEqual(manifest["version"], mcp.SERVER_INFO["version"])
        self.assertEqual(manifest["packages"][0]["version"], mcp.SERVER_INFO["version"])
        self.assertEqual(manifest["packages"][0]["registryType"], "pypi")
        self.assertEqual(manifest["packages"][0]["identifier"], "apple-music-playlists")
        self.assertEqual(manifest["packages"][0]["runtimeHint"], "uvx")
        self.assertEqual(manifest["packages"][0]["packageArguments"][0]["value"], "am-mcp")
        self.assertEqual(manifest["packages"][0]["transport"]["type"], "stdio")

        self.assertIn("workflow_dispatch:", registry_workflow)
        self.assertIn("ref: refs/tags/v${{ inputs.version }}", registry_workflow)
        self.assertIn("name: mcp-registry", registry_workflow)
        self.assertIn("id-token: write", registry_workflow)
        self.assertIn("login github-oidc", registry_workflow)
        self.assertIn("publish server.json", registry_workflow)
        self.assertIn("MCP_PUBLISHER_VERSION: \"1.8.1\"", registry_workflow)
        self.assertIn(
            "a06c9096dcb9727c13555b6be26c7effa707b01f06a4c561ba7a3635443cf2cc",
            registry_workflow,
        )
        self.assertNotIn("secrets.", registry_workflow)
        self.assertNotIn("pull_request_target:", registry_workflow)

    def test_english_readme_coverage_example_is_english(self):
        readme = (self.ROOT / "README.md").read_text(encoding="utf-8")
        section = readme.split("**Coverage is reported, never silently dropped.**", 1)[1]
        example = section.split("That distinction is the point.", 1)[0]
        self.assertIn("Audio-feature coverage:", example)
        self.assertIn("tracks have no ISRC", example)
        self.assertIn("tracks are not in the current source", example)
        self.assertNotRegex(example, r"[\u4e00-\u9fff]")

    def test_ci_reads_the_single_version_source(self):
        workflows = (
            self.ROOT / ".github" / "workflows" / "test.yml",
            self.ROOT / ".github" / "workflows" / "container.yml",
        )
        for path in workflows:
            text = path.read_text(encoding="utf-8")
            self.assertIn("from am_paths import VERSION", text)
            self.assertNotIn(
                f'"version": "{mcp.SERVER_INFO["version"]}"',
                text,
                f"{path.name} must not hardcode the current release version",
            )

    def test_package_metadata_uses_curator_positioning(self):
        metadata = (self.ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('"semantic-curation"', metadata)
        self.assertIn('"narrative-playlists"', metadata)
        self.assertNotIn('"playlist-generator"', metadata)


class TestCommunityHealth(unittest.TestCase):
    ROOT = Path(__file__).resolve().parent.parent

    def test_community_health_files_are_present_and_actionable(self):
        required = (
            "README.md", "LICENSE", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md",
            "SUPPORT.md", "SECURITY.md", ".github/pull_request_template.md",
        )
        for name in required:
            path = self.ROOT / name
            self.assertTrue(path.is_file(), f"missing community health file: {name}")
            self.assertTrue(path.read_text(encoding="utf-8").strip(),
                            f"empty community health file: {name}")

        conduct = (self.ROOT / "CODE_OF_CONDUCT.md").read_text(encoding="utf-8")
        self.assertIn("Contributor Covenant", conduct)
        self.assertIn("security/advisories/new", conduct)
        self.assertNotIn("INSERT CONTACT METHOD", conduct)

    def test_issue_forms_have_github_required_fields(self):
        forms = self.ROOT / ".github" / "ISSUE_TEMPLATE"
        for name in ("bug_report.yml", "feature_request.yml", "question.yml"):
            text = (forms / name).read_text(encoding="utf-8")
            for key in ("name:", "description:", "body:"):
                self.assertIn(key, text, f"{name} is missing {key}")


if __name__ == "__main__":
    unittest.main()
