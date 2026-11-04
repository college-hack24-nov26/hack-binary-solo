"""Kiosk step 2: the patient scans old papers. Needs BOTH the visit's kiosk key and the signed-in patient's identity token, and the
visit must belong to that patient. Everything returned is labelled unverified: the patient confirms what the camera read, a doctor
decides what to use (api/routers/doctor_visits.py). Polling GET /{id} is the progress stream (EventSource cannot send our headers)."""
import os
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile

from records import identity_audit, patients, scanfiles, store

from .. import scan_jobs
from ..deps import WRITE_LOCK
from ..kiosk_identity import IdSession, require_identity, visit_patient
from ..schemas_identity import ScanEditIn, ScanOut, ScansOut
from .kiosk import kiosk_session

router = APIRouter(prefix="/api/kiosk/sessions/{token}/scans", tags=["kiosk scans"])
MAX_BYTES = 15 * 1024 * 1024


def scan_context(token: str, request: Request, _s=Depends(kiosk_session), ident=Depends(require_identity)):
    rec = visit_patient(request, token, ident)
    p = patients.load(rec.patientId)
    if p is None or p.identifierType == "walk_in":
        raise HTTPException(403, "Please ask staff about scanning your papers.", headers={"X-Error-Code": "walkin_no_scans"})
    return rec


def out(e: dict) -> dict:
    stage, prog, el = scan_jobs.progress_of(e)
    return {"id": e["id"], "status": e["status"], "stage": stage, "progress": prog, "elapsedS": el, "docType": e.get("docType"),
            "docDate": e.get("docDate"), "medicines": e.get("medicines") or [], "freeText": e.get("freeText") or "",
            "confirmed": bool(e.get("confirmed")), "hasImage": bool(e.get("imageKept")), "message": e.get("message")}


def _find(rec, sid: str) -> dict:
    for s in rec.kioskScans:
        if s["id"] == sid:
            return s
    raise HTTPException(404, "That paper is not here any more.")


@router.post("", response_model=ScanOut, summary="Add a photo of a paper; reading starts in the background")
def upload(token: str, request: Request, image: UploadFile = File(...), rec=Depends(scan_context)):
    data = image.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "The picture is too big. Take it again.", headers={"X-Error-Code": "too_big"})
    if len(rec.kioskScans) >= 10:
        raise HTTPException(409, "That is enough papers for one visit. Please ask staff.", headers={"X-Error-Code": "too_many"})
    e = scan_jobs.submit(request.app, token, data, lambda: None)
    return out({k: v for k, v in e.items() if k != "_transient"})


@router.get("", response_model=ScansOut)
def list_scans(token: str, rec=Depends(scan_context)):
    return {"scans": [out(s) for s in rec.kioskScans]}


@router.get("/{sid}", response_model=ScanOut, summary="Status, real progress and what was read")
def get_scan(token: str, sid: str, rec=Depends(scan_context)):
    return out(_find(rec, sid))


@router.get("/{sid}/image", response_class=Response)
def image(token: str, sid: str, rec=Depends(scan_context)):
    e = _find(rec, sid)
    img = scanfiles.read(sid) if e.get("imageKept") else None
    if img is None:
        raise HTTPException(404, "No picture.")
    return Response(img, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


def _mutate(token: str, sid: str, fn):
    with WRITE_LOCK:
        rec = store.load(token)
        e = _find(rec, sid)
        new = fn(e)
        store.save(rec.model_copy(update={"kioskScans": [new if s["id"] == sid else s for s in rec.kioskScans]}))
        return new


@router.patch("/{sid}", response_model=ScanOut, summary="The patient corrects the text")
def correct(token: str, sid: str, body: ScanEditIn, rec=Depends(scan_context)):
    def fn(e):
        if e["status"] in scan_jobs.RUNNING:
            raise HTTPException(409, "Still reading. Please wait.")
        if e.get("confirmed"):
            raise HTTPException(409, "Already confirmed.")
        e = dict(e)
        if body.docType is not None:
            e["docType"] = body.docType
        if body.docDate is not None:
            e["docDate"] = {"value": body.docDate.strip() or None, "confidence": None, "check": False}
        if body.medicines is not None:
            f = lambda v: {"value": (v or "").strip()[:120] or None, "confidence": None, "check": False}      # noqa: E731
            e["medicines"] = [{"name": f(m.get("name")), "dose": f(m.get("dose")), "frequency": f(m.get("frequency"))}
                              for m in body.medicines if (m.get("name") or "").strip()]
        if body.freeText is not None:
            e["freeText"] = body.freeText.strip()
        e["patientEdited"] = True
        return e
    return out(_mutate(token, sid, fn))


@router.post("/{sid}/confirm", response_model=ScanOut, summary='"This is right": the paper is kept for the doctor, still marked unverified')
def confirm(token: str, sid: str, request: Request, rec=Depends(scan_context)):
    def fn(e):
        if e["status"] in scan_jobs.RUNNING:
            raise HTTPException(409, "Still reading. Please wait.")
        e = {**e, "confirmed": True}
        if os.environ.get("KIOSK_SCAN_KEEP_IMAGE", "1").strip().lower() in ("0", "false", "no", "off") and e["status"] != "unavailable":
            scanfiles.delete(sid)
            e["imageKept"] = False
        return e
    new = _mutate(token, sid, fn)
    with WRITE_LOCK:
        identity_audit.write("scan.confirmed", actor="kiosk", token=token, scan=sid, count=len(new.get("medicines") or []))
    request.app.state.events.publish("patient.updated", {"token": token})
    return out(new)


@router.delete("/{sid}", status_code=204, summary="Remove a paper and its picture")
def delete(token: str, sid: str, request: Request, rec=Depends(scan_context)):
    with WRITE_LOCK:
        r = store.load(token)
        _find(r, sid)
        scanfiles.delete(sid)
        scan_jobs.LIVE.pop(sid, None)
        store.save(r.model_copy(update={"kioskScans": [s for s in r.kioskScans if s["id"] != sid]}))
        identity_audit.write("scan.deleted", actor="kiosk", token=token, scan=sid)
    request.app.state.events.publish("patient.updated", {"token": token})
    return Response(status_code=204)
