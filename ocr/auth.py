"""Local, offline authentication. Users live in a JSON file with salted scrypt hashes.
No passwords, hashes or usernames are logged. Roles: doctor, staff."""
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

ROLES = {"doctor", "staff"}
_N, _R, _P = 2 ** 14, 8, 1
_DUMMY = None  # hash verified for unknown users so timing does not reveal valid usernames


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${h.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, h = stored.split("$")
        calc = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(calc, bytes.fromhex(h))
    except (ValueError, TypeError):
        return False


def _load(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def add_user(path: Path, username: str, password: str, role: str) -> None:
    username = username.strip().lower()
    if role not in ROLES:
        raise ValueError(f"role must be one of {sorted(ROLES)}")
    if not username or len(password) < 8:
        raise ValueError("username required and password must be at least 8 characters")
    users = _load(path)
    if username in users:
        raise ValueError("user already exists")
    users[username] = {"role": role, "hash": hash_password(password)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(users, indent=1))
    os.chmod(path, 0o600)


def has_users(path: Path) -> bool:
    return bool(_load(path))


class Authenticator:
    """Verifies credentials with per-username lockout after repeated failures."""

    def __init__(self, users_file: Path, max_failures: int = 5, lockout_s: int = 60, clock=time.time):
        self.users_file, self.max_failures, self.lockout_s, self.clock = users_file, max_failures, lockout_s, clock
        self._fails: dict[str, tuple[int, float]] = {}

    def login(self, username: str, password: str) -> tuple[dict | None, str]:
        """Returns (user, message). user = {"username", "role"} on success."""
        global _DUMMY
        u = username.strip().lower()
        count, until = self._fails.get(u, (0, 0.0))
        if until > self.clock():
            return None, f"Too many failed attempts. Try again in {int(until - self.clock()) + 1}s."
        rec = _load(self.users_file).get(u)
        if _DUMMY is None:
            _DUMMY = hash_password("dummy-password")
        ok = verify_password(password, rec["hash"] if rec else _DUMMY)
        if rec and ok and rec.get("role") in ROLES:
            self._fails.pop(u, None)
            return {"username": u, "role": rec["role"]}, "ok"
        count += 1
        if count >= self.max_failures:
            self._fails[u] = (0, self.clock() + self.lockout_s)
        else:
            self._fails[u] = (count, 0.0)
        return None, "Invalid username or password."


def idle_expired(last_seen: float, idle_s: int, now: float | None = None) -> bool:
    return (now or time.time()) - last_seen > idle_s
