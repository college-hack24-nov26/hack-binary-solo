"""Kiosk identity sessions, rate limits and the dependency that guards identity-only kiosk endpoints.

The identity token is `<random id>.<HMAC>`: the HMAC makes forged ids fail without a lookup, the server-side entry holds
{patient id, last seen} and expires after IDENTITY_SESSION_IDLE_S (default 15 min) of no use. It travels in the
`X-Kiosk-Identity` header, never a cookie (nothing on a shared tablet persists), and it is only ever accepted by
/api/kiosk/* routes: staff and doctor routes read the login cookie, so this token opens none of them."""
import hashlib
import hmac
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Optional

from fastapi import Header, HTTPException, Request

from records import identity, store

IDENTITY_HEADER = "x-kiosk-identity"
DEVICE_HEADER = "x-kiosk-device"


def idle_s() -> int:
    try:
        return max(30, int(os.environ.get("IDENTITY_SESSION_IDLE_S", "900")))
    except ValueError:
        return 900


def device_limit() -> int:
    try:
        return max(5, int(os.environ.get("IDENTITY_DEVICE_RATE", "30")))
    except ValueError:
        return 30


@dataclass
class IdSession:
    patient_id: str
    last_seen: float
    visit: Optional[str] = None


class IdentitySessions:
    def __init__(self, clock=time.time):
        self.clock = clock
        self._s: dict[str, IdSession] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _sig(jti: str) -> str:
        return hmac.new(identity._derive(b"session"), jti.encode(), hashlib.sha256).hexdigest()[:32]

    def issue(self, patient_id: str) -> str:
        jti = secrets.token_urlsafe(24)
        with self._lock:
            self._s[jti] = IdSession(patient_id, self.clock())
        return f"{jti}.{self._sig(jti)}"

    def touch(self, token: Optional[str]) -> Optional[tuple[str, IdSession]]:
        if not token or "." not in token:
            return None
        jti, sig = token.rsplit(".", 1)
        if not hmac.compare_digest(sig, self._sig(jti)):
            return None
        with self._lock:
            s = self._s.get(jti)
            if s is None:
                return None
            if self.clock() - s.last_seen > idle_s():
                del self._s[jti]
                return None
            s.last_seen = self.clock()
            return jti, s

    def drop(self, token: Optional[str]) -> None:
        if token and "." in token:
            with self._lock:
                self._s.pop(token.rsplit(".", 1)[0], None)


class RateLimiter:
    """Sliding window per key. In memory: a restart clears it, but the 10-minute PIN lock is persisted on the patient."""

    def __init__(self, clock=time.time):
        self.clock = clock
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_s: int) -> bool:
        now = self.clock()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window_s:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True


def device_id(request: Request, header: Optional[str]) -> str:
    return (header or "")[:64] or (request.client.host if request.client else "unknown")


def check_rate(request: Request, device: str, lookup: Optional[str]) -> None:
    rl: RateLimiter = request.app.state.rate
    if not rl.allow(f"dev:{device}", device_limit(), 300) or (lookup and not rl.allow(f"id:{lookup}", 10, 60)):
        raise HTTPException(429, "Too many tries. Please wait a minute or ask staff.", headers={"X-Error-Code": "rate_limited", "Retry-After": "60"})


def require_identity(request: Request, x_kiosk_identity: Optional[str] = Header(None)) -> tuple[str, IdSession]:
    got = request.app.state.identity_sessions.touch(x_kiosk_identity)
    if got is None:
        raise HTTPException(401, "Please sign in again.", headers={"X-Error-Code": "identity_expired"})
    return got


def visit_patient(request: Request, token: str, ident: tuple[str, IdSession]):
    """The visit record for `token`, only if it belongs to the signed-in patient. Another patient's visit looks like it does not exist."""
    rec = store.load(token)
    if rec is None or not rec.patientId or rec.patientId != ident[1].patient_id:
        raise HTTPException(404, "This visit is not available.")
    return rec
