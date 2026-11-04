"""Kiosk through the API: same record as IntakeSession directly, rebuilt after a restart, one queue number per visit,
two tablets at once, patient-facing output only."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from api_helpers import H, new_kiosk
from fastapi.testclient import TestClient

from api.main import create_app
from dosing import demo
from intake.conditions import SKIPPED, UNSURE
from intake.models import load_graph
from intake.redflags import load_rules
from intake.synthetic import BANK, PATIENTS, run_bank
from records import store

VOLATILE = {"createdAt", "updatedAt", "intakeDurationSeconds", "queueNumber", "queueDate", "finishedAt"}


def _norm(rec) -> dict:
    # round-trip through the store's JSON first: on load, the socrates union reads a radiation answer as SiteAnswer
    # (adds view/inputMode = null). That happens to every saved record, Streamlit's included, so compare like with like.
    from records.schema import PatientRecord
    d = json.loads(PatientRecord.model_validate_json(rec.model_dump_json()).model_dump_json())
    for k in VOLATILE:
        d.pop(k, None)
    d["consent"].pop("timestamp", None)
    return d


def _drive(c: TestClient, token: str, kh: dict, answers: dict, language: str = "en") -> dict:
    """Answer each pending node through the HTTP API exactly as the tablet would."""
    s = c.post(f"/api/kiosk/sessions/{token}/consent", json={"choice": answers.get("consent", "agree")}, headers=kh).json()
    for _ in range(100):
        if s["stage"] != "question":
            return s
        n = s["node"]
        v = answers.get(n["id"], BANK[n["id"]])
        if v == SKIPPED:
            r = c.post(f"/api/kiosk/sessions/{token}/skip", json={"nodeId": n["id"]}, headers=kh)
        elif n["type"] == "body_map" and v != UNSURE:
            r = c.post(f"/api/kiosk/sessions/{token}/bodymap", json={"nodeId": n["id"], **v}, headers=kh)
        else:
            r = c.post(f"/api/kiosk/sessions/{token}/answers", json={"nodeId": n["id"], "value": v}, headers=kh)
        assert r.status_code == 200, (n["id"], r.text)
        s = r.json()
    raise AssertionError("never finished")


SCENARIOS = {**{k: v for k, v in PATIENTS.items()}, **{f"demo_{k}": fx["answers"] for k, fx in demo.DEMO_PATIENTS.items()}, "bank": {}}


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_api_record_equals_intake_session(anon, name):
    answers = dict(SCENARIOS[name])
    token, kh = new_kiosk(anon)
    s = _drive(anon, token, kh, answers)
    assert s["stage"] == "review"
    assert anon.post(f"/api/kiosk/sessions/{token}/finish", headers=kh).status_code == 200
    direct = run_bank(load_graph(), load_rules(), answers, token=token, allow_unused=True).finish()
    assert _norm(store.load(token)) == _norm(direct)


def test_restart_mid_quiz_rebuilds_the_same_session(env):
    app1 = create_app(dist=env / "x")
    c1 = TestClient(app1)
    token, kh = new_kiosk(c1)
    c1.post(f"/api/kiosk/sessions/{token}/consent", json={"choice": "agree"}, headers=kh)
    c1.post(f"/api/kiosk/sessions/{token}/answers", json={"nodeId": "age_years", "value": 40}, headers=kh)
    c1.post(f"/api/kiosk/sessions/{token}/answers", json={"nodeId": "sex", "value": "female"}, headers=kh)
    before = c1.get(f"/api/kiosk/sessions/{token}", headers=kh).json()
    saved = store.load(token)
    c2 = TestClient(create_app(dist=env / "x"))            # "server restart": empty in-memory registry
    after = c2.get(f"/api/kiosk/sessions/{token}", headers=kh).json()
    assert after == before and after["node"]["id"] == "pregnancy"
    rebuilt = c2.app.state.registry.get(token)
    assert _norm(rebuilt.to_record(complete=False, prior=saved)) == _norm(saved)
    assert rebuilt.created_at.isoformat(timespec="seconds") == saved.createdAt
    s = _drive(c2, token, kh, {"sex": "female"})
    assert s["stage"] == "review"


def test_finish_twice_returns_the_same_slip_and_numbers_go_up(anon):
    t1, k1 = new_kiosk(anon)
    _drive(anon, t1, k1, {})
    anon.post(f"/api/kiosk/sessions/{t1}/doctor", json={"doctorId": "dr_general"}, headers=k1)
    with ThreadPoolExecutor(4) as ex:                    # double (quadruple) tap
        slips = list(ex.map(lambda _: anon.post(f"/api/kiosk/sessions/{t1}/finish", headers=k1).json(), range(4)))
    assert len({s["queueNumber"] for s in slips}) == 1
    s1 = slips[0]
    assert s1["doctor"]["id"] == "dr_general" and s1["room"] == "12" and s1["guidance"] == "follow_line"
    assert set(s1) == {"queueNumber", "queueDate", "token", "doctor", "room", "floor", "guidance", "estimatedWaitMinutes", "patientsAhead", "estimateLabel",
                     "papersAdded", "identifierMasked"}      # the two last keys were added with patient identity; still no answers or flags
    t2, k2 = new_kiosk(anon)
    _drive(anon, t2, k2, {})
    anon.post(f"/api/kiosk/sessions/{t2}/doctor", json={"doctorId": "dr_general"}, headers=k2)
    s2 = anon.post(f"/api/kiosk/sessions/{t2}/finish", headers=k2).json()
    assert s2["queueNumber"] == s1["queueNumber"] + 1 and s2["patientsAhead"] == 1 and s2["estimatedWaitMinutes"] == 10
    assert anon.post(f"/api/kiosk/sessions/{t1}/answers", json={"nodeId": "age_years", "value": 30}, headers=k1).status_code == 409


def test_two_tablets_at_once_get_distinct_numbers(app):
    def visit(_):
        c = TestClient(app)
        t, k = new_kiosk(c)
        _drive(c, t, k, {})
        c.post(f"/api/kiosk/sessions/{t}/doctor", json={"doctorId": None}, headers=k)
        return c.post(f"/api/kiosk/sessions/{t}/finish", headers=k).json()
    with ThreadPoolExecutor(6) as ex:
        slips = list(ex.map(visit, range(6)))
    nums = sorted(s["queueNumber"] for s in slips)
    assert nums == list(range(1, 7))
    assert all(s["doctor"] is None and s["room"] is None and s["guidance"] == "reception" for s in slips)


def test_patient_sees_only_the_red_flag_message(anon):
    token, kh = new_kiosk(anon, "hi")
    s = _drive(anon, token, kh, PATIENTS["adult_chest_pain"])
    rec = store.load(token)
    assert rec.redFlags
    msg = rec.redFlags[0].patientMessage["hi"]
    assert s["redFlagMessage"] == msg
    text = json.dumps(s, ensure_ascii=False) + anon.get(f"/api/kiosk/sessions/{token}/review", headers=kh).text
    for f in rec.redFlags:
        assert f.ruleId not in text and f.staffMessage not in text


def test_decline_deletes_the_record_and_bodymap_is_built_on_the_server(anon):
    token, kh = new_kiosk(anon)
    _drive(anon, token, kh, {"chief_complaint": "chest_pain"} | {k: v for k, v in PATIENTS["adult_chest_pain"].items() if k in ("age_years",)})
    assert store.load(token) is not None
    r = anon.post(f"/api/kiosk/sessions/{token}/bodymap", json={"nodeId": "cp_site", "regions": ["not_a_region"]}, headers=kh)
    assert r.status_code == 422
    r = anon.post(f"/api/kiosk/sessions/{token}/consent", json={"choice": "decline"}, headers=kh)
    assert r.json()["stage"] == "declined" and store.load(token) is None


def test_help_raises_an_alert_for_staff(anon, staff):
    token, kh = new_kiosk(anon)
    assert anon.post(f"/api/kiosk/sessions/{token}/help", headers=kh).status_code == 204
    items = staff.get("/api/staff/help-requests").json()["items"]
    assert items[0]["token"] == token
    assert staff.post(f"/api/staff/help-requests/{items[0]['id']}/dismiss", headers=H).status_code == 204
    assert staff.get("/api/staff/help-requests").json()["items"] == []
