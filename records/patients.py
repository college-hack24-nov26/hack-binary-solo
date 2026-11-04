"""Patient identity records: one JSON file per patient in `<data>/patients/`, written like records/store (atomic replace) and,
by callers, under api.deps.WRITE_LOCK. Holds the encrypted identifier, its keyed lookup hash, the PIN hash, lockout state,
consent records and visit tokens. Never holds a plaintext identifier or PIN, and no name."""
import os
import re
import secrets
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from . import identity, store

PID_RE = re.compile(r"^PID-[A-Z2-7]{8}$")
LOCK_AFTER = 5
LOCK_SECONDS = 600


def _now() -> datetime:
    return datetime.now().astimezone()


class ConsentRecord(BaseModel):
    version: str
    language: str
    at: str
    kioskId: str
    agreed: bool
    covers: list[str] = []          # what the patient agreed to: identifier, answers, scans


class Patient(BaseModel):
    id: str
    identifierType: str                       # mobile | abha | walk_in
    identifierEnc: Optional[str] = None       # Fernet token of the normalised identifier; None for a walk-in awaiting staff
    lookupHash: Optional[str] = None          # HMAC-SHA256 of type:identifier
    masked: str
    pinHash: Optional[str] = None
    failedAttempts: int = 0
    lockedUntil: Optional[str] = None
    createdAt: str
    consents: list[ConsentRecord] = []
    visitIds: list[str] = []
    needsStaff: bool = False                  # walk-in chosen at the kiosk, to be completed at the desk


def new_id() -> str:
    return "PID-" + "".join(secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567") for _ in range(8))


def folder() -> Path:
    d = store.data_dir().parent / "patients"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path(pid: str) -> Path:
    if not PID_RE.match(pid):
        raise ValueError(f"bad patient id {pid!r}")
    return folder() / f"{pid}.json"


def save(p: Patient) -> None:
    path = _path(p.id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(p.model_dump_json(indent=1), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def load(pid: str) -> Optional[Patient]:
    try:
        path = _path(pid)
    except ValueError:
        return None
    return Patient.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None


def list_all() -> list[Patient]:
    out = []
    for f in sorted(folder().glob("PID-*.json")):
        try:
            out.append(Patient.model_validate_json(f.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001 - a half-written file must not break the staff page
            continue
    return out


def find_by_hash(lookup: str) -> Optional[Patient]:
    for p in list_all():
        if p.lookupHash and p.lookupHash == lookup:
            return p
    return None


def is_locked(p: Patient, now: Optional[datetime] = None) -> bool:
    return bool(p.lockedUntil and datetime.fromisoformat(p.lockedUntil) > (now or _now()))


def create(kind: str, normalised: Optional[str], pin: Optional[str], consent: Optional[ConsentRecord], needs_staff: bool = False) -> Patient:
    lookup = identity.lookup_hash(kind, normalised) if normalised else None
    p = Patient(id=new_id(), identifierType=kind if normalised else "walk_in", masked=identity.mask(kind, normalised) if normalised else identity.mask("walk_in", ""),
                identifierEnc=identity.encrypt(normalised) if normalised else None, lookupHash=lookup,
                pinHash=identity.hash_pin(lookup, pin) if (lookup and pin) else None,
                createdAt=_now().isoformat(timespec="seconds"), consents=[consent] if consent else [], needsStaff=needs_staff)
    save(p)
    return p
