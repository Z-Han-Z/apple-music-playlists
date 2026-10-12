"""Offline beta handoff regressions; no credentials, live account writes or GUI launches."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

import am_paths
import netease_login

ROOT = Path(__file__).resolve().parent.parent


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bootstrap = load_file("beta_bootstrap", ROOT / "beta" / "bootstrap.py")
builder = load_file("beta_bundle_builder", ROOT / "scripts" / "build_beta_bundle.py")


class BetaDistributionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        for target, attribute, value in ((bootstrap, "BUNDLE_DIR", self.folder / "bundle"),
                                         (bootstrap, "user_dir", lambda kind: self.folder / kind)):
            p = patch.object(target, attribute, value)
            p.start()
            self.addCleanup(p.stop)
        bootstrap.BUNDLE_DIR.mkdir()
        self.version = am_paths.VERSION

    def manifest_fixture(self):
        wheel = bootstrap.BUNDLE_DIR / "wheel" / f"apple_music_playlists-{self.version}-py3-none-any.whl"
        wheel.parent.mkdir()
        wheel.write_bytes(b"synthetic wheel fixture, not executable")
        body = {"version": self.version, "wheel": wheel.name,
                "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(), "tool_count": 20}
        bootstrap.write_json(bootstrap.BUNDLE_DIR / "bundle.json", body)
        return body, wheel

    def runtime_fixture(self):
        runtime = bootstrap.runtime_base(self.version) / ("a" * 32)
        runtime.mkdir(parents=True)
        bootstrap.write_json(runtime / ".netease-beta-runtime.json", {"version": self.version, "kind": "netease-beta-runtime"})
        python = bootstrap.python_path(runtime)
        python.parent.mkdir()
        python.write_bytes(b"synthetic executable placeholder")
        bootstrap.write_json(bootstrap.state_path(self.version), {"version": self.version, "runtime": str(runtime)})
        return runtime

    def test_manifest_rejects_path_traversal_wrong_wheel_or_hash(self):
        body, wheel = self.manifest_fixture()
        self.assertEqual(bootstrap.manifest(), body)
        for changes in ({"version": "../../escape"}, {"wheel": "../other.whl"},
                        {"sha256": "secret"}, {"tool_count": True}):
            bootstrap.write_json(bootstrap.BUNDLE_DIR / "bundle.json", {**body, **changes})
            with self.assertRaises(bootstrap.SetupError):
                bootstrap.manifest()

    def test_install_rejects_tampered_wheel_before_venv_or_subprocess(self):
        body, wheel = self.manifest_fixture()
        wheel.write_bytes(b"changed fixture")
        with patch.object(bootstrap.venv, "EnvBuilder") as make, patch.object(bootstrap.subprocess, "run") as run:
            with self.assertRaises(bootstrap.SetupError):
                bootstrap.install(body)
            make.assert_not_called()
            run.assert_not_called()

    def test_install_offline_private_runtime_and_default_readonly_config(self):
        body, wheel = self.manifest_fixture()
        with patch.object(bootstrap.venv, "EnvBuilder") as make, patch.object(bootstrap.subprocess, "run", return_value=Mock(returncode=0)) as run, patch.object(bootstrap, "probe") as probe, contextlib.redirect_stdout(io.StringIO()):
            make.return_value.create.side_effect = lambda path: path.mkdir(parents=True)
            runtime = bootstrap.install(body)
        self.assertEqual(runtime.parent, bootstrap.runtime_base(self.version))
        make.assert_called_once_with(with_pip=True)
        arguments = run.call_args.args[0]
        self.assertIn("--no-index", arguments)
        self.assertIn("--no-deps", arguments)
        self.assertEqual(arguments[-1], str(wheel))
        probe.assert_called_once_with(runtime, body)
        state = json.loads(bootstrap.state_path(self.version).read_text(encoding="utf-8"))
        self.assertEqual(state["runtime"], str(runtime.resolve()))
        config = json.loads((runtime / "client-config" / "mcp-config.json").read_text(encoding="utf-8"))
        service = config["mcpServers"]["netease-curator-beta"]
        self.assertEqual(service["env"]["NETEASE_ENABLE_WRITES"], "0")
        self.assertEqual(service["env"]["NETEASE_COOKIE"], "")
        self.assertEqual(service["args"], ["-I", "-m", "netease_mcp_server"])
        self.assertTrue(Path(service["command"]).is_absolute())

    def test_failed_install_never_commits_default_runtime_pointer(self):
        body, wheel = self.manifest_fixture()
        with patch.object(bootstrap.venv, "EnvBuilder") as make, patch.object(bootstrap.subprocess, "run", return_value=Mock(returncode=1)), contextlib.redirect_stdout(io.StringIO()):
            make.return_value.create.side_effect = lambda path: path.mkdir(parents=True)
            with self.assertRaises(bootstrap.SetupError):
                bootstrap.install(body)
        self.assertFalse(bootstrap.state_path(self.version).exists())

    def test_runtime_rejects_broad_foreign_or_markerless_targets(self):
        runtime = self.runtime_fixture()
        self.assertEqual(bootstrap.installed(self.version), runtime.resolve())
        for path in (self.folder, runtime.parent, self.folder / ("b" * 32)):
            with self.assertRaises(bootstrap.SetupError):
                bootstrap.check_runtime(path, self.version)
        bootstrap.write_json(runtime / ".netease-beta-runtime.json", {"version": "different", "kind": "netease-beta-runtime"})
        with self.assertRaises(bootstrap.SetupError):
            bootstrap.check_runtime(runtime, self.version)

    def test_probe_only_initializes_and_lists_without_account_access(self):
        runtime = self.runtime_fixture()
        body = {"version": self.version, "tool_count": 20}
        stdout = '\n'.join(map(json.dumps, [{"result": {"serverInfo": {"version": self.version}}}, {"result": {"tools": [{}] * 20}}]))
        with patch.dict(os.environ, {"NETEASE_COOKIE": "SECRET", "NETEASE_ENABLE_WRITES": "1"}), patch.object(bootstrap.subprocess, "run", return_value=Mock(returncode=0, stdout=stdout)) as run:
            bootstrap.probe(runtime, body)
        requests = [json.loads(line) for line in run.call_args.kwargs["input"].splitlines()]
        self.assertEqual([r["method"] for r in requests], ["initialize", "tools/list"])
        self.assertEqual(run.call_args.kwargs["env"]["NETEASE_COOKIE"], "")
        self.assertEqual(run.call_args.kwargs["env"]["NETEASE_ENABLE_WRITES"], "0")

    def test_login_handoff_never_puts_cookie_in_args(self):
        runtime = self.runtime_fixture()
        with patch.dict(os.environ, {"NETEASE_COOKIE": "SECRET"}), patch.object(bootstrap.subprocess, "run", return_value=Mock(returncode=0)) as run, contextlib.redirect_stdout(io.StringIO()):
            bootstrap.launch_login(runtime, "import")
        self.assertEqual(run.call_args.args[0][-2:], ["import", "--save"])
        self.assertNotIn("SECRET", repr(run.call_args))

    def test_qr_requires_loopback_and_only_explicit_action_opens(self):
        runtime = self.runtime_fixture()
        with patch("builtins.input", return_value="http://127.0.0.1:3000"), patch.object(bootstrap.subprocess, "run", return_value=Mock(returncode=0)) as run, contextlib.redirect_stdout(io.StringIO()):
            bootstrap.launch_login(runtime, "qr-external")
        self.assertEqual(run.call_args.args[0][-3:], ["qr", "--save", "--open"])
        self.assertEqual(run.call_args.kwargs["env"]["NETEASE_API_URL"], "http://127.0.0.1:3000")
        for gateway in ("https://public.example", "http://localhost@public.example", "http://localhost/path", "http://localhost/?cookie=secret"):
            with self.assertRaises(bootstrap.SetupError):
                bootstrap.local_gateway(gateway)

    def test_forget_and_uninstall_require_distinct_explicit_confirmation(self):
        runtime = self.runtime_fixture()
        with patch("builtins.input", return_value="no"), patch.object(bootstrap.subprocess, "run") as run, patch.object(bootstrap.shutil, "rmtree") as remove, contextlib.redirect_stdout(io.StringIO()):
            bootstrap.launch_login(runtime, "forget")
            bootstrap.uninstall(runtime, self.version)
        run.assert_not_called()
        remove.assert_not_called()
        self.assertTrue(bootstrap.state_path(self.version).exists())
        with patch("builtins.input", return_value="REMOVE"), patch.object(bootstrap.shutil, "rmtree") as remove, contextlib.redirect_stdout(io.StringIO()):
            bootstrap.uninstall(runtime, self.version)
        remove.assert_called_once_with(runtime.resolve())
        self.assertFalse(bootstrap.state_path(self.version).exists())

    def test_source_allowlist_excludes_integrations_secrets_and_private_scripts(self):
        source = self.folder / "source"
        source.mkdir()
        builder.copy_source(ROOT, source)
        names = {p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_file()}
        for forbidden in ("integrations/", "config.json", "session.bin", "make_day_playlist.py", ".git/", "tests/"):
            self.assertFalse(any(forbidden in name for name in names), forbidden)
        for required in builder.WHEEL_DOCS:
            self.assertIn(required, names)

    def test_bundle_standalone_guides_launchers_integrity_and_safe_names(self):
        wheel = self.folder / f"apple_music_playlists-{self.version}-py3-none-any.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            for doc in builder.WHEEL_DOCS:
                archive.writestr(f"package.data/data/share/apple-music-playlists/{Path(doc).name}", "synthetic guide")
        with patch.dict(os.environ, {"NETEASE_COOKIE": "SECRET-DO-NOT-BUNDLE"}):
            result = builder.package_bundle(wheel, self.folder)
        with zipfile.ZipFile(result) as archive:
            self.assertIsNone(archive.testzip())
            prefix = f"NetEase-Curator-{self.version}-Windows-Preview/"
            names = archive.namelist()
            for name in ("README.txt", "qr_gateway.cjs", "install.cmd", "bootstrap.py", "login-import.cmd", "login-qr.cmd", "configure.cmd", "uninstall.cmd", "bundle.json", "docs/netease-port.md"):
                self.assertIn(prefix + name, names)
            self.assertNotIn(prefix + "README_EN.md", names)
            self.assertNotIn(prefix + "START.cmd", names)
            self.assertNotIn(prefix + "onboarding.py", names)
            self.assertTrue(archive.read(prefix + "README.txt").startswith(b"\xef\xbb\xbf"))
            self.assertIn(b"\r\n", archive.read(prefix + "install.cmd"))
            for name in names:
                self.assertFalse(Path(name).is_absolute() or ".." in Path(name).parts)
                self.assertNotIn(b"SECRET-DO-NOT-BUNDLE", archive.read(name))
            checksums = archive.read(prefix + "CHECKSUMS.sha256").decode("ascii").splitlines()
            self.assertEqual(len(checksums), len(names) - 1)
            for line in checksums:
                digest, name = line.split("  ", 1)
                self.assertEqual(hashlib.sha256(archive.read(prefix + name)).hexdigest(), digest)
        self.assertEqual(result.name, f"NetEase-Curator-{self.version}-Windows-Preview.zip")

    def test_bundle_refuses_wheel_without_beta_guides(self):
        wheel = self.folder / f"apple_music_playlists-{self.version}-py3-none-any.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr("legacy.py", "# synthetic")
        with self.assertRaises(ValueError):
            builder.package_bundle(wheel, self.folder)

    def test_wheel_declares_all_user_guides(self):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        data_files = text.split("[tool.setuptools.data-files]", 1)[1].split("\n[", 1)[0]
        for name in builder.WHEEL_DOCS:
            self.assertIn('"' + name + '"', data_files)
        self.assertNotIn('START_HERE_EN.md', data_files)
        self.assertNotIn('START_HERE_EN.md', builder.WHEEL_DOCS)

    def test_cli_opens_qr_only_if_explicitly_requested(self):
        with patch.object(netease_login, "qr_login", return_value={"logged_in": True}) as qr, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(netease_login.main(["qr", "--save", "--open"]), 0)
        self.assertTrue(qr.call_args.kwargs["open_browser"])
        with patch.object(netease_login, "qr_login", return_value={"logged_in": True}) as qr, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(netease_login.main(["qr", "--save"]), 0)
        self.assertFalse(qr.call_args.kwargs["open_browser"])

    def test_qr_opens_only_valid_local_page_and_cleans_up(self):
        c = Mock()
        c.gateway = "http://127.0.0.1:3000"
        c.request.side_effect = [{"data": {"unikey": "fixture-key"}},
            {"data": {"qrimg": "data:image/png;base64,AA=="}},
            {"code": 803, "cookie": "MUSIC_U=synthetic"}]
        with patch.object(netease_login, "NeteaseClient", return_value=c), patch.object(am_paths, "cache_dir", return_value=self.folder), patch.object(netease_login, "validate_and_save", return_value={"logged_in": True}), patch.object(netease_login.webbrowser, "open") as browser, contextlib.redirect_stdout(io.StringIO()):
            netease_login.qr_login(open_browser=True)
        self.assertTrue(browser.call_args.args[0].startswith("file:"))
        self.assertFalse(list(self.folder.rglob("qr-*.html")))

    def test_qr_invalid_image_never_opens_browser(self):
        c = Mock()
        c.gateway = "http://127.0.0.1:3000"
        c.request.side_effect = [{"data": {"unikey": "fixture-key"}},
            {"data": {"qrimg": "https://evil.example/track"}}]
        with patch.object(netease_login, "NeteaseClient", return_value=c), patch.object(netease_login.webbrowser, "open") as browser:
            with self.assertRaises(netease_login.sessions.SessionError):
                netease_login.qr_login(open_browser=True)
        browser.assert_not_called()

    def gateway_fixture(self):
        root = bootstrap.BUNDLE_DIR / "qr-runtime"
        sdk_meta = "sdk/node_modules/@neteasecloudmusicapienhanced/api/package.json"
        for name, content in {"node.exe": b"synthetic-node", "NODE_LICENSE": b"synthetic license",
                              "sdk/package-lock.json": b"{}", sdk_meta: b'{"version":"4.41.1"}'}.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        helper = bootstrap.BUNDLE_DIR / "qr_gateway.cjs"
        helper.write_bytes(b"// synthetic helper")
        entries = sorted(path for path in root.rglob("*") if path.is_file())
        checksums = "\n".join(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.relative_to(root).as_posix() for path in entries) + "\n"
        (root / "FILES.sha256").write_text(checksums, encoding="ascii")
        return {"qr": {"platform": "win-x64", "sdk_version": "4.41.1",
                "helper_sha256": hashlib.sha256(helper.read_bytes()).hexdigest(),
                "files_sha256": hashlib.sha256((root / "FILES.sha256").read_bytes()).hexdigest()}}, root

    def test_gateway_payload_integrity_extra_file_helper_tamper_and_wrong_platform(self):
        body, root = self.gateway_fixture()
        with patch.object(bootstrap, "supports_gateway", return_value=True):
            self.assertEqual(bootstrap.gateway_assets(body)[0], root / "node.exe")
            extra = root / "unlisted.js"
            extra.write_text("// synthetic", encoding="utf-8")
            with self.assertRaises(bootstrap.SetupError):
                bootstrap.gateway_assets(body)
            extra.unlink()
            (root / "node.exe").write_bytes(b"tampered")
            with self.assertRaises(bootstrap.SetupError):
                bootstrap.gateway_assets(body)
        with patch.object(bootstrap, "supports_gateway", return_value=False):
            with self.assertRaises(bootstrap.SetupError):
                bootstrap.gateway_assets(body)
        with self.assertRaises(bootstrap.SetupError):
            bootstrap.gateway_assets({})

    def test_gateway_helper_and_checksum_tamper_are_rejected_before_execution(self):
        body, root = self.gateway_fixture()
        with patch.object(bootstrap, "supports_gateway", return_value=True), patch.object(bootstrap.subprocess, "Popen") as spawn:
            (bootstrap.BUNDLE_DIR / "qr_gateway.cjs").write_bytes(b"altered")
            with self.assertRaises(bootstrap.SetupError):
                with bootstrap.managed_gateway(body):
                    pass
            spawn.assert_not_called()

    def test_gateway_start_is_private_ephemeral_and_stopped_even_if_login_fails(self):
        process = Mock(stdin=io.StringIO(), stdout=io.StringIO('{"ready":true,"port":48731,"login_only":true}\n'))
        process.poll.return_value = None
        paths = (self.folder / "node.exe", self.folder / "sdk", self.folder / "qr_gateway.cjs")
        with patch.object(bootstrap, "gateway_assets", return_value=paths), patch.object(bootstrap.subprocess, "Popen", return_value=process) as spawn:
            with self.assertRaises(RuntimeError):
                with bootstrap.managed_gateway({}):
                    self.assertEqual(spawn.call_args.args[0][-1], "0")
                    env = spawn.call_args.kwargs["env"]
                    self.assertNotEqual(env["TEMP"], os.environ.get("TEMP"))
                    self.assertNotIn("NETEASE_GATEWAY_DIAGNOSTICS", env)
                    self.assertEqual(env["NETEASE_COOKIE"], "")
                    raise RuntimeError("synthetic failure")
        self.assertTrue(process.stdin.closed)
        self.assertTrue(process.stdout.closed)
        process.wait.assert_called_once_with(timeout=3)
        self.assertFalse(list((self.folder / "cache/netease-login").glob("gateway-*")))

    def test_gateway_invalid_ready_port_or_start_failure_never_hands_off(self):
        for report in ({"ready":True,"port":True,"login_only":True}, {"ready":True,"port":1,"login_only":True}, {"ready":True,"port":49000,"login_only":False}):
            process = Mock(stdin=io.StringIO(), stdout=io.StringIO(json.dumps(report) + "\n"))
            process.poll.return_value = None
            with patch.object(bootstrap, "gateway_assets", return_value=("node", "sdk", "helper")), patch.object(bootstrap.subprocess, "Popen", return_value=process):
                with self.assertRaises(bootstrap.SetupError):
                    with bootstrap.managed_gateway({}):
                        self.fail("Invalid gateway must not yield")
            process.wait.assert_called_once()

    def test_gateway_stop_terminates_then_kills_a_stuck_process(self):
        process = Mock(stdin=io.StringIO(), stdout=io.StringIO())
        process.wait.side_effect = [subprocess.TimeoutExpired("synthetic", 3), subprocess.TimeoutExpired("synthetic", 3), 0]
        bootstrap.stop_gateway(process)
        process.terminate.assert_called_once()
        process.kill.assert_called_once()

    def test_managed_qr_no_manual_gateway_and_direct_validation_only_after_close(self):
        runtime = self.runtime_fixture()
        stages = []
        @contextlib.contextmanager
        def gateway(body):
            stages.append("start")
            try:
                yield "http://127.0.0.1:48731"
            finally:
                stages.append("stop")
        def status(runtime):
            self.assertEqual(stages, ["start", "stop"])
            return True
        with patch.object(bootstrap, "managed_gateway", side_effect=gateway), patch.object(bootstrap, "run_qr", return_value=0) as qr, patch.object(bootstrap, "login_status", side_effect=status), patch("builtins.input") as prompt, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(bootstrap.launch_login(runtime, "qr", body={"qr":True}, quiet=True), 0)
        prompt.assert_not_called()
        self.assertEqual(qr.call_args.args[1]["NETEASE_API_URL"], "http://127.0.0.1:48731")
        self.assertTrue(qr.call_args.kwargs["quiet"])

    def test_qr_success_not_reported_if_direct_login_fails(self):
        with patch.object(bootstrap, "managed_gateway", return_value=contextlib.nullcontext("http://127.0.0.1:48731")), patch.object(bootstrap, "run_qr", return_value=0), patch.object(bootstrap, "login_status", return_value=False), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(bootstrap.launch_login(self.folder, "qr", body={"qr":True}), 1)

    def test_cancelled_helper_qr_kills_child_and_never_captures_credentials(self):
        process = Mock()
        process.poll.return_value = None
        cancel = Mock()
        cancel.is_set.side_effect = [False, True]
        with patch.object(bootstrap.subprocess, "Popen", return_value=process) as spawn:
            self.assertEqual(bootstrap.run_qr(self.folder, {}, quiet=True, cancel=cancel), 1)
        process.terminate.assert_called_once()
        self.assertEqual(spawn.call_args.kwargs["stdout"], subprocess.DEVNULL)
        self.assertEqual(spawn.call_args.kwargs["stderr"], subprocess.DEVNULL)
        self.assertFalse(list((self.folder / "cache/netease-login").glob("qr-page-*")))

    def test_qr_page_cleanup_survives_abrupt_child_exit(self):
        def create_page(command, **kwargs):
            folder = Path(kwargs["env"]["LOCALAPPDATA"]) / "am-playlist/netease-login"
            folder.mkdir(parents=True)
            (folder / "qr-synthetic.html").write_text("synthetic only", encoding="utf-8")
            raise subprocess.TimeoutExpired("synthetic", 180)
        with patch.object(bootstrap.subprocess, "run", side_effect=create_page):
            with self.assertRaises(subprocess.TimeoutExpired):
                bootstrap.run_qr(self.folder, {})
        self.assertFalse(list((self.folder / "cache/netease-login").glob("qr-page-*")))

    def test_login_status_returns_only_verified_bool_and_does_not_leak_output(self):
        for code, stdout, expected in ((0,'{"logged_in":true}',True), (1,'{"logged_in":true}',False), (0,'{"logged_in":"true"}',False), (0,'DO-NOT-EXPOSE',False)):
            with patch.object(bootstrap.subprocess, "run", return_value=Mock(returncode=code, stdout=stdout)), contextlib.redirect_stdout(io.StringIO()) as captured:
                self.assertEqual(bootstrap.login_status(self.folder), expected)
            self.assertEqual(captured.getvalue(), "")

    def test_conversation_starter_and_readonly_config_without_app_wizard(self):
        runtime = self.runtime_fixture()
        config = bootstrap.mcp_config(runtime)
        self.assertEqual(config["mcpServers"]["netease-curator-beta"]["env"]["NETEASE_ENABLE_WRITES"], "0")
        self.assertEqual(config["mcpServers"]["netease-curator-beta"]["env"]["NETEASE_LOGIN_BUNDLE"], str(bootstrap.BUNDLE_DIR.resolve()))
        bootstrap.configs(runtime)
        starter = (runtime / "client-config/FIRST_PLAYLIST.txt").read_text(encoding="utf-8-sig")
        self.assertIn("帮我开始使用网易云 MCP", starter)
        self.assertIn("征得我的同意", starter)
        self.assertIn("不要让我把凭证或二维码发到聊天", starter)

    def test_qr_dependency_lock_rejects_remote_scripts_unpinned_or_nonregistry_inputs(self):
        lock = json.loads((ROOT / "beta/gateway.package-lock.json").read_text(encoding="utf-8"))
        builder.validate_sdk_lock(lock)
        for patch_value in ({"resolved":"https://evil.example/code.tgz"}, {"integrity":""}, {"link":True}):
            changed = json.loads(json.dumps(lock))
            changed["packages"]["node_modules/@neteasecloudmusicapienhanced/api"].update(patch_value)
            with self.assertRaises(ValueError):
                builder.validate_sdk_lock(changed)

    def test_same_version_changed_wheel_gets_new_runtime_and_failed_upgrade_preserves_pointer(self):
        body, wheel = self.manifest_fixture()
        prior_runtime = self.runtime_fixture()
        old_state = bootstrap.state_path(self.version).read_bytes()
        with patch.object(bootstrap.venv, "EnvBuilder") as make, patch.object(bootstrap.subprocess, "run", return_value=Mock(returncode=1)), contextlib.redirect_stdout(io.StringIO()):
            make.return_value.create.side_effect = lambda path: path.mkdir(parents=True)
            with self.assertRaises(bootstrap.SetupError):
                bootstrap.install(body)
        self.assertEqual(bootstrap.state_path(self.version).read_bytes(), old_state)
        self.assertTrue(prior_runtime.exists())
        with patch.object(bootstrap.venv, "EnvBuilder") as make, patch.object(bootstrap.subprocess, "run", return_value=Mock(returncode=0)), patch.object(bootstrap, "probe"), contextlib.redirect_stdout(io.StringIO()):
            make.return_value.create.side_effect = lambda path: path.mkdir(parents=True)
            updated = bootstrap.install(body)
        self.assertNotEqual(updated, prior_runtime)
        self.assertTrue(prior_runtime.exists())
        state = json.loads(bootstrap.state_path(self.version).read_text(encoding="utf-8"))
        self.assertEqual(state["wheel_sha256"], body["sha256"])
        self.assertEqual(state["runtime"], str(updated.resolve()))

    def test_same_wheel_reuses_existing_runtime_without_reinstall(self):
        body, wheel = self.manifest_fixture()
        runtime = self.runtime_fixture()
        bootstrap.write_json(bootstrap.state_path(self.version), {"version":self.version, "runtime":str(runtime), "wheel_sha256":body["sha256"]})
        with patch.object(bootstrap.venv, "EnvBuilder") as make, patch.object(bootstrap, "probe") as probe, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(bootstrap.install(body), runtime.resolve())
        make.assert_not_called()
        probe.assert_called_once_with(runtime.resolve(), body)

    def test_complete_bundle_contains_qr_runtime_and_provenance_not_python(self):
        wheel = self.folder / f"apple_music_playlists-{self.version}-py3-none-any.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            for doc in builder.WHEEL_DOCS:
                archive.writestr(f"package.data/data/share/apple-music-playlists/{Path(doc).name}", "synthetic guide")
        body, gateway = self.gateway_fixture()
        (gateway / "THIRD_PARTY.json").write_text('{"fixture":true}', encoding="utf-8")
        result = builder.package_bundle(wheel, self.folder, gateway=gateway)
        with zipfile.ZipFile(result) as archive:
            prefix = f"NetEase-Curator-{self.version}-Windows-Preview/"
            metadata = json.loads(archive.read(prefix + "bundle.json"))
            self.assertEqual(metadata["qr"]["platform"], "win-x64")
            self.assertEqual(metadata["qr"]["sdk_version"], "4.41.1")
            self.assertIn(prefix + "qr-runtime/node.exe", archive.namelist())
            self.assertIn(prefix + "qr-runtime/NODE_LICENSE", archive.namelist())
            self.assertIn(prefix + "qr-runtime/THIRD_PARTY.json", archive.namelist())
            self.assertNotIn(prefix + "LIGHT_PACKAGE.txt", archive.namelist())
            self.assertFalse(any(name.endswith("python.exe") for name in archive.namelist()))

    def test_prepare_gateway_offline_fixture_pins_hashes_disables_scripts_and_ships_licenses(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            prefix = f"node-v{builder.NODE_VERSION}-win-x64/"
            archive.writestr(prefix + "node.exe", b"synthetic-node")
            archive.writestr(prefix + "LICENSE", "synthetic-node-license")
        data = payload.getvalue()
        response = io.BytesIO(data)
        response.geturl = lambda: f"https://nodejs.org/dist/v{builder.NODE_VERSION}/node.zip"
        def install_fixture(command, **kwargs):
            package = Path(kwargs["cwd"]) / "node_modules/@neteasecloudmusicapienhanced/api"
            package.mkdir(parents=True)
            (package / "package.json").write_text('{"version":"4.41.1"}', encoding="utf-8")
            (package / "LICENSE").write_text("synthetic-sdk-license", encoding="utf-8")
            return Mock(returncode=0)
        with patch.object(builder, "NODE_ZIP_SHA256", hashlib.sha256(data).hexdigest()), patch.object(builder, "NODE_EXE_SHA256", hashlib.sha256(b"synthetic-node").hexdigest()), patch.object(builder.urllib.request, "urlopen", return_value=response) as download, patch.object(builder.shutil, "which", return_value="npm"), patch.object(builder.subprocess, "run", side_effect=install_fixture) as npm, contextlib.redirect_stdout(io.StringIO()):
            output = builder.prepare_gateway(self.folder)
        self.assertIn("--ignore-scripts", npm.call_args.args[0])
        self.assertIn("--omit=dev", npm.call_args.args[0])
        self.assertNotIn("NETEASE_COOKIE", npm.call_args.kwargs["env"])
        self.assertTrue((output / "NODE_LICENSE").is_file())
        self.assertTrue((output / "sdk/node_modules/@neteasecloudmusicapienhanced/api/LICENSE").is_file())
        self.assertTrue((output / "FILES.sha256").is_file())
        provenance = json.loads((output / "THIRD_PARTY.json").read_text(encoding="utf-8"))
        self.assertEqual(provenance["sdk"]["version"], "4.41.1")
        self.assertEqual(len(provenance["packages"]), 1)



if __name__ == "__main__":
    unittest.main()
