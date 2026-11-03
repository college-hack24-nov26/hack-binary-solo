"""Login gate on the intake Staff and Doctor pages. Uses a throw-away users file, never data/users.json."""
import time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from intake.bodymap import make_answer
from intake.models import load_graph
from intake.redflags import load_rules
from intake.synthetic import run_bank
from intake.ui.gate import can_edit
from ocr import auth
from records import store

ROOT = Path(__file__).resolve().parent.parent
PW = "correct-horse-1"


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    users = tmp_path / "users.json"
    auth.add_user(users, "dr", PW, "doctor")
    auth.add_user(users, "nurse", PW, "staff")
    monkeypatch.setenv("OCR_USERS_FILE", str(users))
    monkeypatch.setenv("INTAKE_DATA_DIR", str(tmp_path / "data"))
    store.save(run_bank(load_graph(), load_rules(), {"chief_complaint": "chest_pain",
               "cp_site": make_answer(["chest_center"], "list")}, token="PT-GATEAA").finish())
    return tmp_path


def page(name):
    return AppTest.from_file(str(ROOT / "intake" / "ui" / f"{name}.py"), default_timeout=20)


def login(at, user, pw=PW):
    at.text_input[0].set_value(user)
    at.text_input[1].set_value(pw)
    return at.button[0].click().run()


def test_can_edit_only_doctor():
    assert can_edit("doctor") and not can_edit("staff") and not can_edit(None)


@pytest.mark.parametrize("name", ["staff", "doctor"])
def test_pages_show_login_and_no_patient_data_when_signed_out(name):
    at = page(name).run()
    assert not at.exception and at.title[0].value == "Sign in"
    assert not at.expander and not at.text_area                    # nothing from data_local is rendered


def test_wrong_password_rejected_and_stays_locked_out():
    at = page("staff").run()
    login(at, "nurse", "wrong-password")
    assert at.error and "Invalid" in at.error[0].value and at.title[0].value == "Sign in"


def test_staff_sees_board_after_login():
    at = login(page("staff").run(), "nurse")
    assert not at.exception and at.title[0].value == "Staff alerts" and at.expander


def test_staff_can_view_but_not_edit_summary():
    at = login(page("doctor").run(), "nurse")
    assert not at.exception and at.info[0].value.startswith("Read-only")
    assert at.text_area and all(t.disabled for t in at.text_area)
    assert all(b.disabled for b in at.button if b.label in ("Save edits", "Attach"))


def test_doctor_can_edit_summary():
    at = login(page("doctor").run(), "dr")
    assert not at.exception and not any(i.value.startswith("Read-only") for i in at.info)
    assert at.text_area and not any(t.disabled for t in at.text_area[:1])


def test_idle_session_is_logged_out():
    at = page("staff")
    at.session_state["auth"] = {"username": "nurse", "role": "staff", "last_seen": time.time() - 10_000}
    at.run()
    assert at.title[0].value == "Sign in" and "inactivity" in at.info[0].value


def test_patient_kiosk_needs_no_login():
    at = page("patient").run()
    assert not at.exception and "I agree" in [b.label for b in at.button]


def test_doctor_red_flag_line_uses_readable_answers_and_diagram_renders():
    at = login(page("doctor").run(), "dr")
    flag = at.error[0].value
    assert "Triggered by:" in flag and "{'regions'" not in flag and "Site: Chest, centre" in flag
    assert at.expander[0].label.startswith("Body diagram") and not at.exception
