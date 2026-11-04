"""Read-only audit log (doctor only). No endpoint here can edit or delete an entry. The parsed log is cached by file size and
mtime because it is already about 10 MB."""
import hashlib
import json
import threading
from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from dosing import audit, audit_view

from ..deps import doctor_only
from ..schemas import AuditDetail, AuditPage, AuditVerify

router = APIRouter(prefix="/api/audit", tags=["audit"], dependencies=[Depends(doctor_only)])


class _Cache:
    def __init__(self):
        self._key = None
        self._val: dict = {}
        self._lock = threading.Lock()

    def get(self) -> dict:
        p = audit.log_path()
        st = p.stat() if p.exists() else None
        key = (str(p), st.st_size, st.st_mtime_ns) if st else (str(p), 0, 0)
        with self._lock:
            if key != self._key:
                entries = audit.read()
                rows = audit_view.rows(entries)
                self._val = {"entries": entries, "rows": rows, "verify": _verify(entries),
                             "facets": {"patients": sorted({r["patient"] for r in rows if r["patient"]}),
                                        "drugs": sorted({r["drug"] for r in rows if r["drug"] and r["drug"] != "-"}),
                                        "actions": list(audit_view.ACTIONS.values())}}
                self._key = key
            return self._val


CACHE = _Cache()


def _digest(entry: dict) -> str:
    # same recipe as dosing.audit._digest (sorted-key JSON, SHA-256), restated here so the viewer can name the first bad line
    return hashlib.sha256(json.dumps(entry, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _verify(entries: list) -> dict:
    prev = "0" * 64
    for i, e in enumerate(entries):
        e = dict(e)
        h = e.pop("hash", None)
        if e.get("prev") != prev or _digest(e) != h:
            return {"ok": False, "entries": len(entries), "firstBadIndex": i}
        prev = h
    return {"ok": True, "entries": len(entries), "firstBadIndex": None}


def _day(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise HTTPException(422, f"Use a date like 2026-11-04, not {s!r}.")


def _filtered(patient, drug, action, from_, to) -> tuple[list, dict]:
    c = CACHE.get()
    return audit_view.filter_rows(c["rows"], patient or None, drug or None, action or None, _day(from_), _day(to)), c


def _row(r: dict) -> dict:
    return {"index": r["index"], "time": r["time"], "doctor": r["doctor"], "patient": r["patient"], "drug": r["drug"],
            "status": r["status"], "action": r["action"], "event": r["event"], "overrideCategory": r["override_category"],
            "overrideReason": r["override_reason"], "hash": r["hash"], "prev": r["entry"].get("prev")}


@router.get("", response_model=AuditPage)
def page(cursor: Optional[str] = None, limit: int = Query(50, ge=1, le=200), patient: Optional[str] = None,
         drug: Optional[str] = None, action: Optional[str] = None, from_: Optional[str] = Query(None, alias="from"),
         to: Optional[str] = None):
    rows, c = _filtered(patient, drug, action, from_, to)
    try:
        start = int(cursor) if cursor else 0
    except ValueError:
        raise HTTPException(422, "Bad cursor.")
    chunk = rows[start:start + limit]
    nxt = start + limit if start + limit < len(rows) else None
    return {"rows": [_row(r) for r in chunk], "nextCursor": str(nxt) if nxt is not None else None, "total": len(rows),
            "totalAll": len(c["rows"]), "facets": c["facets"]}


@router.get("/verify", response_model=AuditVerify)
def verify():
    return CACHE.get()["verify"]


@router.get("/entries/{index}", response_model=AuditDetail)
def entry(index: int):
    entries = CACHE.get()["entries"]
    if not 0 <= index < len(entries):
        raise HTTPException(404, "No audit entry at that position.")
    e = entries[index]
    return {"index": index, "hash": e.get("hash"), "prev": e.get("prev"), "detail": audit_view.detail(e)}


@router.get("/export")
def export(format: Literal["json", "csv"] = "json", patient: Optional[str] = None, drug: Optional[str] = None,
           action: Optional[str] = None, from_: Optional[str] = Query(None, alias="from"), to: Optional[str] = None):
    rows, _ = _filtered(patient, drug, action, from_, to)
    if format == "csv":
        return Response(audit_view.to_csv(rows), media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="audit_log.csv"'})
    return Response(audit_view.to_json(rows), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="audit_log.json"'})
