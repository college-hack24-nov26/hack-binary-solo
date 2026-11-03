"""Append-only dosing audit log (JSONL, hash-chained so edits to past lines are detectable).
The repo had no audit log before this module; the existing tracked-edit pattern (PatientRecord.doctorEdits) is
mirrored by PatientRecord.dosingChecks. Quiz answers are never touched."""
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from records.store import data_dir

EVENTS = ("evaluate", "confirm", "override")


def log_path(base: Optional[Path] = None) -> Path:
    d = (base or data_dir().parent) / "audit"
    d.mkdir(parents=True, exist_ok=True)
    return d / "dosing_audit.jsonl"


def _last_hash(p: Path) -> str:
    if not p.exists() or p.stat().st_size == 0:
        return "0" * 64
    with p.open("rb") as fh:
        last = fh.read().splitlines()[-1]
    return json.loads(last)["hash"]


def write(event: str, *, token: str, doctor_id: str, drug: str, result: dict, inputs: dict, provenance: dict,
          override_reason: Optional[str] = None, now: Optional[datetime] = None, base: Optional[Path] = None,
          extra: Optional[dict] = None) -> dict:
    if event not in EVENTS:
        raise ValueError(event)
    p = log_path(base)
    entry = {"ts": (now or datetime.now().astimezone()).isoformat(timespec="seconds"), "event": event, "token": token,
             "doctor_id": doctor_id, "drug": drug, "indication": result.get("indication"), "status": result.get("status"),
             "override_reason": override_reason, "inputs": inputs, "provenance": provenance, "result": result,
             "engine_version": result.get("engine_version"), "formulary_version": result.get("formulary_version"),
             **(extra or {}), "prev": _last_hash(p)}
    body = json.dumps(entry, sort_keys=True, ensure_ascii=False)
    entry["hash"] = hashlib.sha256(body.encode()).hexdigest()
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return entry


def read(base: Optional[Path] = None) -> list:
    p = log_path(base)
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def verify(base: Optional[Path] = None) -> bool:
    prev = "0" * 64
    for e in read(base):
        h = e.pop("hash")
        if e["prev"] != prev or hashlib.sha256(json.dumps(e, sort_keys=True, ensure_ascii=False).encode()).hexdigest() != h:
            return False
        prev = h
    return True
