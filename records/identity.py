"""Identifier handling for the kiosk: normalise, mask, encrypt at rest (Fernet), keyed lookup hash (HMAC-SHA256), PIN hashing
(argon2id over a peppered input). Nothing here touches the network and nothing here logs.

Keys come from IDENTITY_MASTER_KEY (urlsafe base64, 32 bytes) or, when unset, a local key file `<data>/identity.key`
(0600, inside the gitignored data folder, created on first use). Two sub-keys are derived with HKDF so the lookup key and the
encryption key are never the same bytes."""
import base64
import hashlib
import hmac
import os
import re
import secrets
from pathlib import Path
from typing import Literal, Optional

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from . import store

IdType = Literal["mobile", "abha"]
_PH = PasswordHasher()          # argon2id, library defaults (m=64 MiB, t=3, p=4), random 16-byte salt per hash


class IdentifierError(ValueError):
    """The identifier has the wrong shape. The message is shown to the patient, so it names no value."""


# ------------------------------------------------------------------ normalise and mask
def normalise(kind: str, raw: str) -> str:
    """mobile -> '+91XXXXXXXXXX' (10 digits starting 6-9, optional +91/91/0 prefix). abha -> 14 digits.
    Format check only: nothing is verified against any registry (the kiosk is offline)."""
    digits = re.sub(r"[\s\-]", "", raw or "")
    if kind == "mobile":
        if digits.startswith("+91"):
            digits = digits[3:]
        elif len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]
        elif len(digits) == 11 and digits.startswith("0"):
            digits = digits[1:]
        if not re.fullmatch(r"[6-9]\d{9}", digits):
            raise IdentifierError("mobile_format")
        return "+91" + digits
    if kind == "abha":
        if not re.fullmatch(r"\d{14}", digits):
            raise IdentifierError("abha_format")
        return digits
    raise IdentifierError("unknown_type")


def mask(kind: str, normalised: str) -> str:
    """+91 ••••• ••321 and 91-••••-••••-1234. Only the last 3 (mobile) or 4 (ABHA) digits survive."""
    if kind == "mobile":
        return f"+91 ••••• ••{normalised[-3:]}"
    if kind == "abha":
        return f"{normalised[:2]}-••••-••••-{normalised[-4:]}"
    return "Walk-in (no number)"


# ------------------------------------------------------------------ keys
def _key_file() -> Path:
    return store.data_dir().parent / "identity.key"


def _master() -> bytes:
    env = os.environ.get("IDENTITY_MASTER_KEY", "").strip()
    if env:
        raw = base64.urlsafe_b64decode(env + "=" * (-len(env) % 4))
        if len(raw) < 32:
            raise RuntimeError("IDENTITY_MASTER_KEY must decode to at least 32 bytes")
        return raw
    p = _key_file()
    if p.exists():
        return base64.urlsafe_b64decode(p.read_text().strip())
    p.parent.mkdir(parents=True, exist_ok=True)
    raw = secrets.token_bytes(32)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(base64.urlsafe_b64encode(raw).decode())
    return raw


def _derive(purpose: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"medikiosk-identity-" + purpose).derive(_master())


def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(_derive(b"enc")))


# ------------------------------------------------------------------ encrypt, lookup
def lookup_hash(kind: str, normalised: str) -> str:
    return hmac.new(_derive(b"lookup"), f"{kind}:{normalised}".encode(), hashlib.sha256).hexdigest()


def encrypt(normalised: str) -> str:
    return _fernet().encrypt(normalised.encode()).decode()


def decrypt(token: str) -> Optional[str]:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None


# ------------------------------------------------------------------ PIN
PIN_RE = re.compile(r"\d{4}")


def valid_pin(pin: str) -> bool:
    return bool(PIN_RE.fullmatch(pin or ""))


def _pin_input(lookup: str, pin: str) -> bytes:
    """The pepper binds a PIN hash to its patient and to this installation, so a copied hash is useless elsewhere."""
    return hmac.new(_derive(b"pin"), f"{lookup}:{pin}".encode(), hashlib.sha256).digest()


def hash_pin(lookup: str, pin: str) -> str:
    return _PH.hash(_pin_input(lookup, pin))


def verify_pin(lookup: str, pin: str, stored: str) -> bool:
    try:
        return _PH.verify(stored, _pin_input(lookup, pin))
    except (VerificationError, InvalidHashError):
        return False


def temp_pin() -> str:
    return f"{secrets.randbelow(10000):04d}"
