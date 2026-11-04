"""Kiosk step 1: who is the patient. Identifier + 4-digit PIN (see api/identity_provider.py for why not OTP).

Nothing is stored before the patient agrees to the consent screen: `identify` writes nothing, `register` carries the consent.
A patient who says "no thanks" never reaches this router and continues as an anonymous walk-in (the quiz's own consent applies).
Errors carry a machine code in the `X-Error-Code` header so the tablet can answer in the patient's language."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from records import identity, identity_audit, patients, scanfiles, store
from records.identity import IdentifierError

from .. import identity_provider as idp
from ..deps import WRITE_LOCK
from ..kiosk_identity import DEVICE_HEADER, IDENTITY_HEADER, check_rate, device_id, idle_s
from ..schemas import KioskScreen
from ..schemas_identity import (CONSENT_COVERS, CONSENT_VERSION, IdentifyIn, IdentifyOut, IdentityOut, LoginIn, RegisterIn, WalkInIn)
from ..sessions import build_for_save
from .kiosk import _publish, kiosk_session, screen

router = APIRouter(prefix="/api/kiosk", tags=["kiosk identity"])


def _norm(kind: str, raw: str) -> str:
    try:
        return identity.normalise(kind, raw)
    except IdentifierError as e:
        msg = "Enter a 10-digit mobile number." if kind == "mobile" else "An ABHA number has 14 digits."
        raise HTTPException(422, msg, headers={"X-Error-Code": str(e)})


def _kiosk_id() -> str:
    import os
    return os.environ.get("KIOSK_ID", "kiosk-1")[:40]


def _last_visit(p: patients.Patient) -> Optional[str]:
    days = []
    for v in p.visitIds:
        try:
            r = store.load(v)
        except ValueError:
            continue
        if r is not None and r.queueDate:
            days.append(r.queueDate)
    return max(days) if days else None


def _out(request: Request, p: patients.Patient, returning: bool, walk_in: bool = False) -> dict:
    tok = request.app.state.identity_sessions.issue(p.id)
    return {"identityToken": tok, "masked": p.masked, "returning": returning, "walkIn": walk_in,
            "lastVisit": _last_visit(p) if returning else None, "expiresInS": idle_s()}


@router.post("/identify", response_model=IdentifyOut, summary="Is this identifier already registered? (exists only, no data)")
def identify(body: IdentifyIn, request: Request, x_kiosk_device: Optional[str] = Header(None)):
    n = _norm(body.type, body.identifier)
    h = identity.lookup_hash(body.type, n)
    check_rate(request, device_id(request, x_kiosk_device), h)
    return {"exists": patients.find_by_hash(h) is not None, "masked": identity.mask(body.type, n)}


@router.post("/register", response_model=IdentityOut, summary="New patient: identifier, PIN and consent in one call")
def register(body: RegisterIn, request: Request, x_kiosk_device: Optional[str] = Header(None)):
    n = _norm(body.type, body.identifier)
    h = identity.lookup_hash(body.type, n)
    dev = device_id(request, x_kiosk_device)
    check_rate(request, dev, h)
    if not identity.valid_pin(body.pin):
        raise HTTPException(422, "The PIN must be 4 digits.", headers={"X-Error-Code": "pin_format"})
    consent = patients.ConsentRecord(version=CONSENT_VERSION, language=body.consent.language, at=datetime.now().astimezone().isoformat(timespec="seconds"),
                                     kioskId=_kiosk_id(), agreed=True, covers=body.consent.covers or CONSENT_COVERS)
    with WRITE_LOCK:
        if patients.find_by_hash(h) is not None:
            raise HTTPException(409, "This number is already registered. Enter your PIN.", headers={"X-Error-Code": "exists"})
        p = request.app.state.provider.enrol(body.type, n, body.pin, consent)
        identity_audit.write("identity.register", actor="kiosk", patient=p.id, masked=p.masked, type=p.identifierType, device=dev[:16])
        identity_audit.write("consent.recorded", actor="kiosk", patient=p.id, version=consent.version, language=consent.language, agreed=True)
    return _out(request, p, returning=False)


@router.post("/login", response_model=IdentityOut, summary="Returning patient: identifier and PIN")
def login(body: LoginIn, request: Request, x_kiosk_device: Optional[str] = Header(None)):
    n = _norm(body.type, body.identifier)
    h = identity.lookup_hash(body.type, n)
    dev = device_id(request, x_kiosk_device)
    check_rate(request, dev, h)
    if not identity.valid_pin(body.pin):
        raise HTTPException(422, "The PIN must be 4 digits.", headers={"X-Error-Code": "pin_format"})
    with WRITE_LOCK:
        p = patients.find_by_hash(h)
        if p is None:
            raise HTTPException(401, "We could not find that number. Check it or ask staff.", headers={"X-Error-Code": "not_found"})
        try:
            res = request.app.state.provider.authenticate(p, body.pin)
        except idp.AuthError as e:
            if e.code == "locked":
                raise HTTPException(423, "Too many wrong PINs. Please ask staff.", headers={"X-Error-Code": "locked", "Retry-After": str(e.retry_after_s)})
            raise HTTPException(401, "Please ask staff to help you sign in.", headers={"X-Error-Code": e.code})
        patients.save(res.patient)
        if res.event == "identity.login":
            identity_audit.write("identity.login", actor="kiosk", patient=p.id, masked=p.masked, device=dev[:16])
            return _out(request, p, returning=True)
        if res.event == "identity.locked":
            identity_audit.write("identity.locked", actor="kiosk", patient=p.id, masked=p.masked, until=p.lockedUntil or "")
            raise HTTPException(423, "Too many wrong PINs. Please ask staff.", headers={"X-Error-Code": "locked", "Retry-After": str(patients.LOCK_SECONDS)})
        identity_audit.write("identity.login_failed", actor="kiosk", patient=p.id, masked=p.masked, attempts=p.failedAttempts)
        left = patients.LOCK_AFTER - p.failedAttempts
        raise HTTPException(401, "That PIN is not right.", headers={"X-Error-Code": "wrong_pin", "X-Attempts-Left": str(left)})


@router.post("/walk-in", response_model=IdentityOut, summary='"I have neither / ask staff": a walk-in record that staff complete at the desk')
def walk_in(body: WalkInIn, request: Request, x_kiosk_device: Optional[str] = Header(None)):
    check_rate(request, device_id(request, x_kiosk_device), None)
    with WRITE_LOCK:
        p = patients.create("walk_in", None, None, None, needs_staff=True)
        identity_audit.write("identity.walk_in", actor="kiosk", patient=p.id, language=body.language)
    return _out(request, p, returning=False, walk_in=True)


@router.post("/sessions/{token}/bind", response_model=KioskScreen, summary="Attach the signed-in patient to this visit")
def bind(token: str, request: Request, s=Depends(kiosk_session), x_kiosk_identity: Optional[str] = Header(None)):
    got = request.app.state.identity_sessions.touch(x_kiosk_identity)
    if got is None:
        raise HTTPException(401, "Please sign in again.", headers={"X-Error-Code": "identity_expired"})
    pid = got[1].patient_id
    with WRITE_LOCK:
        p = patients.load(pid)
        if p is None:
            raise HTTPException(404, "Please sign in again.", headers={"X-Error-Code": "identity_expired"})
        prior = store.load(token)
        if prior is not None and prior.patientId not in (None, pid):
            raise HTTPException(409, "This visit already belongs to someone else.")
        returning = bool(p.visitIds) and p.identifierType != "walk_in"
        s.identity = {"patientId": pid, "identifierType": p.identifierType, "identifierMasked": p.masked, "returning": returning}
        if token not in p.visitIds:
            p.visitIds.append(token)
            patients.save(p)
        if p.identifierType != "walk_in":          # the identity consent screen was the consent; a walk-in answers the quiz consent himself
            before = {f.ruleId for f in s.red_flags}
            if not s.consented:
                s.answer("consent", "agree")
            store.save(build_for_save(s))
            _publish(request, s, before)
        identity_audit.write("visit.bound", actor="kiosk", token=token, patient=pid, masked=p.masked)
    request.app.state.events.publish("queue.changed", {"token": token})
    return screen(s)


@router.post("/sessions/{token}/end", status_code=204, summary="Finish or reset: drop the identity session and unconfirmed scans")
def end(token: str, request: Request, s=Depends(kiosk_session), x_kiosk_identity: Optional[str] = Header(None)):
    request.app.state.identity_sessions.drop(x_kiosk_identity)
    with WRITE_LOCK:
        rec = store.load(token)
        if rec is not None and rec.kioskScans:
            keep, dropped = [], 0
            for sc in rec.kioskScans:
                if sc.get("confirmed"):
                    keep.append(sc)
                else:
                    scanfiles.delete(sc["id"])
                    dropped += 1
            if dropped:
                store.save(rec.model_copy(update={"kioskScans": keep}))
                identity_audit.write("scan.discarded_on_end", actor="kiosk", token=token, count=dropped)
    return Response(status_code=204)
