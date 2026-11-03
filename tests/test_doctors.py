"""Patient chooses a doctor after the quiz; staff and doctor pages show it."""
import json
from pathlib import Path

import pytest

from intake.demo import DEMO_TOKEN
from intake.doctors import DOCTORS_PATH, doctor_for_login, get_doctor, load_doctors
from intake.models import LANGS, TRANSLATION_STATUS, load_graph
from intake.redflags import load_rules
from intake.synthetic import run_bank
from ocr import auth
from records import store
from records.schema import PatientRecord

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("INTAKE_DATA_DIR", str(tmp_path / "data"))
    users = tmp_path / "users.json"
    auth.add_user(users, "doctor1", "correct-horse-1", "doctor")
    auth.add_user(users, "other", "correct-horse-1", "doctor")
    monkeypatch.setenv("OCR_USERS_FILE", str(users))


H = {"X-Requested-With": "medikiosk"}


def kiosk_at_review(lang="en"):
    """The synthetic bank patient answered through the HTTP kiosk API up to the review screen (replaces the Streamlit demo button)."""
    from fastapi.testclient import TestClient

    from api.main import create_app
    from intake.synthetic import BANK
    c = TestClient(create_app(dist=ROOT / "no_dist"))
    r = c.post("/api/kiosk/sessions", json={"language": lang}, headers=H).json()
    t, kh = r["token"], {**H, "X-Kiosk-Key": r["kioskKey"]}
    s = c.post(f"/api/kiosk/sessions/{t}/consent", json={"choice": "agree"}, headers=kh).json()
    while s["stage"] == "question":
        n = s["node"]
        v = BANK[n["id"]]
        url = "bodymap" if n["type"] == "body_map" else "answers"
        body = {"nodeId": n["id"], **v} if url == "bodymap" else {"nodeId": n["id"], "value": v}
        s = c.post(f"/api/kiosk/sessions/{t}/{url}", json=body, headers=kh).json()
    assert s["stage"] == "review"
    return c, t, kh


def test_doctors_file_is_valid_synthetic_and_translated():
    docs = load_doctors()
    assert len(docs) >= 3 and len({d.id for d in docs}) == len(docs)
    for d in docs:
        for lang in LANGS:
            assert getattr(d.specialty, lang).strip()
        assert d.specialty.hi != d.specialty.en and d.specialty.mr != d.specialty.en
    assert json.loads(DOCTORS_PATH.read_text(encoding="utf-8"))["translationStatus"] == TRANSLATION_STATUS


def test_lookups():
    assert get_doctor("dr_heart").name.startswith("Dr.") and get_doctor("nope") is None and get_doctor(None) is None
    assert doctor_for_login("doctor1").id == "dr_general" and doctor_for_login(" DOCTOR1 ").id == "dr_general"
    assert doctor_for_login("someone") is None


def test_old_records_without_the_field_still_load():
    rec = run_bank(load_graph(), load_rules(), token="PT-OLDAAA").finish()
    raw = json.loads(rec.model_dump_json())
    del raw["assignedDoctor"]
    assert PatientRecord.model_validate(raw).assignedDoctor is None


def test_kiosk_asks_for_a_doctor_after_the_quiz_and_stores_the_choice():
    c, t, kh = kiosk_at_review()
    assert [d["id"] for d in c.get("/api/doctors").json()] == ["dr_general", "dr_heart", "dr_child", "dr_women"]
    assert store.load(t).assignedDoctor is None
    assert c.post(f"/api/kiosk/sessions/{t}/doctor", json={"doctorId": "dr_heart"}, headers=kh).status_code == 200
    assert store.load(t).assignedDoctor == "dr_heart"
    slip = c.post(f"/api/kiosk/sessions/{t}/finish", headers=kh).json()
    assert slip["doctor"]["name"] == "Dr. Rohan Deshmukh" and store.load(t).status == "complete"
    assert store.load(t).assignedDoctor == "dr_heart"


def test_any_available_doctor_leaves_it_unassigned():
    c, t, kh = kiosk_at_review()
    assert c.post(f"/api/kiosk/sessions/{t}/doctor", json={"doctorId": None}, headers=kh).status_code == 200
    slip = c.post(f"/api/kiosk/sessions/{t}/finish", headers=kh).json()
    assert store.load(t).assignedDoctor is None and slip["doctor"] is None and slip["guidance"] == "reception"


def test_doctor_choice_screen_in_hindi():
    c, t, kh = kiosk_at_review("hi")
    docs = {d["id"]: d for d in c.get("/api/doctors").json()}
    assert docs["dr_general"]["specialty"]["hi"] == "सामान्य चिकित्सक"
    import json as _j
    web = _j.loads((ROOT / "web" / "src" / "i18n" / "kiosk.json").read_text(encoding="utf-8"))
    assert "कोई भी उपलब्ध" in web["strings"]["anyDoctor"]["hi"] and "डॉक्टर" in web["strings"]["chooseDoctor"]["hi"]


def test_choice_survives_a_rebuild_of_the_record():
    s = run_bank(load_graph(), load_rules(), token="PT-KEEPAA")
    s.assigned_doctor = "dr_child"
    rec = s.finish()
    assert rec.assignedDoctor == "dr_child"
    assert s.to_record(prior=rec).assignedDoctor == "dr_child"


