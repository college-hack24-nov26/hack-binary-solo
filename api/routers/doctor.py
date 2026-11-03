"""Doctor-only patient work: the deterministic summary with edit tracking, notes, and scan confirmation."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from intake import llm_summary
from intake.summary import apply_doctor_edits, build_summary, duration_text, template_paragraph
from ocr import session as ocr_session
from ocr.config import load_settings
from ocr.timeline import edited_fields, to_timeline_entry
from records import store
from records.schema import TimelineEntry

from ..deps import WRITE_LOCK, User, doctor_only, staff_or_doctor
from ..schemas import NotesIn, NotesOut, Paragraph, ScanConfirmIn, SummaryOut, SummaryPatch, Timeline
from .patients import load_or_404

router = APIRouter(prefix="/api/patients/{token}", tags=["doctor"])


def _summary(rec, lang: str) -> dict:
    s = build_summary(rec, lang)
    return {**s.model_dump(), "lang": lang, "durationText": duration_text(s.intakeDurationSeconds), "paragraph": template_paragraph(s)}


@router.get("/summary", response_model=SummaryOut)
def summary(token: str, lang: str = "en", _: User = Depends(doctor_only)):
    return _summary(load_or_404(token), lang if lang in ("en", "hi", "mr") else "en")


@router.patch("/summary", response_model=SummaryOut)
def edit_summary(token: str, body: SummaryPatch, request: Request, _: User = Depends(doctor_only)):
    with WRITE_LOCK:
        rec = load_or_404(token)
        try:
            rec = apply_doctor_edits(rec, body.values, datetime.now().astimezone(), body.lang)
        except KeyError as e:
            raise HTTPException(422, str(e).strip("'\""))
        store.save(rec)
    request.app.state.events.publish("patient.updated", {"token": token})
    return _summary(rec, body.lang)


@router.post("/summary/paragraph", response_model=Paragraph)
def paragraph(token: str, lang: str = "en", _: User = Depends(doctor_only)):
    """Optional local-model paragraph (off unless asked). Falls back to the template with the reason, as the Streamlit toggle did."""
    res = llm_summary.draft_paragraph(build_summary(load_or_404(token), lang), enabled=True)
    return {"source": res.source, "text": res.text, "reason": getattr(res, "reason", None),
            "label": llm_summary.LABEL if res.source == "ai-drafted" else None}


@router.put("/notes", response_model=NotesOut)
def notes(token: str, body: NotesIn, request: Request, _: User = Depends(doctor_only)):
    with WRITE_LOCK:
        rec = load_or_404(token).model_copy(update={"doctorNotes": body.notes.strip()})
        store.save(rec)
    request.app.state.events.publish("patient.updated", {"token": token})
    return {"doctorNotes": rec.doctorNotes}


def _timeline(rec) -> dict:
    tmp = load_settings().tmp_dir
    return {"confirmed": [e.model_dump() for e in rec.timeline],
            "pending": [{**p, "imageAvailable": ocr_session.read(tmp, p["id"]) is not None} for p in rec.pendingScans]}


@router.get("/timeline", response_model=Timeline)
def timeline(token: str, _: User = Depends(doctor_only)):
    return _timeline(load_or_404(token))


@router.post("/timeline/{i}/confirm", response_model=Timeline)
def confirm_scan(token: str, i: int, body: ScanConfirmIn, request: Request, user: User = Depends(doctor_only)):
    """Doctor confirms one pending scan, with any edits. Edited fields are tracked against the model's draft (ocr.timeline)."""
    with WRITE_LOCK:
        rec = load_or_404(token)
        if not 0 <= i < len(rec.pendingScans):
            raise HTTPException(404, "No pending scan at that position. Reload the timeline.")
        p = rec.pendingScans[i]
        orig = p["draft"]
        edited = {**orig, **body.model_dump()}
        edits = edited_fields(orig, edited)
        entry = TimelineEntry.model_validate(to_timeline_entry(edited, edits, user.username))
        rec = rec.model_copy(update={"timeline": rec.timeline + [entry],
                                     "pendingScans": rec.pendingScans[:i] + rec.pendingScans[i + 1:]})
        store.save(rec)
        ocr_session.delete(load_settings().tmp_dir, p["id"])
    request.app.state.events.publish("patient.updated", {"token": token})
    return _timeline(rec)


@router.post("/timeline/{i}/discard", response_model=Timeline)
def discard_scan(token: str, i: int, request: Request, _: User = Depends(doctor_only)):
    with WRITE_LOCK:
        rec = load_or_404(token)
        if not 0 <= i < len(rec.pendingScans):
            raise HTTPException(404, "No pending scan at that position. Reload the timeline.")
        p = rec.pendingScans[i]
        rec = rec.model_copy(update={"pendingScans": rec.pendingScans[:i] + rec.pendingScans[i + 1:]})
        store.save(rec)
        ocr_session.delete(load_settings().tmp_dir, p["id"])
    request.app.state.events.publish("patient.updated", {"token": token})
    return _timeline(rec)


@router.get("/scans/{sid}/image", response_class=Response)
def scan_image(token: str, sid: str, _: User = Depends(staff_or_doctor)):
    rec = load_or_404(token)
    if not any(p["id"] == sid for p in rec.pendingScans):
        raise HTTPException(404, "No such scan for this patient.")
    img = ocr_session.read(load_settings().tmp_dir, sid)
    if img is None:
        raise HTTPException(404, "The image was deleted after the review time limit. The draft is still here.")
    return Response(img, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
