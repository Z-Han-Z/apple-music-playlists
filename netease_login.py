"""Explicit local login handoff, hidden paste or optional local-gateway QR."""
from __future__ import annotations

import argparse
import getpass
import html
import json
import os
import re
import sys
import tempfile
import time
import warnings
import webbrowser
from pathlib import Path

import am_paths
import netease_session as sessions
from netease_api import NeteaseClient, NeteaseError


def hidden_cookie():
    if not sys.stdin.isatty():
        raise sessions.SessionError("Use an interactive terminal; session input must not be echoed")
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            return sessions.clean_cookie(getpass.getpass("Paste MUSIC_U or Cookie header (hidden): "))
        except getpass.GetPassWarning:
            raise sessions.SessionError("Hidden input unavailable; import cancelled") from None


def validate_and_save(cookie, *, persist=False, allow_plaintext=False, gateway=None):
    client = NeteaseClient(cookie=sessions.clean_cookie(cookie), gateway=gateway)
    client.account_id()
    client.ensure_csrf()
    if persist:
        sessions.save(client.cookie, client.csrf, allow_plaintext=allow_plaintext)
    return {"logged_in": True, "csrf_ready": True, "saved": persist,
            "note": "Session validated. Not saved unless --save was explicitly given."}


def qr_login(*, persist=False, allow_plaintext=False, timeout=120, open_browser=False):
    client = NeteaseClient(cookie="")
    if not client.gateway:
        raise sessions.SessionError("QR requires your own loopback API Enhanced gateway (NETEASE_API_URL); hidden import works without it")
    key_body = client.request("qr_key", {"type": 3})
    key = (key_body.get("data") or {}).get("unikey") or key_body.get("unikey")
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", key):
        raise sessions.SessionError("Invalid QR key response")
    body = client.request("qr_image", {"key": key, "qrimg": "true"})
    picture = (body.get("data") or {}).get("qrimg")
    if not isinstance(picture, str) or not re.fullmatch(r"data:image/png;base64,[A-Za-z0-9+/=]{1,500000}", picture):
        raise sessions.SessionError("Gateway did not return a safe local QR image")
    folder = am_paths.cache_dir() / "netease-login"
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, filename = tempfile.mkstemp(prefix="qr-", suffix=".html", dir=folder)
    path = Path(filename)
    try:
        if os.name != "nt":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write('<!doctype html><meta charset="utf-8"><title>NetEase login</title>'
                         '<h1>Scan with the official NetEase app</h1><p>Authorize only if you initiated this login.</p>'
                         '<img alt="Login QR" src="' + html.escape(picture, quote=True) + '">')
        print("Open this local QR page, scan and confirm in the official app: " + str(path), flush=True)
        if open_browser:
            try:
                webbrowser.open(path.resolve().as_uri())
            except Exception:
                print("Browser could not open automatically; open the local path above.", flush=True)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = client.request("qr_check", {"key": key, "type": 3})
            code = result["code"]
            if code == 803:
                cookie = result.get("cookie")
                if not isinstance(cookie, str):
                    raise sessions.SessionError("Authorized QR did not return a session")
                return validate_and_save(cookie, persist=persist, allow_plaintext=allow_plaintext,
                                         gateway=client.gateway)
            if code == 800:
                raise sessions.SessionError("QR expired; restart login")
            if code not in {801, 802}:
                raise sessions.SessionError("Unexpected QR status")
            time.sleep(2)
        raise sessions.SessionError("QR login timed out; restart login")
    finally:
        path.unlink(missing_ok=True)


def main(argv=None):
    am_paths.enable_utf8_stdout()
    parser = argparse.ArgumentParser(description="Local NetEase login; never paste cookies into chat or command arguments")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("import", "qr"):
        sub = commands.add_parser(name)
        sub.add_argument("--save", action="store_true", help="Explicitly save locally (Windows current-user DPAPI)")
        sub.add_argument("--allow-plaintext", action="store_true", help="POSIX only: explicitly consent to mode-0600 plaintext storage")
    commands.add_parser("status").add_argument("--verify", action="store_true")
    commands.add_parser("forget").add_argument("--confirm", action="store_true")
    # Only an explicit login action may open the local QR page; never on MCP startup.
    commands.choices["qr"].add_argument("--open", action="store_true", help="Open the generated local QR page in your browser")
    args = parser.parse_args(argv)
    try:
        if args.command == "import":
            result = validate_and_save(hidden_cookie(), persist=args.save, allow_plaintext=args.allow_plaintext)
        elif args.command == "qr":
            result = qr_login(persist=args.save, allow_plaintext=args.allow_plaintext, open_browser=args.open)
        elif args.command == "forget":
            sessions.forget(confirm=args.confirm)
            result = {"forgotten": True, "note": "Local copy removed; revoke the old session in the official account settings separately"}
        else:
            result = sessions.describe()
            if args.verify:
                client = NeteaseClient()
                client.account_id()
                result["logged_in"] = True
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except NeteaseError as exc:
        print(json.dumps({"ok": False, "error": exc.public(), "note": "Login failed; re-import locally. No automatic retry."}), file=sys.stderr)
    except (sessions.SessionError, ValueError, OSError, EOFError):
        print("Login unavailable. Check local session, terminal, storage consent and loopback gateway; no credential details exposed.", file=sys.stderr)
    except KeyboardInterrupt:
        print("Login cancelled.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
