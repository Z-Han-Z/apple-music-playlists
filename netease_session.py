"""Explicit local session storage. No browser harvesting, passwords or token logs."""
from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from http.cookies import SimpleCookie
from pathlib import Path

import am_paths


class SessionError(RuntimeError):
    pass


def session_path():
    return am_paths.config_dir() / "netease" / "session.bin"


def clean_cookie(value):
    value = str(value).strip()
    if "=" not in value:
        value = "MUSIC_U=" + value
    if "\r" in value or "\n" in value or len(value) > 16384:
        raise SessionError("Invalid session input")
    value = re.sub(r"^cookie\s*:\s*", "", value, flags=re.IGNORECASE)
    authentication = {}
    # SDKs concatenate complete Set-Cookie lines. Unknown flag attributes (e.g.
    # Partitioned on Python <3.14) make SimpleCookie discard the WHOLE header.
    # Parse only independent authentication pairs; never import attributes/analytics.
    for part in value.split(";"):
        name = part.strip().partition("=")[0].strip()
        if name not in {"MUSIC_U", "__csrf"}:
            continue
        cookie = SimpleCookie()
        try:
            cookie.load(part.strip())
        except Exception:
            raise SessionError("Invalid session input") from None
        if name not in cookie or len(cookie) != 1:
            raise SessionError("Invalid authentication cookie value")
        field = cookie[name].value
        if not re.fullmatch(r"[A-Za-z0-9._~%+/=\-]{1,4096}", field):
            raise SessionError("Invalid authentication cookie value")
        if name in authentication and authentication[name] != field:
            raise SessionError("Conflicting authentication cookies")
        authentication[name] = field
    if not authentication.get("MUSIC_U"):
        raise SessionError("MUSIC_U is required")
    # Never import analytics/device cookies from a pasted browser cookie header.
    return "; ".join(f"{key}={authentication[key]}" for key in ("MUSIC_U", "__csrf") if key in authentication)


def _dpapi(data, decrypt=False):
    """Current-user Windows DPAPI, standard library only, no UI prompts."""
    import ctypes
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypto = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    name = "CryptUnprotectData" if decrypt else "CryptProtectData"
    fn = getattr(crypto, name)
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise SessionError("Windows session protection failed")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        kernel.LocalFree(target.pbData)


def _check_path(path):
    path = Path(path)
    if path.is_symlink() or path.parent.is_symlink():
        raise SessionError("Session symlinks are not allowed")
    try:
        path.resolve().relative_to(am_paths.REPO_DIR.resolve())
    except ValueError:
        return path
    raise SessionError("Sessions must not be stored inside the repository")


def save(cookie, csrf="", *, allow_plaintext=False):
    path = _check_path(session_path())
    cookie = clean_cookie(cookie)
    if "\r" in csrf or "\n" in csrf or ";" in csrf:
        raise SessionError("Invalid CSRF input")
    data = json.dumps({"version": 1, "cookie": cookie, "csrf": csrf}).encode("utf-8")
    if os.name == "nt":
        data = b"NC1:DPAPI:" + _dpapi(data)
    elif allow_plaintext:
        data = b"NC1:POSIX:" + data
    else:
        raise SessionError("This OS requires --allow-plaintext to save a mode-0600 session; environment-only use remains available")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".session-", dir=path.parent)
    try:
        if os.name != "nt":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def load():
    path = _check_path(session_path())
    if not path.exists():
        return {}
    try:
        if os.name != "nt":
            metadata = path.stat()
            if stat.S_IMODE(metadata.st_mode) & 0o077 or metadata.st_uid != os.getuid():
                raise SessionError("Session file must be owner-only (mode 0600)")
        raw = path.read_bytes()
        if raw.startswith(b"NC1:DPAPI:") and os.name == "nt":
            data = _dpapi(raw[len(b"NC1:DPAPI:"):], decrypt=True)
        elif raw.startswith(b"NC1:POSIX:") and os.name != "nt":
            data = raw[len(b"NC1:POSIX:"):]
        else:
            raise SessionError("Session protection format is unsupported on this OS")
        body = json.loads(data)
        if body.get("version") != 1 or not isinstance(body.get("csrf", ""), str):
            raise SessionError("Invalid session format")
        body["cookie"] = clean_cookie(body["cookie"])
        if any(c in body.get("csrf", "") for c in "\r\n;"):
            raise SessionError("Invalid session format")
        return body
    except SessionError:
        raise
    except Exception:
        raise SessionError("Session could not be loaded; re-import locally") from None


def forget(*, confirm=False):
    if not confirm:
        raise SessionError("Forgetting a local session requires --confirm")
    path = _check_path(session_path())
    if path.exists():
        path.unlink()


def describe():
    path = _check_path(session_path())
    return {"saved": path.exists(), "storage": "Windows current-user DPAPI" if os.name == "nt"
            else "owner-only POSIX file (explicit plaintext consent required)",
            "note": "Local deletion does not revoke a session at NetEase"}
