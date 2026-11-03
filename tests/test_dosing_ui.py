"""AppTest smoke for the doctor-only dosage panel."""
import time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from records import store
from records.schema import PatientRecord

from dosing_helpers import quiz

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def datadir(tmp_path, monkeypatch):
    monkeypatch.setenv("INTAKE_DATA_DIR", str(tmp_path))
    store.save(PatientRecord(token="PT-ABCDEF", createdAt="2026-01-01T00:00:00", updatedAt="2026-01-01T00:00:00", answers=quiz(age_y=5, wt=18)))


def page(role):
    at = AppTest.from_file(str(ROOT / "intake" / "ui" / "doctor.py"), default_timeout=30)
    at.session_state["auth"] = {"username": f"test_{role}", "role": role, "last_seen": time.time()}
    return at


def test_doctor_sees_banner_and_can_run_a_check():
    at = page("doctor").run()
    assert not at.exception
    assert any("not clinically verified" in e.value for e in at.error)
    at.button(key="dc_run_PT-ABCDEF").click().run()
    assert not at.exception
    assert any("Result" in s.value for s in at.subheader)


def test_staff_cannot_run_a_check():
    at = page("staff").run()
    assert not at.exception
    assert not [b for b in at.button if b.key and b.key.startswith("dc_run_")]


def test_dosage_page_runs_a_check():
    at = AppTest.from_file(str(ROOT / "intake" / "ui" / "dosage.py"), default_timeout=30)
    at.session_state["auth"] = {"username": "test_doctor", "role": "doctor", "last_seen": time.time()}
    at.run()
    assert not at.exception
    at.button(key="dc_run_PT-ABCDEF").click().run()
    assert not at.exception and any("Result" in s.value for s in at.subheader)
