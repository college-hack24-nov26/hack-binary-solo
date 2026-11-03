"""Patient chooses a doctor after the quiz; staff and doctor pages show it."""
import json
import time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

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


def page(name, role=None, user=None):
    at = AppTest.from_file(str(ROOT / "intake" / "ui" / f"{name}.py"), default_timeout=20)
    if role:
        at.session_state["auth"] = {"username": user or role, "role": role, "last_seen": time.time()}
    return at


def finish_demo(lang="en"):
    at = page("patient").run()
    if lang != "en":
        at.radio[0].set_value(lang).run()
    at.button(key="demo_mode").click().run()
    next(b for b in at.button if b.key is None and ("finish" in b.label.lower() or "पूरा करें" in b.label)).click().run()
    return at


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
    at = finish_demo()
    assert not at.exception and "Which doctor" in at.subheader[0].value
    assert [k for k in ("doc_dr_general", "doc_dr_heart", "doc_dr_child", "doc_dr_women", "doc_any")
            if at.button(key=k)] == ["doc_dr_general", "doc_dr_heart", "doc_dr_child", "doc_dr_women", "doc_any"]
    assert store.load(DEMO_TOKEN).assignedDoctor is None and store.load(DEMO_TOKEN).status == "complete"
    at.button(key="doc_dr_heart").click().run()
    assert store.load(DEMO_TOKEN).assignedDoctor == "dr_heart"
    assert "Rohan Deshmukh" in at.info[0].value and any("Thank you" in s.value for s in at.success)


def test_any_available_doctor_leaves_it_unassigned():
    at = finish_demo()
    at.button(key="doc_any").click().run()
    assert store.load(DEMO_TOKEN).assignedDoctor is None and not at.exception


def test_doctor_choice_screen_in_hindi():
    at = finish_demo("hi")
    assert "डॉक्टर" in at.subheader[0].value and "सामान्य चिकित्सक" in at.button(key="doc_dr_general").label
    assert "कोई भी उपलब्ध" in at.button(key="doc_any").label


def test_choice_survives_a_rebuild_of_the_record():
    s = run_bank(load_graph(), load_rules(), token="PT-KEEPAA")
    s.assigned_doctor = "dr_child"
    rec = s.finish()
    assert rec.assignedDoctor == "dr_child"
    assert s.to_record(prior=rec).assignedDoctor == "dr_child"


def test_staff_board_shows_chosen_doctor_or_none():
    store.save(run_bank(load_graph(), load_rules(), token="PT-AAAAAA").finish().model_copy(update={"assignedDoctor": "dr_heart"}))
    store.save(run_bank(load_graph(), load_rules(), token="PT-BBBBBB").finish())
    labels = [e.label for e in page("staff", "staff").run().expander]
    assert any("PT-AAAAAA" in l and "→ Dr. Rohan Deshmukh" in l for l in labels)
    assert any("PT-BBBBBB" in l and "no doctor chosen" in l for l in labels)


def test_doctor_page_lists_my_patients_first_for_a_linked_login():
    for tok, doc in (("PT-AAAAAA", "dr_heart"), ("PT-BBBBBB", "dr_general")):
        store.save(run_bank(load_graph(), load_rules(), token=tok).finish().model_copy(update={"assignedDoctor": doc}))
    at = page("doctor", "doctor", "doctor1").run()
    assert not at.exception and at.selectbox[0].options[0].startswith("👤 PT-BBBBBB")
    at = page("doctor", "doctor", "other").run()            # login not linked to a doctor: no reordering, no marker
    assert not any(o.startswith("👤") for o in at.selectbox[0].options)
