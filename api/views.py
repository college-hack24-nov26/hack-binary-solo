"""Read models built from PatientRecord for the board and the patient panel. Display only: labels come from the graph and the
existing helpers (answer_label, vitals.abnormal, vitals.bmi); nothing clinical is computed here."""
from datetime import datetime
from functools import lru_cache
from typing import Optional

from intake.doctors import Doctor, doctor_for_login, load_doctors
from intake.engine import answer_label, recompute_path
from intake.models import Graph, load_graph
from ocr.config import load_settings
from ocr import session as ocr_session
from records.schema import PatientRecord
from records.vitals import abnormal, bmi


@lru_cache(maxsize=1)
def graph() -> Graph:
    return load_graph()


def _now() -> datetime:
    return datetime.now().astimezone()


def red_flags(rec: PatientRecord, lang: str = "en") -> list[dict]:
    g = graph()
    out = []
    for f in rec.redFlags:
        lines = [{"nodeId": n, "label": g.node(n).shortLabel or g.node(n).text.en, "answer": answer_label(g.node(n), v, lang)}
                 for n, v in f.triggeredBy.items()]
        out.append({"ruleId": f.ruleId, "severity": f.severity, "staffMessage": f.staffMessage, "patientMessage": f.patientMessage,
                    "draft": f.draft, "label": f.label, "triggeredBy": lines})
    return out


def answer_lines(rec: PatientRecord, lang: str = "en") -> list[dict]:
    g = graph()
    out = []
    for nid in recompute_path(g, rec.answers).path:
        if nid == "consent" or nid not in rec.answers:
            continue
        n = g.node(nid)
        out.append({"nodeId": nid, "label": n.shortLabel or n.text.en, "question": n.text.get(lang),
                    "answer": answer_label(n, rec.answers[nid], lang), "section": n.section})
    return out


def minutes_since(iso: str, now: Optional[datetime] = None) -> int:
    try:
        return max(0, int(((now or _now()) - datetime.fromisoformat(iso)).total_seconds() // 60))
    except ValueError:
        return 0


def board_row(rec: PatientRecord, me: Optional[Doctor] = None) -> dict:
    flags = red_flags(rec)
    d = rec.dosingInputs
    return {"token": rec.token, "queueNumber": rec.queueNumber, "status": rec.status, "ageYears": d.ageYears, "sex": d.sex,
            "complaint": rec.complaint.label, "complaintText": rec.complaint.text, "redFlags": flags,
            "urgent": any(f["severity"] == "urgent" for f in flags), "assignedDoctor": rec.assignedDoctor,
            "vitalsPresent": bool(rec.vitals and rec.vitals.any_measured()), "pendingScans": len(rec.pendingScans),
            "minutesWaiting": minutes_since(rec.createdAt), "createdAt": rec.createdAt, "updatedAt": rec.updatedAt,
            "mine": bool(me) and rec.assignedDoctor == me.id}


def board_sort_key(row: dict):
    """A doctor's own patients first (as the old doctor page did), then most urgent flags, most flags, longest unchanged
    (as the old staff board did). Staff rows are never "mine", so the staff board is urgent-first."""
    urgent = sum(1 for f in row["redFlags"] if f["severity"] == "urgent")
    return (not row["mine"], -urgent, -len(row["redFlags"]), row["updatedAt"])


def doctor_for(username: str) -> Optional[Doctor]:
    return doctor_for_login(username, load_doctors())


def _pending_meta(rec: PatientRecord) -> list[dict]:
    tmp = load_settings().tmp_dir
    out = []
    for p in rec.pendingScans:
        draft = p.get("draft") or {}
        out.append({"id": p["id"], "uploadedBy": p.get("uploadedBy", "?"), "uploadedAt": p.get("uploadedAt", ""),
                    "documentType": draft.get("documentType"), "documentDate": draft.get("documentDate"),
                    "items": len(draft.get("medications") or []) + len(draft.get("labResults") or []),
                    "imageAvailable": ocr_session.read(tmp, p["id"]) is not None})
    return out


def patient_view(rec: PatientRecord, role: str, lang: str = "en") -> dict:
    d = rec.dosingInputs
    v = rec.vitals
    mismatch = None
    if v and d.weightKg and v.weightKg and abs(d.weightKg - v.weightKg) / v.weightKg > 0.1:
        mismatch = f"Reported weight {d.weightKg:g} kg differs from measured {v.weightKg:g} kg. Use the measured value for dosing."
    out = {"token": rec.token, "status": rec.status, "createdAt": rec.createdAt, "updatedAt": rec.updatedAt, "language": rec.language,
           "queueNumber": rec.queueNumber, "queueDate": rec.queueDate, "finishedAt": rec.finishedAt,
           "complaint": rec.complaint.model_dump(), "dosingInputs": d.model_dump(), "redFlags": red_flags(rec, lang),
           "answers": answer_lines(rec, lang), "assignedDoctor": rec.assignedDoctor,
           "vitals": v.model_dump() if v else None, "abnormal": abnormal(v, d.ageYears) if v else {}, "bmi": bmi(v) if v else None,
           "weightMismatch": mismatch, "pendingScans": _pending_meta(rec), "timelineCount": len(rec.timeline), "role": role}
    if role == "doctor":
        out.update({"socrates": {k: (x.model_dump() if hasattr(x, "model_dump") else [l.model_dump() for l in x])
                                 for k, x in rec.socrates.items()},
                    "doctorNotes": rec.doctorNotes, "dosingChecks": [_check_line(c) for c in rec.dosingChecks],
                    "visitHistory": rec.visitHistory, "visitHistoryBy": rec.visitHistoryBy, "visitHistoryAt": rec.visitHistoryAt,
                    "intakeDurationSeconds": rec.intakeDurationSeconds, "fieldsCaptured": rec.fieldsCaptured,
                    "editedFields": rec.editedFields})
    return out


def _check_line(c) -> dict:
    """A confirmed dosage check for the Dosing record list. The stored engine result is not re-sent (it is in the audit log)."""
    return {"at": c.at, "doctorId": c.doctorId, "drug": c.drug, "indication": c.indication, "ruleId": c.ruleId, "status": c.status,
            "dataStatus": c.dataStatus, "overrideCategories": c.overrideCategories, "overrideReasons": c.overrideReasons,
            "acknowledgedItems": c.acknowledgedItems}


def text_color_on(hex_color: Optional[str]) -> Optional[str]:
    """White or ink text on a floor-line stripe, whichever has the higher WCAG contrast (pairs listed in docs/DESIGN.md 3.4)."""
    if not hex_color:
        return None

    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    bg = lum(hex_color)
    white = 1.05 / (bg + 0.05)
    ink = (bg + 0.05) / (lum("#14302D") + 0.05)
    return "#FFFFFF" if white >= ink else "#14302D"


def doctor_out(d: Doctor) -> dict:
    return {"id": d.id, "name": d.name, "specialty": d.specialty.model_dump(), "room": d.room,
            "floor": d.floor.model_dump() if d.floor else None, "lineColor": d.lineColor,
            "lineName": d.lineName.model_dump() if d.lineName else None, "lineTextColor": text_color_on(d.lineColor)}
