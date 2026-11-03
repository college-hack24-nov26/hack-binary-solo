"""Read-only helpers for the audit-log viewer: flatten, filter, export. Never writes to the log."""
import csv
import io
import json
from datetime import date

ACTIONS = {"evaluate": "evaluated", "confirm": "confirmed", "override": "override", "history": "history-check answered"}
CSV_COLUMNS = ["time", "doctor", "patient", "drug", "status", "action", "override_category", "override_reason", "hash"]


def rows(entries: list) -> list[dict]:
    """Newest first. `index` is the line number in the log (ties inside one second keep log order, newest line first)."""
    out = []
    for i, e in enumerate(entries):
        out.append({"index": i, "time": e["ts"], "doctor": e.get("doctor_id"), "patient": e.get("token"), "drug": e.get("drug"),
                    "status": e.get("status"), "action": ACTIONS.get(e["event"], e["event"]), "event": e["event"],
                    "override_category": e.get("override_category"), "override_reason": e.get("override_reason"),
                    "hash": e.get("hash"), "entry": e})
    return sorted(out, key=lambda r: (r["time"], r["index"]), reverse=True)


def _day(ts: str) -> date:
    return date.fromisoformat(ts[:10])


def filter_rows(rs: list[dict], patient: str | None = None, drug: str | None = None, action: str | None = None,
                start: date | None = None, end: date | None = None) -> list[dict]:
    out = []
    for r in rs:
        if patient and r["patient"] != patient:
            continue
        if drug and r["drug"] != drug:
            continue
        if action and r["action"] != action:
            continue
        d = _day(r["time"])
        if (start and d < start) or (end and d > end):
            continue
        out.append(r)
    return out


def to_json(rs: list[dict]) -> str:
    """The stored entries exactly as written (hash and prev included), in the order shown."""
    return json.dumps([r["entry"] for r in rs], indent=1, ensure_ascii=False, sort_keys=True)


def to_csv(rs: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in rs:
        w.writerow({c: ("" if r.get(c) is None else r[c]) for c in CSV_COLUMNS})
    return buf.getvalue()


def detail(entry: dict) -> dict:
    """The parts of a stored entry the expander shows."""
    res = entry.get("result") or {}
    return {"inputs": entry.get("inputs") or {}, "provenance": entry.get("provenance") or {},
            "calculation_steps": res.get("calculation_steps") or [], "warnings": [w.get("text") for w in res.get("warnings") or []],
            "interactions": [i.get("text") for i in res.get("interactions") or []], "blocks": [b.get("text") for b in res.get("blocks") or []],
            "sources": res.get("sources") or [], "override_category": entry.get("override_category"),
            "override_reason": entry.get("override_reason"), "overridden_block": entry.get("overridden_block"),
            "overrides": res.get("overrides") or []}
