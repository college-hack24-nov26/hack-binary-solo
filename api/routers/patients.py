"""Board and patient panel (staff and doctor), reference data, and the live event stream."""
import asyncio
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from intake import bodymap
from intake.doctors import get_doctor, load_doctors
from records import store
from records.schema import PatientRecord, Vitals

from ..deps import WRITE_LOCK, User, staff_or_doctor
from ..events import sse_format
from ..schemas import Board, BodyRegions, DoctorChoiceIn, DoctorOut, PatientView, VitalsIn
from ..views import board_row, board_sort_key, doctor_for, doctor_out, patient_view

router = APIRouter(tags=["patients"])


def load_or_404(token: str) -> PatientRecord:
    try:
        rec = store.load(token)
    except ValueError:
        raise HTTPException(404, "No patient with that token.")
    if rec is None:
        raise HTTPException(404, "No patient with that token.")
    return rec


@router.get("/api/intake/body-regions", response_model=BodyRegions)
def body_regions():
    c = bodymap.catalog()
    return {"viewBox": c.viewBox, "sideLabels": c.sideLabels, "viewLabels": c.viewLabels, "translationStatus": c.translationStatus,
            "regions": [{"id": r.id, "view": r.view, "side": r.side, "label": {"en": r.en, "hi": r.hi, "mr": r.mr},
                         "polygon": r.polygon} for r in c.regions]}


@router.get("/api/doctors", response_model=list[DoctorOut])
def doctors():
    return [doctor_out(d) for d in load_doctors()]


@router.get("/api/patients", response_model=Board)
def board(day: Optional[str] = Query(None, alias="date", description="YYYY-MM-DD (default today) or 'all'"),
          status: Optional[str] = None, q: Optional[str] = None, user: User = Depends(staff_or_doctor)):
    day = day or date.today().isoformat()
    me = doctor_for(user.username) if user.role == "doctor" else None
    rows = []
    for r in store.list_records():
        if day != "all" and r.createdAt[:10] != day and r.queueDate != day:
            continue
        if status and r.status != status:
            continue
        row = board_row(r, me)
        if q:
            needle = q.strip().lower()
            hay = " ".join(str(x or "") for x in (r.token, row["complaint"], row["complaintText"], r.queueNumber)).lower()
            if needle not in hay:
                continue
        rows.append(row)
    rows.sort(key=board_sort_key)
    return {"rows": rows, "date": day}


@router.get("/api/patients/{token}", response_model=PatientView)
def patient(token: str, lang: str = "en", user: User = Depends(staff_or_doctor)):
    return patient_view(load_or_404(token), user.role, lang if lang in ("en", "hi", "mr") else "en")


@router.put("/api/patients/{token}/vitals", response_model=PatientView)
def vitals(token: str, body: VitalsIn, request: Request, user: User = Depends(staff_or_doctor)):
    if body.bpSystolic and body.bpDiastolic and body.bpSystolic <= body.bpDiastolic:
        raise HTTPException(422, [{"loc": ["body", "bpSystolic"], "msg": "Systolic must be higher than diastolic.", "type": "value_error"}])
    try:
        v = Vitals(**body.model_dump(), recordedBy=user.username, recordedAt=datetime.now().astimezone().isoformat(timespec="seconds"))
    except ValidationError as e:          # same bounds as the schema; VitalsIn already checked them
        raise HTTPException(422, e.errors())
    with WRITE_LOCK:
        rec = load_or_404(token)
        rec = rec.model_copy(update={"vitals": v})
        store.save(rec)
    request.app.state.events.publish("patient.updated", {"token": token})
    return patient_view(rec, user.role)


@router.put("/api/patients/{token}/doctor", response_model=PatientView)
def reassign(token: str, body: DoctorChoiceIn, request: Request, user: User = Depends(staff_or_doctor)):
    if body.doctorId is not None and get_doctor(body.doctorId) is None:
        raise HTTPException(422, "Unknown doctor.")
    with WRITE_LOCK:
        rec = load_or_404(token).model_copy(update={"assignedDoctor": body.doctorId})
        store.save(rec)
    request.app.state.events.publish("queue.changed", {"token": token})
    return patient_view(rec, user.role)


@router.get("/api/events")
async def events(request: Request, _: User = Depends(staff_or_doctor)):
    broker = request.app.state.events

    async def stream():
        q = broker.subscribe()
        try:
            yield "retry: 3000\n: connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15)
                    yield sse_format(msg)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            broker.unsubscribe(q)
    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
