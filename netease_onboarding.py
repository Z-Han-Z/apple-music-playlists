"""Conversation-first setup facts and explicit local QR handoff; no application UI.

The host LLM guides the user. Only an approved nc_login start launches a private
helper. QR keys/images/URLs/cookies and helper output never enter MCP content.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import uuid
from pathlib import Path

import am_paths
import netease_session as sessions


def supports_managed_login():
    return os.name == "nt" and platform.machine().lower() in {"amd64", "x86_64"}


def local_bundle():
    value = os.environ.get("NETEASE_LOGIN_BUNDLE", "")
    if not value:
        raise ValueError("managed-login-not-configured")
    root = Path(value)
    if not root.is_absolute() or root.is_symlink():
        raise ValueError("invalid-login-bundle")
    body = json.loads((root / "bundle.json").read_text(encoding="utf-8"))
    if not isinstance(body, dict):
        raise ValueError("invalid-login-bundle")
    spec = body.get("qr")
    if body.get("version") != am_paths.VERSION or not isinstance(spec, dict) or spec.get("platform") != "win-x64":
        raise ValueError("login-bundle-version-or-platform")
    helper = root / "bootstrap.py"
    digest = spec.get("bootstrap_sha256", "")
    if (helper.is_symlink() or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)
            or hashlib.sha256(helper.read_bytes()).hexdigest() != digest):
        raise ValueError("login-helper-integrity")
    return root, body


def setup_facts():
    """Offline facts only. A saved session is not proof of a valid account login."""
    try:
        local_bundle()
        managed = supports_managed_login()
        bundle_state = "configured" if managed else "unsupported-platform"
    except (OSError, ValueError, TypeError):
        managed, bundle_state = False, "missing-or-invalid"
    try:
        saved = sessions.describe()["saved"]
    except (OSError, sessions.SessionError):
        saved = None
    return {
        "status": "setup-facts", "interface": "MCP stdio; conversation in the host, no standalone application",
        "local_session_present": saved, "login_verified": None,
        "writes_enabled": os.environ.get("NETEASE_ENABLE_WRITES") == "1",
        "managed_qr_available": managed, "login_bundle": bundle_state,
        "next_actions": ["Explain these facts in the user's language; do not present a fixed app/menu.",
                         "Call nc_status to verify login when the user requests account setup/use.",
                         "If login is needed, explain local encrypted storage and ask permission before nc_login(action=start, confirm=true).",
                         "After authorization, poll nc_login(action=status), then call nc_status; never infer success from showing a QR.",
                         "Ask for a playlist brief only after addressing the user's setup question; public search remains available without login."],
        "privacy": "Never request a password, cookie, MUSIC_U, QR image/key/URL or session file in chat. QR is displayed only in the local browser.",
        "client_setup": "A host must connect this stdio server before it can call tools. The ZIP installer only generates config; it never edits a client.",
        "fallback": "If the managed bundle is unavailable, explain local install/config repair or hidden nc-login import --save outside chat; never request credentials as tool arguments.",
    }


def guidance(state):
    if state.get("logged_in") is True:
        return {"stage": "ready-for-preview", "next_action": "Ask what the user wants to curate; keep their words authoritative and preview first.",
                "writes": "Already opt-in enabled; each write still needs explicit approval." if state.get("writes_enabled") else
                          "Readonly. Explain host write opt-in only if the user requests a real playlist write; do not require it to preview."}
    kind = (state.get("error") or {}).get("kind")
    if kind == "network" or (state.get("cookie_configured") and kind not in {"login-expired", "login-required", "local-session-unavailable"}):
        return {"stage": "verification-unavailable", "next_action": "Explain network/API verification failure. Check connectivity and retry nc_status before proposing another login.",
                "note": "An unavailable check is not proof that the session expired. Never repeatedly scan automatically."}
    return {"stage": "login-needed", "next_action": "Explain the login requirement, offer public-only preview, or request approval for nc_login start. Guide in conversation, not an app.",
            "privacy": "Keep authentication in the local browser/official app; never ask for secrets or QR material in chat."}


class LoginHandoff:
    def __init__(self):
        self.process = None
        self.job_id = None
        self.cancel_requested = False

    def status(self, job_id=None):
        if job_id is not None and job_id != self.job_id:
            return {"status": "unknown-job", "next_action": "Call nc_status to inspect current login. Jobs belong to this MCP process; do not automatically start another QR."}
        if self.process is None:
            return {"status": "not-started", "next_action": "Explain login and ask the user before starting local QR authorization."}
        code = self.process.poll()
        phase = ("cancelling" if self.cancel_requested else "pending") if code is None else (
            "cancelled" if self.cancel_requested else "verified" if code == 0 else "not-completed")
        return {"status": phase, "job_id": self.job_id,
                "login_verified": phase == "verified", "helper_stopped": code is not None,
                "next_action": "Ask the user to scan/confirm in the local browser and poll status without starting another login." if phase == "pending" else
                               "Wait for the helper to stop; local cancellation does not revoke an already-approved server session." if phase == "cancelling" else
                               "Call nc_status. If verification failed, inspect connectivity/session before deciding with the user whether to restart.",
                "privacy": "No QR image/key/URL, cookie, session file or raw helper output is returned to the host."}

    def start(self, *, confirm=False, restart=False):
        if confirm is not True:
            return {"status": "approval-required", "next_action": "Ask permission to open local QR, verify the account and save an encrypted local session; only then pass confirm=true."}
        if self.process is not None and (self.process.poll() is None or not restart):
            return {**self.status(), "reused_job": True,
                    "note": "No second login started. Restart requires a new user decision and restart=true after checking nc_status."}
        try:
            root, body = local_bundle()
            if not supports_managed_login():
                raise ValueError("unsupported-platform")
            env = dict(os.environ)
            for name in ("NETEASE_COOKIE", "NETEASE_CSRF", "NETEASE_API_URL"):
                env[name] = ""
            env["NETEASE_ENABLE_WRITES"] = "0"
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            for name in ("NODE_OPTIONS", "NODE_PATH", "NETEASE_GATEWAY_DIAGNOSTICS", "APPLE_MUSIC_USER_TOKEN"):
                env.pop(name, None)
            process = subprocess.Popen([sys.executable, "-I", str(root / "bootstrap.py"), "qr-chat"],
                                       cwd=root, env=env, stdin=subprocess.PIPE,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       text=True, encoding="utf-8",
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, ValueError, TypeError):
            return {"status": "setup-required", "is_error": True,
                    "next_action": "Explain that managed login is unavailable. Repair the complete ZIP installation/config or use hidden local import; no secret should enter chat."}
        self.process, self.job_id, self.cancel_requested = process, uuid.uuid4().hex, False
        return self.status()

    def cancel(self, job_id=None):
        if job_id is not None and job_id != self.job_id:
            return self.status(job_id)
        if self.process is not None and self.process.poll() is None:
            self.cancel_requested = True
            try:
                self.process.stdin.write("CANCEL\n")
                self.process.stdin.flush()
            except (OSError, ValueError):
                pass
        return self.status()

    def close(self):
        self.cancel()
        if self.process is not None:
            if self.process.stdin:
                try:
                    self.process.stdin.close()
                except OSError:
                    pass
            try:
                self.process.wait(timeout=55)
            except subprocess.TimeoutExpired:
                # Do not kill the helper parent and orphan an in-flight account child.
                # Parent EOF is its cancellation signal; its bounded child/gateway timeouts remain active.
                pass


LOGIN = LoginHandoff()
