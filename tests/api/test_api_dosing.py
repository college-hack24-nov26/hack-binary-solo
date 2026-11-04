"""Dosing and audit through the API: results are the engine's own (byte-identical), overrides and confirmations are enforced
by the server, a missing formulary gives 503 while intake keeps working, and the audit viewer is read-only and honest."""
import json

from api_helpers import H, dumps, login, new_kiosk, save_demo
from fastapi.testclient import TestClient

from dosing import audit, service
from records import store

ARGS = {"drug": "paracetamol", "indication": "pain/fever", "confirmed": ["weight_kg"]}


def _none_apply(c, token, drug):
    items = c.post("/api/dosing/history-items", json={"token": token, "drug": drug}, headers=H).json()
    if items["unknown"]:
        assert c.post(f"/api/patients/{token}/history", json={"answers": {i["field"]: "no" for i in items["unknown"]}}, headers=H).status_code == 200


def test_evaluate_is_byte_identical_to_the_service(doctor):
    rec = save_demo("child_fever")
    _none_apply(doctor, rec.token, "paracetamol")
    r = doctor.post("/api/dosing/evaluate", json={"token": rec.token, **ARGS}, headers=H)
    assert r.status_code == 200
    direct = service.evaluate_for_record(store.load(rec.token), "paracetamol", "pain/fever", doctor_id="doctor_t",
                                         confirmed=["weight_kg"], log=False)
    assert dumps(r.json()["result"]) == dumps(direct)
    assert json.loads(r.text)["result"] == json.loads(json.dumps(direct))
    assert r.json()["card"]["header"] == "Dose ready for doctor review" and r.json()["canConfirm"] is True


def test_override_needs_category_and_ten_characters(doctor):
    rec = save_demo("penicillin_allergy")
    body = {"token": rec.token, "drug": "amoxicillin", "indication": "community-acquired pneumonia", "selectedRuleId": "amoxicillin#0"}
    assert doctor.post("/api/dosing/evaluate", json=body, headers=H).json()["result"]["status"] == "blocked"
    r = doctor.post("/api/dosing/evaluate", json={**body, "overrideCategory": "benefit_outweighs_risk", "overrideReason": "short"}, headers=H)
    assert r.status_code == 422 and r.json()["detail"] == "Write a reason of at least 10 characters."
    r = doctor.post("/api/dosing/evaluate", json={**body, "overrideReason": "Specialist advised it"}, headers=H)
    assert r.status_code == 422 and r.json()["detail"] == "Choose a reason category."
    r = doctor.post("/api/dosing/evaluate", json={**body, "overrideCategory": "benefit_outweighs_risk", "overrideReason": "Mild reaction only; ID consult done"}, headers=H)
    res = r.json()["result"]
    assert res["status"] == "ok" and res["overrides"] and res["overrides"][0]["doctor_id"] == "doctor_t"
    assert any(e["event"] == "override" and e["doctor_id"] == "doctor_t" for e in audit.read())


def test_confirm_uses_the_server_result_only(doctor, app):
    rec = save_demo("child_fever")
    _none_apply(doctor, rec.token, "paracetamol")
    assert doctor.post("/api/dosing/confirm", json={"token": rec.token, "resultId": "made-up"}, headers=H).status_code == 409
    nf = doctor.post("/api/dosing/evaluate", json={"token": rec.token, "drug": "paracetamol", "indication": "pain/fever"}, headers=H).json()
    assert nf["result"]["final"] is False and nf["canConfirm"] is False                      # weight not confirmed
    assert doctor.post("/api/dosing/confirm", json={"token": rec.token, "resultId": nf["resultId"]}, headers=H).status_code == 409
    ok = doctor.post("/api/dosing/evaluate", json={"token": rec.token, **ARGS}, headers=H).json()
    other = login(TestClient(app), "doctor1")
    assert other.post("/api/dosing/confirm", json={"token": rec.token, "resultId": ok["resultId"]}, headers=H).status_code == 409
    r = doctor.post("/api/dosing/confirm", json={"token": rec.token, "resultId": ok["resultId"]}, headers=H)
    assert r.status_code == 200 and r.json()["dosingChecks"][-1]["result"] == ok["result"]
    assert doctor.post("/api/dosing/confirm", json={"token": rec.token, "resultId": ok["resultId"]}, headers=H).status_code == 409  # one-shot
    assert audit.verify()


def test_missing_formulary_is_503_and_intake_still_works(doctor, monkeypatch, tmp_path):
    rec = save_demo("child_fever")
    monkeypatch.setenv("DOSING_FORMULARY_PATH", str(tmp_path / "missing.json"))
    for r in (doctor.get("/api/dosing/drugs"), doctor.post("/api/dosing/evaluate", json={"token": rec.token, **ARGS}, headers=H)):
        assert r.status_code == 503 and "Intake, the staff board and summaries still work" in r.json()["detail"]
    assert doctor.get("/api/system/config").json()["formularyLoaded"] is False
    token, kh = new_kiosk(doctor)
    assert doctor.post(f"/api/kiosk/sessions/{token}/consent", json={"choice": "agree"}, headers=kh).status_code == 200
    assert doctor.get(f"/api/patients/{rec.token}/summary").status_code == 200


def test_audit_pages_newest_first_and_reports_a_broken_chain(doctor):
    rec = save_demo("child_fever")
    for _ in range(5):
        doctor.post("/api/dosing/evaluate", json={"token": rec.token, **ARGS}, headers=H)
    p1 = doctor.get("/api/audit?limit=2").json()
    p2 = doctor.get(f"/api/audit?limit=2&cursor={p1['nextCursor']}").json()
    assert p1["total"] == 5 and [r["index"] for r in p1["rows"] + p2["rows"]] == [4, 3, 2, 1]
    assert p1["rows"][0]["prev"] == p1["rows"][1]["hash"]
    assert doctor.get("/api/audit/verify").json() == {"ok": True, "entries": 5, "firstBadIndex": None}
    assert doctor.get("/api/audit/export?format=csv").text.startswith("time,doctor,patient")
    assert len(json.loads(doctor.get("/api/audit/export?format=json&action=evaluated").text)) == 5
    # tamper with line 3: the viewer says so and names it, and never rewrites the log
    p = audit.log_path()
    lines = p.read_text(encoding="utf-8").splitlines()
    e = json.loads(lines[2])
    e["doctor_id"] = "someone_else"
    lines[2] = json.dumps(e, sort_keys=True, ensure_ascii=False)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    before = p.read_bytes()
    assert doctor.get("/api/audit/verify").json() == {"ok": False, "entries": 5, "firstBadIndex": 2}
    assert p.read_bytes() == before and audit.verify() is False


def test_demo_routes_are_404_without_demo_mode(doctor, monkeypatch):
    assert doctor.get("/api/demo/fixtures").status_code == 404
    monkeypatch.setenv("DEMO_MODE", "1")
    keys = [f["key"] for f in doctor.get("/api/demo/fixtures").json()]
    assert set(keys) == {"child_fever", "diabetes_kidney", "penicillin_allergy"}
    r = doctor.post("/api/demo/load/penicillin_allergy", headers=H)
    assert r.status_code == 200 and store.load(r.json()["token"]) is not None
