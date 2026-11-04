"""Patient kiosk. No login: every call after creation carries the session's X-Kiosk-Key, which only opens its own token.
Flow logic, validation and red flags all stay in intake/; this router only stores and renders what the session says."""
import os
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from intake import bodymap
from intake.conditions import UNSURE
from intake.doctors import get_doctor, load_doctors
from intake.engine import answer_label
from intake.session import ConsentRequired, IntakeSession
from records import store

from ..deps import WRITE_LOCK
from ..schemas import (AnswerIn, BackIn, BodyMapIn, ConsentIn, DoctorChoiceIn, KioskCreated, KioskScreen, LanguageIn,
                       NewKioskSession, NodeIn, Review, TokenSlip)
from ..sessions import build_for_save
from ..views import doctor_out

router = APIRouter(prefix="/api/kiosk", tags=["kiosk"])


def kiosk_session(token: str, request: Request, x_kiosk_key: Optional[str] = Header(None)) -> IntakeSession:
    reg = request.app.state.registry
    if not x_kiosk_key:
        raise HTTPException(401, "This tablet session has ended. Start again.")
    if not reg.check_key(token, x_kiosk_key):
        raise HTTPException(403, "This tablet cannot open that token.")
    s = reg.get(token)
    if s is None:                       # key known but nothing saved and not in memory (restart before consent)
        raise HTTPException(404, "This session has ended. Start again.")
    return s


# ---------------------------------------------------------------- screen
def screen(s: IntakeSession, view: Optional[str] = None) -> dict:
    lang = s.language
    rec = store.load(s.token) if s.consented else None
    done, total = s.progress()
    base = {"token": s.token, "language": lang, "progress": {"done": done, "total": total}, "doctorId": s.assigned_doctor,
            "redFlagMessage": s.red_flags[0].patientMessage.get(lang) if s.red_flags and not s.declined else None}
    if s.declined:
        return {**base, "stage": "declined", "canGoBack": False}
    nid = view or s.pending
    if nid is None:
        return {**base, "stage": "done" if rec is not None and rec.queueNumber else "review", "canGoBack": bool(s.path)}
    if nid not in s.path:
        raise HTTPException(409, "That question is not on this patient's path any more.")
    n = s.graph.node(nid)
    node = {"id": n.id, "type": n.type, "section": n.section, "text": n.text.get(lang),
            "options": [{"id": o.id, "label": o.get(lang)} for o in n.options], "min": n.min, "max": n.max,
            "maxSelections": n.maxSelections}
    return {**base, "stage": "consent" if n.section == "consent" else "question", "node": node, "value": s.answers.get(nid),
            "canGoBack": s.previous(nid) is not None}


def _publish(request: Request, s: IntakeSession, before: set[str]) -> None:
    ev = request.app.state.events
    ev.publish("patient.updated", {"token": s.token})
    new = [f for f in s.red_flags if f.ruleId not in before]
    for f in new:
        ev.publish("redflag.triggered", {"token": s.token, "ruleId": f.ruleId, "severity": f.severity, "staffMessage": f.staffMessage})


def _apply(request: Request, s: IntakeSession, fn) -> dict:
    """Run a session change under the write lock, save like the old Streamlit kiosk page did, publish events, return the next screen."""
    with WRITE_LOCK:
        rec = store.load(s.token)
        if rec is not None and rec.queueNumber:
            raise HTTPException(409, "This visit is finished. Start again for the next patient.")
        before = {f.ruleId for f in s.red_flags}
        try:
            fn()
        except ConsentRequired:
            raise HTTPException(409, "Consent is needed before any question.")
        except ValueError as e:
            raise HTTPException(422, str(e))
        if s.declined:                    # nothing is kept; the in-memory session remembers "declined" until the tablet resets
            store.delete(s.token)
            request.app.state.events.publish("queue.changed", {"token": s.token})
        elif s.consented:
            store.save(build_for_save(s))
            _publish(request, s, before)
    return screen(s)


# ---------------------------------------------------------------- endpoints
@router.post("/sessions", response_model=KioskCreated)
def create(body: NewKioskSession, request: Request):
    with WRITE_LOCK:
        s, key = request.app.state.registry.create(body.language)
    return {"token": s.token, "kioskKey": key, "screen": screen(s)}


@router.get("/sessions/{token}", response_model=KioskScreen)
def get_screen(node: Optional[str] = None, s: IntakeSession = Depends(kiosk_session)):
    return screen(s, node)


@router.post("/sessions/{token}/consent", response_model=KioskScreen)
def consent(body: ConsentIn, request: Request, s: IntakeSession = Depends(kiosk_session)):
    return _apply(request, s, lambda: s.answer("consent", body.choice))


@router.post("/sessions/{token}/answers", response_model=KioskScreen)
def answer(body: AnswerIn, request: Request, s: IntakeSession = Depends(kiosk_session)):
    if body.nodeId == "consent":
        raise HTTPException(422, "Use the consent endpoint.")
    if body.nodeId in s.graph.ids() and s.graph.node(body.nodeId).type == "body_map" and body.value != UNSURE:
        raise HTTPException(422, "Body-map answers go to the bodymap endpoint.")
    return _apply(request, s, lambda: s.answer(body.nodeId, body.value))


