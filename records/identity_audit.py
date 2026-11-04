"""Identity, consent, lock, PIN-reset and scan events in the existing hash-chained audit file.

dosing/audit.write only accepts the four dosing events and dosing/ is off limits, so this module appends to the SAME file with
the SAME chain recipe (it reuses dosing.audit's helpers unchanged). `audit.verify()` and the audit viewer therefore keep
working: the viewer shows these rows with the event name as the action and drug "-". Detail carries masked values and ids only,
never an identifier or a PIN. Callers hold api.deps.WRITE_LOCK."""
import json
import os
from datetime import datetime
from typing import Optional

from dosing import audit

SAFE_KEYS = {"patient", "masked", "type", "device", "reason", "scan", "count", "language", "version", "visit", "until", "attempts", "agreed"}


def write(event: str, *, actor: str, token: str = "", **detail) -> dict:
    bad = set(detail) - SAFE_KEYS
    if bad:
        raise ValueError(f"audit detail keys not allowed: {sorted(bad)}")
    p = audit.log_path()
    entry = {"ts": datetime.now().astimezone().isoformat(timespec="seconds"), "event": event, "token": token, "doctor_id": actor,
             "drug": "-", "indication": None, "status": "-", "override_reason": None, "inputs": {}, "provenance": {},
             "result": {}, "engine_version": None, "formulary_version": None, "detail": detail, "prev": audit._last_hash(p)}
    entry["hash"] = audit._digest(entry)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return entry
