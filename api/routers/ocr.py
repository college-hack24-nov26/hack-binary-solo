"""Scan an old prescription or lab report at the staff desk or doctor screen. The draft waits on the record (pendingScans)
until a doctor confirms it (doctor router). Images stay only in the OCR temp folder, never on the kiosk."""
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from ocr import service as ocr_service
from records import store

from ..deps import WRITE_LOCK, User, staff_or_doctor
from ..schemas import PendingScanOut
from .patients import load_or_404

router = APIRouter(prefix="/api/patients/{token}", tags=["ocr"])
MAX_BYTES = 15 * 1024 * 1024


@router.post("/scans", response_model=PendingScanOut)
def upload(token: str, request: Request, image: UploadFile = File(...), consent: bool = Form(False),
           user: User = Depends(staff_or_doctor)):
    load_or_404(token)
    if not consent:
        raise HTTPException(422, "Tick the box to confirm the patient agreed to this scan.")
    data = image.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "The photo is larger than 15 MB. Take it again at a lower resolution.")
    try:
        h = ocr_service.health()
    except ValueError as e:                     # OLLAMA_URL is not localhost
        raise HTTPException(503, str(e))
    if not h.get("ollamaUp"):
        raise HTTPException(503, "Scanning is unavailable: the local model server (Ollama) is not running on this computer. "
                                 "Start it with `ollama serve`, or type the details into the notes. Everything else keeps working.")
    if not h.get("modelPresent"):
        raise HTTPException(503, f"Scanning is unavailable: the model {h.get('model')} is not installed in Ollama.")
    try:
        r = ocr_service.extract(data, True, user.role)    # slow (30-60 s): never under the write lock
    except ocr_service.OcrRefused as e:
        raise HTTPException(403, str(e))
    if not r["ok"]:
        raise HTTPException(422, f"Could not read this document ({r['error']}). Enter the details by hand.")
    pending = {"id": r["sessionId"], "uploadedBy": user.username, "uploadedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
               "latencyS": r["latencyS"], "draft": r["result"]}
    with WRITE_LOCK:
        rec = load_or_404(token)
        store.save(rec.model_copy(update={"pendingScans": rec.pendingScans + [pending]}))
    request.app.state.events.publish("patient.updated", {"token": token})
    return pending
