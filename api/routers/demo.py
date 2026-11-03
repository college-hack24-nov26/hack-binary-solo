"""Demo helpers, only when DEMO_MODE=1 (404 otherwise). Synthetic patients only; records are built by replaying answers through
the real IntakeSession, nothing here is canned output."""
from fastapi import APIRouter, Depends, HTTPException, Request

from intake import offline
from intake.demo import load_demo
from records import store

from ..deps import WRITE_LOCK, User, doctor_only, staff_or_doctor
from ..schemas import Fixture, Loaded

router = APIRouter(prefix="/api/demo", tags=["demo"])


def demo_on() -> None:
    if not offline.demo_mode():
        raise HTTPException(404, "Not found")


@router.get("/fixtures", response_model=list[Fixture], dependencies=[Depends(demo_on)])
def fixtures(_: User = Depends(doctor_only)):
    from dosing import demo
    return [{"key": k, "displayName": f["displayName"], "title": f["title"], "token": f["token"], "drug": f["check"]["drug"],
             "indication": f["check"].get("indication")} for k, f in demo.DEMO_PATIENTS.items()]


@router.post("/load/{key}", response_model=Loaded, dependencies=[Depends(demo_on)])
def load(key: str, request: Request, _: User = Depends(doctor_only)):
    from dosing import demo
    if key not in demo.DEMO_PATIENTS:
        raise HTTPException(404, "No demo patient with that key.")
    with WRITE_LOCK:
        rec = demo.record(key)
        store.save(rec)
    request.app.state.events.publish("queue.changed", {"token": rec.token})
    return {"token": rec.token}


@router.post("/kiosk-patient", response_model=Loaded, dependencies=[Depends(demo_on)])
def kiosk_patient(request: Request, _: User = Depends(staff_or_doctor)):
    """The old kiosk 'demo' button: a synthetic chest-pain patient, answered through the real session (red flags included)."""
    reg = request.app.state.registry
    with WRITE_LOCK:
        s = load_demo(reg.graph, reg.rules)
        store.save(s.finish())
    request.app.state.events.publish("patient.updated", {"token": s.token})
    for f in s.red_flags:
        request.app.state.events.publish("redflag.triggered", {"token": s.token, "ruleId": f.ruleId, "severity": f.severity,
                                                               "staffMessage": f.staffMessage})
    return {"token": s.token}
