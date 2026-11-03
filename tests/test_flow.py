"""The three-step flow: 1 sign in, 2 scan old records (OCR), 3 quiz. OCR is faked; no Ollama, no network."""
import time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from intake.session import IntakeSession
from intake.models import load_graph
from intake.redflags import load_rules
from ocr import auth, session as ocr_session
from ocr.config import load_settings
from ocr.postprocess import enrich
from ocr.schema import RawExtraction
from records import store

ROOT = Path(__file__).resolve().parent.parent
PW = "correct-horse-1"
RAW = {"documentType": "prescription", "documentDate": "12/03/2024",
       "medications": [{"nameAsWritten": "Tab. Paracetamol", "strength": "500 mg", "frequencyAsWritten": "1-0-1", "confidence": 0.95}],
       "labResults": [], "diagnosesAsWritten": ["fever"], "unreadable": [], "warnings": []}


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    users = tmp_path / "users.json"
    auth.add_user(users, "dr", PW, "doctor")
    auth.add_user(users, "nurse", PW, "staff")
    monkeypatch.setenv("OCR_USERS_FILE", str(users))
    monkeypatch.setenv("INTAKE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OCR_TMP_DIR", str(tmp_path / "ocr_tmp"))
    return tmp_path


def app(path="main_app.py", role=None):
    at = AppTest.from_file(str(ROOT / path), default_timeout=30)
    if role:
        at.session_state["auth"] = {"username": role, "role": role, "last_seen": time.time()}
    return at


def test_step1_signed_out_shows_only_sign_in():
    at = app().run()
    assert not at.exception and at.title[0].value == "Sign in"


def test_step1_login_moves_to_step2():
    at = app().run()
    at.text_input[0].set_value("nurse")
    at.text_input[1].set_value(PW)
    at.button[0].click().run()
    assert not at.exception and at.title[0].value == "Step 2 · Scan old records"


def test_step1_wrong_password_stays_on_sign_in():
    at = app().run()
    at.text_input[0].set_value("nurse")
    at.text_input[1].set_value("nope-nope-1")
    at.button[0].click().run()
    assert at.title[0].value == "Sign in" and "Invalid" in at.error[0].value


def test_step2_page_needs_login():
    at = app("intake/ui/ocr_scan.py").run()
    assert at.title[0].value == "Sign in"


def test_step2_extract_button_needs_consent_and_skip_is_offered():
    at = app("intake/ui/ocr_scan.py", "doctor").run()
    assert not at.exception and "Tick consent" in at.info[0].value
    assert any("Skip scanning" in b.label for b in at.button)


def review_state(at, sid):
    at.session_state["review"] = {"sessionId": sid, "original": enrich(RawExtraction.model_validate(RAW)), "latencyS": 1.0}
    return at


def make_image(tmp_dir):
    import io
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(b, "JPEG")
    return ocr_session.create(tmp_dir, b.getvalue())


def test_step2_doctor_confirm_attaches_scan_to_the_patient_session_and_record():
    s = IntakeSession(load_graph(), load_rules())
    s.answer("consent", "agree")
    at = app("intake/ui/ocr_scan.py", "doctor")
    at.session_state["sess"] = s
    review_state(at, make_image(load_settings().tmp_dir)).run()
    assert not at.exception
    next(b for b in at.button if "Confirm and attach" in b.label).click().run()
    assert len(s.timeline) == 1 and s.timeline[0].source == "ocr" and s.timeline[0].diagnoses == ["fever"]
    assert s.timeline[0].confirmedBy == "doctor"
    assert store.load(s.token).timeline[0].items[0]["nameAsWritten"] == "Tab. Paracetamol"   # saved because quiz consent was given


def test_step2_before_quiz_consent_nothing_is_stored():
    s = IntakeSession(load_graph(), load_rules())
    at = app("intake/ui/ocr_scan.py", "doctor")
    at.session_state["sess"] = s
    review_state(at, make_image(load_settings().tmp_dir)).run()
    next(b for b in at.button if "Confirm and attach" in b.label).click().run()
    assert len(s.timeline) == 1 and store.list_records() == []


def test_step2_staff_cannot_confirm():
    at = app("intake/ui/ocr_scan.py", "staff")
    review_state(at, make_image(load_settings().tmp_dir)).run()
    assert next(b for b in at.button if "Confirm and attach" in b.label).disabled


def test_attached_scan_appears_in_the_saved_record_after_the_quiz_consent():
    s = IntakeSession(load_graph(), load_rules())
    at = app("intake/ui/ocr_scan.py", "doctor")
    at.session_state["sess"] = s
    review_state(at, make_image(load_settings().tmp_dir)).run()
    next(b for b in at.button if "Confirm and attach" in b.label).click().run()
    s.answer("consent", "agree")
    assert s.to_record().timeline[0].type == "prescription"
