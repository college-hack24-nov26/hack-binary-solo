"""Staff view of patient identities: masked only. Lookup, PIN reset, completing a walk-in."""
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from records import identity, identity_audit, patients, store

from ..deps import WRITE_LOCK, User, staff_or_doctor
from ..routers.identity import _norm
from ..schemas_identity import PatientAdminOut, PatientLookupOut, ResetPinOut, WalkInCompleteIn, WalkInCompleteOut

router = APIRouter(prefix="/api/staff", tags=["staff identity"])


def admin_out(p: patients.Patient) -> dict:
    return {"id": p.id, "identifierType": p.identifierType, "masked": p.masked, "needsStaff": p.needsStaff, "locked": patients.is_locked(p),
            "lockedUntil": p.lockedUntil if patients.is_locked(p) else None, "createdAt": p.createdAt, "visitIds": p.visitIds,
            "consents": len(p.consents), "lastConsentVersion": p.consents[-1].version if p.consents else None}


def _load(pid: str) -> patients.Patient:
    p = patients.load(pid)
    if p is None:
        raise HTTPException(404, "No patient with that id.")
    return p


@router.get("/patients", response_model=PatientLookupOut, summary="Find a patient by the visible digits, a visit token, a queue number or the full number")
def lookup(q: str = "", user: User = Depends(staff_or_doctor)):
    q = q.strip()
    if not q:
        return {"patients": [admin_out(p) for p in patients.list_all()[-30:]]}
    found: dict[str, patients.Patient] = {}
    for kind in ("mobile", "abha"):                       # a full number is normalised and found by its keyed hash, never compared in plain
        try:
            p = patients.find_by_hash(identity.lookup_hash(kind, identity.normalise(kind, q)))
        except identity.IdentifierError:
            continue
        if p:
            found[p.id] = p
    digits = re.sub(r"\D", "", q)
    for p in patients.list_all():
        visits = [v for v in p.visitIds if q.upper() in v]
        if (digits and len(digits) <= 4 and re.sub(r"\D", "", p.masked).endswith(digits)) or visits or q.upper() == p.id:
            found[p.id] = p
    if digits.isdigit() and len(digits) <= 4:              # a queue number today
        for r in store.list_records():
            if r.queueNumber is not None and str(r.queueNumber) == digits and r.patientId:
                p = patients.load(r.patientId)
                if p:
                    found[p.id] = p
    return {"patients": [admin_out(p) for p in found.values()]}


@router.get("/patients/{pid}", response_model=PatientAdminOut)
def get_patient(pid: str, user: User = Depends(staff_or_doctor)):
    return admin_out(_load(pid))


@router.post("/patients/{pid}/reset-pin", response_model=ResetPinOut, summary="Staff verified the person: set a temporary PIN and clear the lock")
def reset_pin(pid: str, user: User = Depends(staff_or_doctor)):
    with WRITE_LOCK:
        p = _load(pid)
        if not p.lookupHash:
            raise HTTPException(409, "This walk-in has no number yet. Complete the walk-in first.")
        pin = identity.temp_pin()
        p.pinHash, p.failedAttempts, p.lockedUntil = identity.hash_pin(p.lookupHash, pin), 0, None
        patients.save(p)
        identity_audit.write("identity.pin_reset", actor=user.username, patient=p.id, masked=p.masked)
    return {"id": p.id, "pin": pin}


@router.post("/patients/{pid}/walk-in-complete", response_model=WalkInCompleteOut, summary="Attach a number to a walk-in and give a temporary PIN")
def walk_in_complete(pid: str, body: WalkInCompleteIn, user: User = Depends(staff_or_doctor)):
    n = _norm(body.type, body.identifier)
    h = identity.lookup_hash(body.type, n)
    with WRITE_LOCK:
        p = _load(pid)
        if p.identifierType != "walk_in" or p.lookupHash:
            raise HTTPException(409, "This patient already has a number.")
        other = patients.find_by_hash(h)
        if other is not None:
            raise HTTPException(409, f"That number already belongs to patient {other.id}.")
        pin = identity.temp_pin()
        p.identifierType, p.identifierEnc, p.lookupHash = body.type, identity.encrypt(n), h
        p.masked, p.pinHash, p.needsStaff = identity.mask(body.type, n), identity.hash_pin(h, pin), False
        patients.save(p)
        for v in p.visitIds:                                 # the visit records show the masked number from now on
            try:
                r = store.load(v)
            except ValueError:
                continue
            if r is not None:
                store.save(r.model_copy(update={"identifierType": p.identifierType, "identifierMasked": p.masked}))
        identity_audit.write("walkin.completed", actor=user.username, patient=p.id, masked=p.masked, type=p.identifierType)
    return {"patient": admin_out(p), "pin": pin}
