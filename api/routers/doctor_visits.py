"""Doctor view of what the patient scanned at the kiosk, and the one action that lets it near the dosage check.

Scanned text is patient-supplied and UNVERIFIED. It never feeds the engine by itself: "Use as current medicines" writes a timeline
entry that carries the doctor's name (`confirmedBy`) and a provenance on every item, which is exactly what dosing/ocr_meds.py
already reads. dosing/ is not changed."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from records import identity_audit, patients, scanfiles, store
from records.schema import TimelineEntry

from ..deps import WRITE_LOCK, User, doctor_only
from ..schemas_identity import DoctorScansOut, PreviousVisitsOut, UseMedicinesOut
from .patients import load_or_404

router = APIRouter(prefix="/api/doctor/visits/{token}", tags=["doctor papers"])
PROVENANCE = "patient_scan_unverified_doctor_used"


def _flat(s: dict) -> dict:
    v = lambda f: (f or {}).get("value")                                           # noqa: E731
    return {"id": s["id"], "uploadedAt": s["uploadedAt"], "docType": s.get("docType"), "docDate": v(s.get("docDate")),
            "medicines": [{"name": v(m["name"]), "dose": v(m["dose"]), "frequency": v(m["frequency"]),
                           "lowConfidence": bool(m["name"].get("check") or m["dose"].get("check") or m["frequency"].get("check"))}
                          for m in s.get("medicines") or []],
            "freeText": s.get("freeText") or "", "confirmedByPatient": bool(s.get("confirmed")), "hasImage": bool(s.get("imageKept")),
            "usedByDoctor": s.get("usedBy")}


@router.get("/scans", response_model=DoctorScansOut, summary="Papers the patient scanned (images and unverified text)")
def scans(token: str, _: User = Depends(doctor_only)):
    rec = load_or_404(token)
    return {"visit": token, "patientMasked": rec.identifierMasked,
            "scans": [_flat(s) for s in rec.kioskScans if s.get("confirmed") or s.get("status") == "unavailable"]}


@router.get("/scans/{sid}/image", response_class=Response)
def scan_image(token: str, sid: str, _: User = Depends(doctor_only)):
    rec = load_or_404(token)
    e = next((s for s in rec.kioskScans if s["id"] == sid), None)
    img = scanfiles.read(sid) if e and e.get("imageKept") else None
    if img is None:
        raise HTTPException(404, "No picture was kept for this paper.")
    return Response(img, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/scans/{sid}/use-as-current-medicines", response_model=UseMedicinesOut)
def use_as_current_medicines(token: str, sid: str, request: Request, user: User = Depends(doctor_only)):
    with WRITE_LOCK:
        rec = load_or_404(token)
        e = next((s for s in rec.kioskScans if s["id"] == sid), None)
        if e is None:
            raise HTTPException(404, "No such paper for this visit.")
        if e.get("usedBy"):
            raise HTTPException(409, "This paper was already used.")
        items = [{"nameAsWritten": m["name"]["value"], "strength": m["dose"].get("value"), "frequencyAsWritten": m["frequency"].get("value"),
                  "provenance": PROVENANCE, "scanId": sid}
                 for m in e.get("medicines") or [] if m["name"].get("value")]
        if not items:
            raise HTTPException(409, "There are no medicines on this paper.")
        entry = TimelineEntry.model_validate({
            "date": (e.get("docDate") or {}).get("value") or date.today().isoformat(), "type": "prescription", "items": items, "diagnoses": [],
            "source": "ocr", "editedByDoctor": False, "editedFields": [], "confirmedBy": user.username, "provenance": PROVENANCE})
        scans_ = [{**s, "usedBy": user.username} if s["id"] == sid else s for s in rec.kioskScans]
        store.save(rec.model_copy(update={"timeline": rec.timeline + [entry], "kioskScans": scans_}))
        identity_audit.write("doctor.use_as_current_medicines", actor=user.username, token=token, scan=sid, count=len(items))
    request.app.state.events.publish("patient.updated", {"token": token})
    return {"added": len(items), "scan": sid}


@router.get("/previous", response_model=PreviousVisitsOut, summary="Earlier visits of a returning patient")
def previous(token: str, _: User = Depends(doctor_only)):
    rec = load_or_404(token)
    p = patients.load(rec.patientId) if rec.patientId else None
    out = []
    for v in (p.visitIds if p else []):
        if v == token:
            continue
        try:
            r = store.load(v)
        except ValueError:
            continue
        if r is not None and r.queueNumber:
            out.append({"token": v, "date": r.queueDate or r.createdAt[:10], "complaint": r.complaint.label or r.complaint.text, "queueNumber": r.queueNumber})
    out.sort(key=lambda x: x["date"], reverse=True)
    return {"visits": out}
