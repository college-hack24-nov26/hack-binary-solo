"""Error states the screens rely on: scanning without consent or without the local model server, vitals bounds, unknown
tokens. Each says what happened and how to fix it."""
from api_helpers import H, save_demo


def test_scan_needs_consent_and_a_running_local_model(staff):
    rec = save_demo("child_fever")
    img = {"image": ("rx.png", b"\x89PNG\r\n\x1a\n", "image/png")}
    r = staff.post(f"/api/patients/{rec.token}/scans", files=img, data={"consent": "false"}, headers=H)
    assert r.status_code == 422 and "agreed" in r.json()["detail"]
    r = staff.post(f"/api/patients/{rec.token}/scans", files=img, data={"consent": "true"}, headers=H)
    assert r.status_code == 503 and "Ollama" in r.json()["detail"] and "Everything else keeps working" in r.json()["detail"]
    assert staff.get(f"/api/patients/{rec.token}").status_code == 200            # the rest of the app keeps working


def test_vitals_bounds_come_back_as_field_errors(staff):
    rec = save_demo("child_fever")
    r = staff.put(f"/api/patients/{rec.token}/vitals", json={"bpSystolic": 320, "spo2": 101}, headers=H)
    assert r.status_code == 422
    fields = {e["loc"][-1] for e in r.json()["detail"]}
    assert fields == {"bpSystolic", "spo2"}
    r = staff.put(f"/api/patients/{rec.token}/vitals", json={"bpSystolic": 80, "bpDiastolic": 90}, headers=H)
    assert r.status_code == 422 and r.json()["detail"][0]["msg"] == "Systolic must be higher than diastolic."
    r = staff.put(f"/api/patients/{rec.token}/vitals", json={"bpSystolic": 120, "bpDiastolic": 80, "notes": "after rest"}, headers=H)
    assert r.status_code == 200 and r.json()["vitals"]["recordedBy"] == "staff_t"


def test_unknown_or_malformed_token_is_404(staff, doctor):
    for t in ("PT-ZZZZZZ", "not-a-token", "..%2F..%2Fetc"):
        assert staff.get(f"/api/patients/{t}").status_code == 404
        assert doctor.get(f"/api/patients/{t}/summary").status_code == 404


def test_offline_strict_installs_the_guard_and_the_badge_says_so(env, monkeypatch):
    import socket

    import pytest
    from fastapi.testclient import TestClient

    from api.main import create_app
    from api_helpers import login
    from intake import offline
    monkeypatch.setenv("OFFLINE_STRICT", "1")
    try:
        c = login(TestClient(create_app(dist=env / "x")), "staff_t")
        assert socket.socket.connect is offline._guarded_connect
        s = c.get("/api/system/offline-status").json()
        assert s["strict"] is True and s["internet"] is None and "strict" in s["headline"]
        with pytest.raises(offline.OfflineViolation):
            socket.create_connection(("93.184.216.34", 80), timeout=1)
        assert c.get("/api/system/config").json()["strict"] is True
    finally:
        offline.remove_guard()


def test_doctor_queue_lists_my_patients_first(app):
    from fastapi.testclient import TestClient

    from api_helpers import login
    from dosing import demo
    from intake.demo import load_demo
    from intake.models import load_graph
    from intake.redflags import load_rules
    from records import store
    urgent = load_demo(load_graph(), load_rules()).finish()                  # red flag, no doctor
    mine = demo.record("child_fever").model_copy(update={"assignedDoctor": "dr_general"})
    store.save(urgent)
    store.save(mine)
    doc = login(TestClient(app), "doctor1")                                   # linked to dr_general
    rows = doc.get("/api/patients").json()["rows"]
    assert [r["token"] for r in rows][:2] == [mine.token, urgent.token] and rows[0]["mine"]
    staff = login(TestClient(app), "staff_t")
    assert staff.get("/api/patients").json()["rows"][0]["token"] == urgent.token