@router.post("/sessions/{token}/bodymap", response_model=KioskScreen)
def body_map(body: BodyMapIn, request: Request, s: IntakeSession = Depends(kiosk_session)):
    def go():
        if body.special == "unsure":
            s.answer(body.nodeId, UNSURE)         # "I'm not sure" is the ordinary unsure answer (bodymap_input.py)
        else:
            s.answer(body.nodeId, bodymap.make_answer(body.regions, body.inputMode, body.special))
    return _apply(request, s, go)


@router.post("/sessions/{token}/skip", response_model=KioskScreen)
def skip(body: NodeIn, request: Request, s: IntakeSession = Depends(kiosk_session)):
    if body.nodeId == "consent":
        raise HTTPException(422, "Consent cannot be skipped.")
    return _apply(request, s, lambda: s.skip(body.nodeId))


@router.post("/sessions/{token}/back", response_model=KioskScreen)
def back(body: BackIn, s: IntakeSession = Depends(kiosk_session)):
    prev = s.previous(body.nodeId) if body.nodeId else (s.path[-1] if s.path else None)
    if prev is None:
        raise HTTPException(409, "There is no earlier question.")
    return screen(s, prev)


@router.put("/sessions/{token}/language", response_model=KioskScreen)
def language(body: LanguageIn, request: Request, node: Optional[str] = None, s: IntakeSession = Depends(kiosk_session)):
    with WRITE_LOCK:
        s.language = body.language
        if s.consented and not s.declined:
            rec = store.load(s.token)
            if rec is None or not rec.queueNumber:
                store.save(build_for_save(s))
    return screen(s, node)


@router.get("/sessions/{token}/review", response_model=Review)
def review(s: IntakeSession = Depends(kiosk_session)):
    items = []
    for nid in s.path:
        n = s.graph.node(nid)
        if n.section == "consent" or nid not in s.answers:
            continue
        items.append({"nodeId": nid, "question": n.text.get(s.language), "answer": answer_label(n, s.answers[nid], s.language)})
    return {"items": items}


@router.post("/sessions/{token}/doctor", response_model=KioskScreen)
def choose_doctor(body: DoctorChoiceIn, request: Request, s: IntakeSession = Depends(kiosk_session)):
    if body.doctorId is not None and get_doctor(body.doctorId) is None:
        raise HTTPException(422, "Unknown doctor.")
    if not s.consented:
        raise HTTPException(409, "Consent is needed first.")
    with WRITE_LOCK:
        rec = store.load(s.token)
        if rec is not None and rec.queueNumber:
            raise HTTPException(409, "This visit is finished.")
        s.assigned_doctor = body.doctorId
        store.save(build_for_save(s))
    request.app.state.events.publish("queue.changed", {"token": s.token})
    return screen(s)


def minutes_per_patient() -> int:
    try:
        return max(1, int(os.environ.get("OPD_MINUTES_PER_PATIENT", "10")))
    except ValueError:
        return 10


def slip(rec) -> dict:
    """The token slip from the saved record: queue number, token, doctor and room only. No answers, no red flags."""
    today = [r for r in store.list_records() if r.queueDate == rec.queueDate and r.queueNumber]
    same = (lambda r: r.assignedDoctor == rec.assignedDoctor) if rec.assignedDoctor else (lambda r: True)
    ahead = sum(1 for r in today if r.queueNumber < rec.queueNumber and same(r))
    d = get_doctor(rec.assignedDoctor, load_doctors()) if rec.assignedDoctor else None
    dout = doctor_out(d) if d else None
    has_room = bool(d and d.room)
    return {"queueNumber": rec.queueNumber, "queueDate": rec.queueDate, "token": rec.token, "doctor": dout,
            "room": d.room if has_room else None, "floor": dout["floor"] if has_room else None,
            "guidance": "follow_line" if has_room and d.lineColor else ("room" if has_room else "reception"),
            "estimatedWaitMinutes": ahead * minutes_per_patient(), "patientsAhead": ahead, "estimateLabel": "estimate"}


@router.post("/sessions/{token}/finish", response_model=TokenSlip)
def finish(request: Request, s: IntakeSession = Depends(kiosk_session)):
    with WRITE_LOCK:
        prior = store.load(s.token)
        if prior is not None and prior.queueNumber:          # idempotent: a double tap returns the same slip
            return slip(prior)
        if not s.complete:
            raise HTTPException(409, "Some questions are still unanswered.")
        today = date.today().isoformat()
        n = 1 + max((r.queueNumber for r in store.list_records() if r.queueDate == today and r.queueNumber), default=0)
        rec = build_for_save(s, complete=True)
        rec = rec.model_copy(update={"queueNumber": n, "queueDate": today,
                                     "finishedAt": (s.finished_at or datetime.now().astimezone()).isoformat(timespec="seconds")})
        store.save(rec)
    request.app.state.events.publish("queue.changed", {"token": s.token, "queueNumber": n})
    request.app.state.events.publish("patient.updated", {"token": s.token})
    return slip(rec)


@router.post("/sessions/{token}/help", status_code=204)
def help_(request: Request, s: IntakeSession = Depends(kiosk_session)):
    it = request.app.state.help.add(s.token)
    request.app.state.events.publish("help.requested", {"token": s.token, "id": it["id"], "at": it["at"]})
    return Response(status_code=204)
