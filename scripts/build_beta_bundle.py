"""Whitelist-only beta distribution builder. Artifacts always go to the user cache."""
import ast
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import urllib.parse
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import am_paths
import netease_mcp_server


BETA_FILES = {
    "START_HERE_ZH_CN.txt": "README.txt", "START_HERE_EN.md": "README_EN.md",
    "bootstrap.py": "bootstrap.py", "qr_gateway.cjs": "qr_gateway.cjs",
    "mcp-config.example.json": "mcp-config.example.json",
    **{name: name for name in ("run.cmd", "install.cmd", "login-import.cmd", "login-qr.cmd",
                              "status.cmd", "configure.cmd", "forget-login.cmd", "uninstall.cmd")},
}
WHEEL_DOCS = ("README.md", "docs/netease-port.md", "beta/START_HERE_ZH_CN.txt", "beta/START_HERE_EN.md")
NODE_VERSION = "24.19.0"
NODE_ZIP_SHA256 = "57f71ab3652e797d84acddc79c81cc9ff1c6ddb2a1974cdb83f00fee9bff4c73"
NODE_EXE_SHA256 = "3602f2bb1a10f2cbab4c36886218a33c1ab3db87290e73b033c46c77147d0237"
SDK_VERSION = "4.41.1"


def validate_sdk_lock(lock):
    """All third-party bytes must have registry integrity; never install scripts or git URLs."""
    packages = lock.get("packages", {})
    if packages.get("", {}).get("dependencies") != {"@neteasecloudmusicapienhanced/api": SDK_VERSION}:
        raise ValueError("Gateway dependency must be pinned")
    if packages.get("node_modules/@neteasecloudmusicapienhanced/api", {}).get("version") != SDK_VERSION:
        raise ValueError("Gateway lock version mismatch")
    for name, package in packages.items():
        if not name:
            continue
        if (not name.startswith("node_modules/") or ".." in Path(name).parts or
                package.get("link") or not package.get("resolved", "").startswith("https://registry.npmjs.org/") or
                not re.fullmatch(r"sha512-[A-Za-z0-9+/]+={0,2}", package.get("integrity", ""))):
            raise ValueError("Unsafe dependency lock entry")


