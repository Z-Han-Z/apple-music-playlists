"""Windows beta handoff: local-wheel install, safe launch, nonsecret MCP configuration.

This standalone file is shipped next to the wheel; it never reads browser cookies.
"""
import hashlib
import contextlib
import json
import os
import platform
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import venv
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit


class SetupError(RuntimeError):
    pass


BUNDLE_DIR = Path(__file__).resolve().parent


def user_dir(kind):
    if os.name == "nt":
        variable = "APPDATA" if kind == "config" else "LOCALAPPDATA"
        fallback = Path.home() / "AppData" / ("Roaming" if kind == "config" else "Local")
    else:
        variable = "XDG_CONFIG_HOME" if kind == "config" else "XDG_CACHE_HOME"
        fallback = Path.home() / (".config" if kind == "config" else ".cache")
    return Path(os.environ.get(variable) or fallback) / "am-playlist"


def manifest():
    body = json.loads((BUNDLE_DIR / "bundle.json").read_text(encoding="utf-8"))
    if not isinstance(body, dict):
        raise SetupError("内测包信息无效，请重新取得完整 ZIP。")
    version = body.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}", version):
        raise SetupError("内测版本信息无效，请重新取得完整 ZIP。")
    if body.get("wheel") != f"apple_music_playlists-{version}-py3-none-any.whl":
        raise SetupError("安装包文件名不正确。")
    if not isinstance(body.get("sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", body["sha256"]):
        raise SetupError("安装包校验信息无效。")
    if not isinstance(body.get("tool_count"), int) or isinstance(body["tool_count"], bool) or body["tool_count"] < 1:
        raise SetupError("内测工具清单信息无效。")
    return body


def runtime_base(version):
    return user_dir("cache") / "netease-beta-runtime" / version


def state_path(version):
    return user_dir("config") / "netease-beta" / (version + ".json")


def python_path(runtime):
    return runtime / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def clean_env():
    # Probes/installers must not accidentally use a shell's pre-existing account session.
    env = dict(os.environ)
    for key in ("NETEASE_COOKIE", "NETEASE_CSRF", "NETEASE_API_URL"):
        env[key] = ""
    env["NETEASE_ENABLE_WRITES"] = "0"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    for key in ("NODE_OPTIONS", "NODE_PATH", "NETEASE_GATEWAY_DIAGNOSTICS", "APPLE_MUSIC_USER_TOKEN"):
        env.pop(key, None)
    return env


def write_json(path, value):
    if path.is_symlink() or path.parent.is_symlink():
        raise SetupError("不允许将内测配置写入符号链接。")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".beta-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def check_runtime(path, version):
    path = Path(path)
    base = runtime_base(version).resolve()
    resolved = path.resolve()
    if (path.is_symlink() or path.parent.is_symlink() or resolved.parent != base or
            not re.fullmatch(r"[a-f0-9]{32}", resolved.name)):
        raise SetupError("拒绝操作内测专属目录以外的路径。")
    marker = json.loads((resolved / ".netease-beta-runtime.json").read_text(encoding="utf-8"))
    if marker != {"version": version, "kind": "netease-beta-runtime"}:
        raise SetupError("无法确认这是本安装器创建的内测环境。")
    return resolved


def installed(version):
    path = state_path(version)
    if not path.exists():
        raise SetupError("尚未安装；请先完整解压并运行 install.cmd。")
    if path.is_symlink():
        raise SetupError("内测配置不允许使用符号链接。")
    body = json.loads(path.read_text(encoding="utf-8"))
    if body.get("version") != version or not isinstance(body.get("runtime"), str):
        raise SetupError("内测安装记录无效。")
    runtime = check_runtime(body["runtime"], version)
    if not python_path(runtime).is_file():
        raise SetupError("内测 Python 环境缺失；请重新安装，不要改用全局旧版包。")
    return runtime


def mcp_config(runtime, *, writes=False):
    env = {"NETEASE_COOKIE": "", "NETEASE_CSRF": "", "NETEASE_API_URL": "",
           "NETEASE_ENABLE_WRITES": "1" if writes else "0", "NETEASE_LOGIN_BUNDLE": str(BUNDLE_DIR.resolve())}
    return {"mcpServers": {"netease-curator-beta": {"command": str(python_path(runtime)),
            "args": ["-I", "-m", "netease_mcp_server"], "env": env}}}


def configs(runtime):
    folder = runtime / "client-config"
    for name, writes in (("mcp-config.json", False), ("mcp-config-write-opt-in.json", True)):
        write_json(folder / name, mcp_config(runtime, writes=writes))
    (folder / "FIRST_PLAYLIST.txt").write_text(
        "帮我开始使用网易云 MCP。先检查配置和登录；如果需要登录，请解释并征得我的同意，"
        "引导我在本机扫码，不要让我把凭证或二维码发到聊天。准备好后再问我想做什么歌单；"
        "先给预览，不创建或修改歌单。\n", encoding="utf-8-sig")
    return folder / "mcp-config.json"


def probe(runtime, body):
    source = "\n".join(json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": {}})
                       for i, method in enumerate(("initialize", "tools/list"), 1)) + "\n"
    result = subprocess.run([str(python_path(runtime)), "-I", "-m", "netease_mcp_server"],
                            input=source, capture_output=True, encoding="utf-8", timeout=30,
                            env=clean_env(), cwd=runtime)
    if result.returncode:
        raise SetupError("内测 MCP 启动检查失败；未进行账号操作。")
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    if (len(responses) != 2 or responses[0]["result"]["serverInfo"]["version"] != body["version"] or
            len(responses[1]["result"]["tools"]) != body["tool_count"]):
        raise SetupError("内测服务版本/工具数量不匹配。")


def install(body):
    wheel = BUNDLE_DIR / "wheel" / body["wheel"]
    if wheel.is_symlink() or hashlib.sha256(wheel.read_bytes()).hexdigest() != body["sha256"]:
        raise SetupError("wheel 校验失败；不要继续安装，请重新下载。")
    state = state_path(body["version"])
    if state.exists():
        runtime = installed(body["version"])
        prior = json.loads(state.read_text(encoding="utf-8"))
        if prior.get("wheel_sha256") == body["sha256"]:
            probe(runtime, body)
            print("此构建已经安装。配置文件：" + str(configs(runtime)))
            return runtime
        print("检测到同版本的新构建；创建新独立环境，成功前不切换现有安装。", flush=True)
    runtime = runtime_base(body["version"]) / uuid.uuid4().hex
    if runtime.exists() or runtime.parent.is_symlink():
        raise SetupError("内测目录不可安全创建。")
    print("正在创建独立环境并离线安装本包，不修改系统 Python，不需要管理员。", flush=True)
    venv.EnvBuilder(with_pip=True).create(runtime)
    write_json(runtime / ".netease-beta-runtime.json", {"version": body["version"], "kind": "netease-beta-runtime"})
    process = subprocess.run([str(python_path(runtime)), "-I", "-m", "pip", "install",
                              "--no-index", "--no-deps", str(wheel)], env=clean_env(), cwd=runtime,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if process.returncode:
        raise SetupError("离线安装失败；未写入默认安装记录。失败的独立目录可手动清理。")
    probe(runtime, body)
    config = configs(runtime)
    write_json(state, {"version": body["version"], "runtime": str(runtime.resolve()), "wheel_sha256": body["sha256"]})
    print("安装成功。将生成配置合并到 MCP 客户端并重连，然后在聊天里说：帮我开始使用网易云 MCP。")
    print("默认只读配置：" + str(config))
    print(json.dumps(mcp_config(runtime), ensure_ascii=False, indent=2))
    return runtime


def local_gateway(value):
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise SetupError("扫码只能连接你信任的 loopback HTTP(S) 网关，不能使用公共代理。")
    return value.rstrip("/")


def supports_gateway():
    return os.name == "nt" and platform.machine().lower() in {"amd64", "x86_64"}


def gateway_assets(body):
    """Verify the entire private executable dependency tree before starting Node."""
    spec = body.get("qr")
    if not isinstance(spec, dict) or spec.get("platform") != "win-x64":
        raise SetupError("这是不含扫码运行时的轻量包；请取得完整 Windows ZIP，或使用安全导入。")
    if not supports_gateway():
        raise SetupError("随包扫码运行时仅支持 Windows x64；当前平台请使用安全导入或自建网关。")
    root = BUNDLE_DIR / "qr-runtime"
    if root.is_symlink():
        raise SetupError("扫码运行时目录不允许符号链接。")
    checksum = root / "FILES.sha256"
    helper = BUNDLE_DIR / "qr_gateway.cjs"
    for file, key in ((checksum, "files_sha256"), (helper, "helper_sha256")):
        if file.is_symlink() or not re.fullmatch(r"[a-f0-9]{64}", str(spec.get(key, ""))):
            raise SetupError("扫码运行时校验信息无效，请重新取得可信分发包。")
        if hashlib.sha256(file.read_bytes()).hexdigest() != spec[key]:
            raise SetupError("扫码运行时校验失败；未启动网关。")
    checked = set()
    for line in checksum.read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        path = PurePosixPath(name)
        if (not re.fullmatch(r"[a-f0-9]{64}", digest) or path.is_absolute() or
                ".." in path.parts or "\\" in name or ":" in name or name in checked):
            raise SetupError("扫码运行时文件清单无效。")
        target = root / name
        if (target.is_symlink() or not target.resolve().is_relative_to(root.resolve()) or
                hashlib.sha256(target.read_bytes()).hexdigest() != digest):
            raise SetupError("扫码依赖损坏；未启动网关，请重新解压可信分发包。")
        checked.add(name)
    actual = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise SetupError("扫码运行时不允许符号链接。")
        if path.is_file() and path != checksum:
            actual.add(path.relative_to(root).as_posix())
    if actual != checked or not {"node.exe", "NODE_LICENSE", "sdk/package-lock.json",
                                 "sdk/node_modules/@neteasecloudmusicapienhanced/api/package.json"} <= checked:
        raise SetupError("扫码运行时缺少文件或包含额外文件；请重新解压。")
    sdk = json.loads((root / "sdk/node_modules/@neteasecloudmusicapienhanced/api/package.json").read_text(encoding="utf-8"))
    if sdk.get("version") != "4.41.1" or spec.get("sdk_version") != "4.41.1":
        raise SetupError("扫码 SDK 版本不匹配。")
    return root / "node.exe", root / "sdk", helper


def stop_gateway(process):
    if process.stdin:
        try:
            process.stdin.close()
        except OSError:
            pass
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
    if process.stdout:
        process.stdout.close()


@contextlib.contextmanager
def managed_gateway(body):
    node, sdk, helper = gateway_assets(body)
    # Upstream temporary keys/cookies can never share the user's normal TEMP folder.
    base = user_dir("cache") / "netease-login"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gateway-", dir=base) as temporary:
        env = clean_env()
        env.update(TEMP=temporary, TMP=temporary, TMPDIR=temporary)
        process = subprocess.Popen([str(node), str(helper), str(sdk), "0"],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                   env=env, cwd=temporary,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            ready = queue.Queue()
            threading.Thread(target=lambda: ready.put(process.stdout.readline()), daemon=True).start()
            try:
                report = json.loads(ready.get(timeout=20))
            except (queue.Empty, ValueError):
                raise SetupError("本地扫码网关未能启动；可重新尝试或改用安全导入。") from None
            port = report.get("port") if isinstance(report, dict) else None
            if (not isinstance(report, dict) or report.get("ready") is not True or
                    report.get("login_only") is not True or isinstance(port, bool) or
                    not isinstance(port, int) or not 1024 <= port <= 65535 or process.poll() is not None):
                raise SetupError("本地扫码网关启动检查失败。")
            yield "http://127.0.0.1:" + str(port)
        finally:
            stop_gateway(process)


def login_status(runtime):
    """Return only a verified login flag, never session bodies or raw subprocess errors."""
    result = subprocess.run([str(python_path(runtime)), "-I", "-m", "netease_login", "status", "--verify"],
                            env=clean_env(), cwd=runtime, capture_output=True, encoding="utf-8",
                            timeout=45, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        value = json.loads(result.stdout)
    except ValueError:
        return False
    return result.returncode == 0 and isinstance(value, dict) and value.get("logged_in") is True


def run_qr(runtime, env, *, quiet=False, cancel=None):
    base = user_dir("cache") / "netease-login"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="qr-page-", dir=base) as temporary:
        isolated = dict(env)
        isolated.update(LOCALAPPDATA=temporary, XDG_CACHE_HOME=temporary)
        return run_qr_process(runtime, isolated, quiet=quiet, cancel=cancel)


def run_qr_process(runtime, env, *, quiet=False, cancel=None):
    command = [str(python_path(runtime)), "-I", "-m", "netease_login", "qr", "--save", "--open"]
    if not quiet:
        return subprocess.run(command, env=env, cwd=runtime, timeout=180).returncode
    if cancel is not None and cancel.is_set():
        return 1
    # GUI login uses no credential-bearing capture/log files; its local browser owns the QR.
    process = subprocess.Popen(command, env=env, cwd=runtime, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    deadline = time.monotonic() + 180
    try:
        while process.poll() is None:
            if (cancel is not None and cancel.is_set()) or time.monotonic() >= deadline:
                return 1
            time.sleep(0.1)
        return process.returncode
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)


def launch_login(runtime, action, *, body=None, quiet=False, cancel=None):
    env = clean_env()
    if action == "import":
        print("只在下方隐藏输入中粘贴你自己的 MUSIC_U，按 Enter；不要发到 AI 聊天。", flush=True)
        arguments = ["import", "--save"]
    elif action == "qr":
        print("正在校验随包扫码组件。二维码会在本机浏览器打开；请用官方网易云 App 扫码并确认。", flush=True)
        with managed_gateway(body or manifest()) as gateway:
            env["NETEASE_API_URL"] = gateway
            code = run_qr(runtime, env, quiet=quiet, cancel=cancel)
        # A QR handoff is not complete until a gateway-free account request succeeds.
        if cancel is not None and cancel.is_set():
            return 1
        if code == 0 and not login_status(runtime):
            print("扫码会话已保存，但直连验证未通过。请检查网络，再点检查登录；不要反复扫码。")
            return 1
        print("扫码登录成功，临时网关已关闭。" if code == 0 else "扫码未完成，临时网关已关闭；可重试或改用安全导入。")
        return code
    elif action == "qr-external":
        print("进阶模式：仅连接你信任的已启动本地网关。")
        env["NETEASE_API_URL"] = local_gateway(input("本地网关地址（留空使用 http://127.0.0.1:3000）：").strip() or "http://127.0.0.1:3000")
        arguments = ["qr", "--save", "--open"]
    elif action == "forget":
        print("将删除此 Windows 用户共享的本地网易云会话，影响其他 nc-mcp 客户端；不会撤销服务器令牌。")
        if input("确认请输入 FORGET：").strip() != "FORGET":
            print("已取消，未删除会话。")
            return 0
        arguments = ["forget", "--confirm"]
    else:
        print("检查本地登录（只读联网，不显示令牌）。", flush=True)
        arguments = ["status", "--verify"]
    process = subprocess.run([str(python_path(runtime)), "-I", "-m", "netease_login", *arguments],
                             env=env, cwd=runtime)
    print("操作完成。" if process.returncode == 0 else "未完成，请查看 README.txt 故障排查；不要盲目重试账号写入。")
    return process.returncode


def uninstall(runtime, version):
    runtime = check_runtime(runtime, version)
    print("请先停用客户端 MCP 服务。只移除此内测专属环境：" + str(runtime))
    print("保留系统 Python、Apple 设置、共享网易云会话以及网易云账号内容。")
    if input("确认请输入 REMOVE：").strip() != "REMOVE":
        print("已取消，未删除环境。")
        return
    runtime = check_runtime(runtime, version)  # revalidate resolved target immediately before removal
    shutil.rmtree(runtime)
    state_path(version).unlink()
    print("内测环境已移除，无法由工具恢复；可重新运行 install.cmd 安装。共享会话未删除。")


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    actions = {"install", "import", "qr", "qr-chat", "qr-external", "status", "configure", "forget", "uninstall"}
    args = list(sys.argv[1:] if argv is None else argv)
    if sys.version_info < (3, 10):
        print("请安装正常版本的 Python 3.10+；本包不包含 Python。")
        return 1
    if len(args) != 1 or args[0] not in actions:
        print("请通过随包的安装/登录/配置/卸载入口运行；使用引导在 MCP 客户端对话中完成。")
        return 1
    try:
        body = manifest()
        if args[0] == "install":
            install(body)
            return 0
        runtime = installed(body["version"])
        if args[0] == "qr-chat":
            cancel = threading.Event()
            # The MCP owns this private pipe; cancellation or parent EOF stops QR.
            def listen():
                sys.stdin.readline()
                cancel.set()
            threading.Thread(target=listen, daemon=True).start()
            return launch_login(runtime, "qr", body=body, quiet=True, cancel=cancel)
        if args[0] == "configure":
            path = configs(runtime)
            print("请合并服务项到客户端 MCP 设置，不要覆盖其他服务：" + str(path))
            if os.name == "nt":
                subprocess.Popen(["notepad.exe", str(path)])
            return 0
        if args[0] == "uninstall":
            uninstall(runtime, body["version"])
            return 0
        return launch_login(runtime, args[0])
    except SetupError as exc:
        print(str(exc), file=sys.stderr)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, EOFError):
        print("内测包/环境检查未通过。查看 README.txt，必要时向维护者提供脱敏错误；不输出账号数据。", file=sys.stderr)
    except KeyboardInterrupt:
        print("已取消。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
