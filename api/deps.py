"""Shared dependencies: the process-wide write lock, server-side login sessions, role checks and the formulary gate.

One uvicorn worker only. Records are JSON files and the audit log is a hash chain whose `write()` reads the last hash and then
appends, so every request that writes a record or the audit log takes WRITE_LOCK. Endpoints that take it are plain `def`
(they run in the threadpool, never on the event loop)."""
import os
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Callable

from fastapi import Depends, HTTPException, Request

from dosing import formulary as fmod
from dosing.config import Config
from ocr import auth
from ocr.config import load_settings

WRITE_LOCK = threading.Lock()
COOKIE = "mk_session"
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "medikiosk"
KIOSK_HEADER = "x-kiosk-key"


def https_on() -> bool:
    return os.environ.get("HTTPS", "").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class User:
    username: str
    role: str
    last_seen: float


class SessionStore:
    """In-memory login sessions (a server restart signs everyone out). Idle sessions expire after OCR_AUTH_IDLE_S."""

    def __init__(self, idle_s: int, clock: Callable[[], float] = time.time):
        self.idle_s, self.clock = idle_s, clock
        self._s: dict[str, User] = {}
        self._lock = threading.Lock()

    def create(self, username: str, role: str) -> str:
        sid = secrets.token_urlsafe(32)
        with self._lock:
            self._s[sid] = User(username, role, self.clock())
        return sid

    def touch(self, sid: str | None) -> tuple[User | None, str]:
        """(user, reason). reason: ok | none | idle. A valid call refreshes last_seen."""
        if not sid:
            return None, "none"
        with self._lock:
            u = self._s.get(sid)
            if u is None:
                return None, "none"
            if auth.idle_expired(u.last_seen, self.idle_s, self.clock()):
                del self._s[sid]
                return None, "idle"
            u.last_seen = self.clock()
            return u, "ok"

    def drop(self, sid: str | None) -> None:
        with self._lock:
            self._s.pop(sid or "", None)


def current_user(request: Request) -> User:
    user, reason = request.app.state.sessions.touch(request.cookies.get(COOKIE))
    if user is None:
        msg = "Signed out after inactivity. Sign in again." if reason == "idle" else "Sign in to continue."
        raise HTTPException(401, msg, headers={"X-Auth-Reason": reason})
    return user


def require_role(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "Your role cannot use this. Ask a doctor.")
        return user
    return dep


staff_or_doctor = require_role("staff", "doctor")
doctor_only = require_role("doctor")


def authenticator(request: Request) -> auth.Authenticator:
    return request.app.state.authenticator


def make_authenticator() -> auth.Authenticator:
    s = load_settings()
    return auth.Authenticator(s.users_file, s.max_login_failures, s.lockout_s)


def dosing_formulary() -> tuple[fmod.Formulary, Config]:
    """The formulary and config, or 503 with a plain reason. Intake, the staff board and summaries never depend on this."""
    cfg = Config.from_env()
    try:
        return fmod.load(cfg.formulary_path), cfg
    except Exception as e:  # noqa: BLE001 - missing file, bad JSON or failed validation all mean "dosing unavailable"
        raise HTTPException(503, f"Dosing is unavailable: the formulary could not be loaded from {cfg.formulary_path.name} "
                                 f"({type(e).__name__}). Intake, the staff board and summaries still work.")


def formulary_status() -> tuple[bool, str | None]:
    cfg = Config.from_env()
    try:
        fmod.load(cfg.formulary_path)
        return True, None
    except Exception as e:  # noqa: BLE001
        return False, type(e).__name__