def prepare_gateway(output, root=ROOT):
    """Maintainer-only network build. End users receive a complete, offline dependency tree."""
    gateway = output / "prepared-qr-runtime"
    gateway.mkdir()
    filename = f"node-v{NODE_VERSION}-win-x64.zip"
    archive_path = output / filename
    url = f"https://nodejs.org/dist/v{NODE_VERSION}/{filename}"
    print("Fetching pinned Node runtime from nodejs.org; checking published SHA256.", flush=True)
    with urllib.request.urlopen(url, timeout=60) as response, archive_path.open("wb") as stream:
        if urllib.parse.urlsplit(response.geturl()).hostname != "nodejs.org":
            raise ValueError("Node download left the official origin")
        shutil.copyfileobj(response, stream)
    if hashlib.sha256(archive_path.read_bytes()).hexdigest() != NODE_ZIP_SHA256:
        raise ValueError("Node archive integrity mismatch")
    with zipfile.ZipFile(archive_path) as archive:
        prefix = f"node-v{NODE_VERSION}-win-x64/"
        for source, destination in (("node.exe", "node.exe"), ("LICENSE", "NODE_LICENSE")):
            (gateway / destination).write_bytes(archive.read(prefix + source))
    if hashlib.sha256((gateway / "node.exe").read_bytes()).hexdigest() != NODE_EXE_SHA256:
        raise ValueError("Node executable integrity mismatch")
    sdk = gateway / "sdk"
    sdk.mkdir()
    lock = json.loads((root / "beta/gateway.package-lock.json").read_text(encoding="utf-8"))
    validate_sdk_lock(lock)
    shutil.copyfile(root / "beta/gateway.package.json", sdk / "package.json")
    shutil.copyfile(root / "beta/gateway.package-lock.json", sdk / "package-lock.json")
    npm = shutil.which("npm.cmd" if sys.platform == "win32" else "npm")
    if not npm:
        raise ValueError("Maintainer build requires npm; --light is for advanced import-only users")
    env = dict(os.environ)
    for key in ("NETEASE_COOKIE", "NETEASE_CSRF", "NETEASE_API_URL", "NODE_OPTIONS", "NODE_PATH",
                "APPLE_MUSIC_USER_TOKEN", "NPM_TOKEN", "NODE_AUTH_TOKEN"):
        env.pop(key, None)
    print("Installing registry-integrity-locked QR dependencies; lifecycle scripts disabled.", flush=True)
    result = subprocess.run([npm, "ci", "--ignore-scripts", "--omit=dev", "--no-audit", "--no-fund",
                             "--registry=https://registry.npmjs.org", "--cache=" + str(output / "npm-cache")],
                            cwd=sdk, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=240)
    if result.returncode:
        raise ValueError("Pinned QR dependency installation failed; raw npm logs are not distributed")
    package = json.loads((sdk / "node_modules/@neteasecloudmusicapienhanced/api/package.json").read_text(encoding="utf-8"))
    if package.get("version") != SDK_VERSION:
        raise ValueError("Installed SDK does not match lock")
    # npm's .bin links are not used and are not executable inputs for our private gateway.
    bin_dir = sdk / "node_modules/.bin"
    if bin_dir.exists():
        if bin_dir.is_symlink() or bin_dir.resolve().parent != (sdk / "node_modules").resolve():
            raise ValueError("Unsafe npm bin directory")
        shutil.rmtree(bin_dir)
    packages = []
    for name, meta in lock["packages"].items():
        if name and (sdk / name / "package.json").is_file():
            packages.append({"path": name, "version": meta["version"], "license": meta.get("license", "see package"),
                             "resolved": meta["resolved"], "integrity": meta["integrity"]})
    (gateway / "THIRD_PARTY.json").write_text(json.dumps({"node": {"version": NODE_VERSION, "url": url,
        "archive_sha256": NODE_ZIP_SHA256, "exe_sha256": NODE_EXE_SHA256, "license": "NODE_LICENSE"},
        "sdk": {"version": SDK_VERSION, "url": "https://github.com/NeteaseCloudMusicApiEnhanced/api-enhanced"},
        "packages": packages}, indent=2) + "\n", encoding="utf-8")
    entries = sorted(path for path in gateway.rglob("*") if path.is_file())
    if any(path.is_symlink() for path in gateway.rglob("*")):
        raise ValueError("Gateway assets must not contain symlinks")
    checksums = "\n".join(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.relative_to(gateway).as_posix()
                          for path in entries) + "\n"
    (gateway / "FILES.sha256").write_text(checksums, encoding="ascii")
    return gateway


def module_names(root):
    source = (root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r"(?s)py-modules\s*=\s*(\[.*?\])", source)
    names = ast.literal_eval(match.group(1))
    if not names or any(not isinstance(name, str) or not re.fullmatch(r"[a-z_]+", name) for name in names):
        raise ValueError("Invalid module allowlist")
    return names


