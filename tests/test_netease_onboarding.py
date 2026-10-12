"""Conversation-first onboarding contracts. Synthetic sessions/processes only."""
import contextlib
import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import am_paths
import netease_api as api
import netease_mcp_server as nc
import netease_onboarding as onboarding
import netease_session as sessions


def call(name, arguments):
    return nc.handle({"jsonrpc":"2.0", "id":1, "method":"tools/call",
                      "params":{"name":name,"arguments":arguments}})["result"]


class ConversationalOnboardingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        for patcher in (patch.dict(os.environ, {"NETEASE_LOGIN_BUNDLE":"", "NETEASE_ENABLE_WRITES":"0"}),
                        patch.object(onboarding, "supports_managed_login", return_value=True),
                        patch.object(sessions, "describe", return_value={"saved":False})):
            patcher.start()
            self.addCleanup(patcher.stop)

    def bundle(self, *, code="pass\n"):
        helper = self.folder / "bootstrap.py"
        helper.write_text(code, encoding="utf-8")
        body = {"version":am_paths.VERSION,"qr":{"platform":"win-x64",
                "bootstrap_sha256":hashlib.sha256(helper.read_bytes()).hexdigest()}}
        (self.folder / "bundle.json").write_text(json.dumps(body), encoding="utf-8")
        os.environ["NETEASE_LOGIN_BUNDLE"] = str(self.folder)
        return body

    def test_setup_is_offline_and_saved_session_not_reported_as_logged_in(self):
        self.bundle()
        with patch.object(nc, "NeteaseClient") as client, patch.object(onboarding.subprocess, "Popen") as spawn, patch.object(sessions, "describe", return_value={"saved":True}):
            result = call("nc_setup", {})
        client.assert_not_called()
        spawn.assert_not_called()
        data = result["structuredContent"]
        self.assertTrue(data["local_session_present"])
        self.assertIsNone(data["login_verified"])
        self.assertTrue(data["managed_qr_available"])
        self.assertIn("next_actions", json.loads(result["content"][0]["text"].split(": ",1)[1]))
        self.assertIn("no standalone application", data["interface"])

    def test_initialization_does_not_load_sessions_start_login_or_open_browser(self):
        with patch.object(nc, "NeteaseClient") as client, patch.object(sessions, "load") as load, patch.object(onboarding.subprocess, "Popen") as spawn:
            result = nc.handle({"jsonrpc":"2.0","id":1,"method":"initialize"})["result"]
        client.assert_not_called()
        load.assert_not_called()
        spawn.assert_not_called()
        self.assertIn("host conversation", result["instructions"])
        self.assertIn("explicit user approval", result["instructions"])

    def test_login_requires_consent_and_does_not_accept_secrets_or_qr_in_arguments(self):
        manager = onboarding.LoginHandoff()
        with patch.object(onboarding, "LOGIN", manager), patch.object(nc, "NeteaseClient") as client, patch.object(onboarding.subprocess, "Popen") as spawn:
            data = call("nc_login", {"action":"start"})["structuredContent"]
            self.assertEqual(data["status"], "approval-required")
            invalid = nc.handle({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{
                "name":"nc_login","arguments":{"action":"start","confirm":True,"cookie":"SYNTHETIC-SECRET"}}})
            self.assertIn("error", invalid)
        client.assert_not_called()
        spawn.assert_not_called()

    def test_missing_corrupt_wrong_version_helper_never_executes(self):
        manager = onboarding.LoginHandoff()
        with patch.object(onboarding.subprocess, "Popen") as spawn:
            self.assertEqual(manager.start(confirm=True)["status"], "setup-required")
            body = self.bundle()
            (self.folder / "bootstrap.py").write_text("# changed", encoding="utf-8")
            self.assertEqual(manager.start(confirm=True)["status"], "setup-required")
            (self.folder / "bundle.json").write_text("[]", encoding="utf-8")
            self.assertEqual(onboarding.setup_facts()["login_bundle"], "missing-or-invalid")
        spawn.assert_not_called()

    def test_only_local_helper_opens_after_approval_and_output_is_discarded(self):
        self.bundle()
        process = Mock()
        process.poll.return_value = None
        manager = onboarding.LoginHandoff()
        with patch.dict(os.environ,{"NETEASE_COOKIE":"SYNTHETIC-SECRET","NODE_OPTIONS":"unsafe"}), patch.object(onboarding.subprocess,"Popen",return_value=process) as spawn:
            result = manager.start(confirm=True)
        self.assertEqual(result["status"], "pending")
        self.assertFalse(result["login_verified"])
        self.assertFalse(result["helper_stopped"])
        args = spawn.call_args.args[0]
        self.assertEqual(args[1], "-I")
        self.assertEqual(args[-1], "qr-chat")
        self.assertEqual(spawn.call_args.kwargs["stdout"], subprocess.DEVNULL)
        self.assertEqual(spawn.call_args.kwargs["stderr"], subprocess.DEVNULL)
        self.assertEqual(spawn.call_args.kwargs["env"]["NETEASE_COOKIE"], "")
        self.assertNotIn("NODE_OPTIONS", spawn.call_args.kwargs["env"])
        self.assertNotIn("SYNTHETIC-SECRET", json.dumps(result))
        self.assertNotIn("qrimg", result)
        self.assertNotIn("qrurl", result)

    def test_repeated_start_reuses_job_even_after_success_until_explicit_restart(self):
        self.bundle()
        process = Mock()
        process.poll.return_value = None
        manager = onboarding.LoginHandoff()
        with patch.object(onboarding.subprocess,"Popen",return_value=process) as spawn:
            first = manager.start(confirm=True)
            again = manager.start(confirm=True,restart=True)
            self.assertEqual(again["job_id"],first["job_id"])
            process.poll.return_value = 0
            success = manager.start(confirm=True)
            self.assertEqual(success["status"],"verified")
            self.assertEqual(spawn.call_count,1)
            manager.start(confirm=True,restart=True)
            self.assertEqual(spawn.call_count,2)

    def test_pending_failure_unknown_and_cancel_not_silently_called_success(self):
        manager = onboarding.LoginHandoff()
        self.assertEqual(manager.status()["status"], "not-started")
        manager.job_id = "synthetic-job"
        manager.process = Mock(stdin=io.StringIO())
        manager.process.poll.return_value = None
        self.assertEqual(manager.status("foreign")["status"], "unknown-job")
        manager.cancel("foreign")
        self.assertEqual(manager.process.stdin.getvalue(), "")
        self.assertEqual(manager.cancel()["status"], "cancelling")
        self.assertEqual(manager.process.stdin.getvalue(), "CANCEL\n")
        manager.process.poll.return_value = 0
        self.assertEqual(manager.status()["status"], "cancelled")
        self.assertFalse(manager.status()["login_verified"])
        manager.cancel_requested = False
        manager.process.poll.return_value = 1
        self.assertEqual(manager.status()["status"], "not-completed")
        self.assertIn("nc_status", manager.status()["next_action"])

    def test_actual_synthetic_helper_cancel_and_parent_cleanup_never_access_account(self):
        self.bundle(code="import sys\nprint('SYNTHETIC-AUTH-OUTPUT')\nsys.stdout.flush()\nsys.stdin.readline()\nsys.exit(1)\n")
        manager = onboarding.LoginHandoff()
        try:
            start = manager.start(confirm=True)
            self.assertEqual(start["status"], "pending")
            manager.close()
            final = manager.status()
            self.assertEqual(final["status"], "cancelled")
            self.assertTrue(final["helper_stopped"])
            self.assertNotIn("SYNTHETIC-AUTH-OUTPUT", json.dumps(final))
        finally:
            manager.close()

    def test_network_failure_guides_network_check_not_repeated_login(self):
        client = Mock(cookie="SYNTHETIC-SECRET", gateway="", session_source="local-store", csrf="")
        client.account_id.side_effect = api.NeteaseError("SYNTHETIC-SECRET",kind="network")
        result = nc.run_tool("nc_status",{},client)
        self.assertEqual(result["onboarding"]["stage"], "verification-unavailable")
        self.assertIn("connectivity", result["onboarding"]["next_action"])
        self.assertNotIn("SYNTHETIC-SECRET", json.dumps(result))
        client.account_id.side_effect = api.NeteaseError("expired",kind="login-expired")
        self.assertEqual(nc.run_tool("nc_status",{},client)["onboarding"]["stage"],"login-needed")
        client.account_id.side_effect = None
        client.account_id.return_value = "1"
        ready = nc.run_tool("nc_status",{},client)["onboarding"]
        self.assertEqual(ready["stage"],"ready-for-preview")
        self.assertIn("Readonly",ready["writes"])

    def test_getting_started_prompt_optional_menu_and_annotation_contract(self):
        req = {"jsonrpc":"2.0","id":1,"method":"prompts/get","params":{"name":"getting_started"}}
        text = nc.handle(req)["result"]["messages"][0]["content"]["text"]
        self.assertIn("in conversation",text)
        self.assertIn("never modify playlists",text)
        req["params"]["arguments"] = {"cookie":"synthetic"}
        self.assertIn("error",nc.handle(req))
        tools = {tool["name"]:tool for tool in nc.TOOLS}
        self.assertTrue(tools["nc_setup"]["annotations"]["readOnlyHint"])
        self.assertFalse(tools["nc_login"]["annotations"]["readOnlyHint"])
        self.assertNotIn("cookie",tools["nc_login"]["inputSchema"]["properties"])

    def test_server_eof_always_signals_owned_login_shutdown(self):
        with patch.object(nc.sys,"stdin",io.StringIO("")), patch.object(onboarding.LOGIN,"close") as close:
            self.assertEqual(nc.main(),0)
        close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