def copy_source(root, target):
    # No globbing over the repository: integrations, private scripts, tests and caches stay out.
    files = [name + ".py" for name in module_names(root)] + ["pyproject.toml", "LICENSE", *WHEEL_DOCS]
    for name in files:
        source, destination = root / name, target / name
        if source.is_symlink():
            raise ValueError("Distribution inputs must not be symlinks")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def package_bundle(wheel, output, root=ROOT, gateway=None):
    if wheel.name != f"apple_music_playlists-{am_paths.VERSION}-py3-none-any.whl":
        raise ValueError("Unexpected wheel version")
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        for doc in WHEEL_DOCS:
            expected = f"share/apple-music-playlists/{Path(doc).name}"
            if not any(name.endswith(expected) for name in names):
                raise ValueError("Wheel does not contain required guide: " + doc)
    folder = output / f"NetEase-Curator-{am_paths.VERSION}-Windows-Preview"
    folder.mkdir()
    for original, name in BETA_FILES.items():
        source = root / "beta" / original
        if source.is_symlink():
            raise ValueError("Bundle inputs must not be symlinks")
        # CRLF launchers for Windows Explorer/cmd; UTF-8 BOM for Notepad's Chinese guide.
        if source.suffix == ".cmd":
            (folder / name).write_bytes(source.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\n", "\r\n").encode("ascii"))
        elif name == "README.txt":
            (folder / name).write_bytes(source.read_text(encoding="utf-8").encode("utf-8-sig"))
        else:
            shutil.copyfile(source, folder / name)
    (folder / "wheel").mkdir()
    shutil.copyfile(wheel, folder / "wheel" / wheel.name)
    (folder / "docs").mkdir()
    shutil.copyfile(root / "docs" / "netease-port.md", folder / "docs" / "netease-port.md")
    shutil.copyfile(root / "LICENSE", folder / "LICENSE")
    body = {"version": am_paths.VERSION, "wheel": wheel.name,
            "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
            "tool_count": len(netease_mcp_server.TOOLS)}
    if gateway is not None:
        if gateway.is_symlink() or any(path.is_symlink() for path in gateway.rglob("*")):
            raise ValueError("Gateway inputs must not contain symlinks")
        shutil.copytree(gateway, folder / "qr-runtime", symlinks=False)
        body["qr"] = {"platform": "win-x64", "node_version": NODE_VERSION, "sdk_version": SDK_VERSION,
                      "files_sha256": hashlib.sha256((gateway / "FILES.sha256").read_bytes()).hexdigest(),
                      "helper_sha256": hashlib.sha256((folder / "qr_gateway.cjs").read_bytes()).hexdigest(),
                      "bootstrap_sha256": hashlib.sha256((folder / "bootstrap.py").read_bytes()).hexdigest()}
    else:
        (folder / "LIGHT_PACKAGE.txt").write_text("Advanced import-only package: no bundled QR runtime. Use login-import.cmd.\n", encoding="utf-8")
    (folder / "bundle.json").write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    entries = sorted(path for path in folder.rglob("*") if path.is_file())
    checksum = "\n".join(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.relative_to(folder).as_posix() for path in entries) + "\n"
    (folder / "CHECKSUMS.sha256").write_text(checksum, encoding="ascii")
    target = output / (folder.name + ".zip")
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                archive.write(path, arcname=path.relative_to(output).as_posix())
    return target


def main():
    am_paths.enable_utf8_stdout()
    parser = argparse.ArgumentParser(description="Build an offline Windows beta; Python is never bundled")
    parser.add_argument("--light", action="store_true", help="Advanced import-only package without QR runtime")
    args = parser.parse_args()
    base = am_paths.cache_dir() / "beta-distributions" / am_paths.VERSION
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-")
    output = Path(tempfile.mkdtemp(prefix=stamp, dir=base))
    source, wheels = output / "build-source", output / "wheel"
    source.mkdir()
    wheels.mkdir()
    copy_source(ROOT, source)
    subprocess.run([sys.executable, "-B", "-c",
                    "import setuptools.build_meta,sys; print(setuptools.build_meta.build_wheel(sys.argv[1]))",
                    str(wheels)], cwd=source, check=True)
    wheel = wheels / f"apple_music_playlists-{am_paths.VERSION}-py3-none-any.whl"
    gateway = None if args.light else prepare_gateway(output)
    result = package_bundle(wheel, output, gateway=gateway)
    print(json.dumps({"zip": str(result), "sha256": hashlib.sha256(result.read_bytes()).hexdigest(),
                      "bytes": result.stat().st_size}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
