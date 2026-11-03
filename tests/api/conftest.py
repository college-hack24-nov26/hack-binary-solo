"""Fixtures for the HTTP API: a fresh data folder, a users file with one staff and two doctor logins, and logged-in clients."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient  # noqa: E402

from api_helpers import PASSWORDS, login  # noqa: E402
from ocr import auth  # noqa: E402


@pytest.fixture()
def env(tmp_path, monkeypatch):
    users = tmp_path / "users.json"
    auth.add_user(users, "staff_t", PASSWORDS["staff_t"], "staff")
    auth.add_user(users, "doctor1", PASSWORDS["doctor1"], "doctor")      # linked to dr_general in data/doctors.json
    auth.add_user(users, "doctor_t", PASSWORDS["doctor_t"], "doctor")
    monkeypatch.setenv("INTAKE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OCR_USERS_FILE", str(users))
    monkeypatch.setenv("OCR_TMP_DIR", str(tmp_path / "ocr_tmp"))
    monkeypatch.setenv("OLLAMA_URL", "http://localhost:9")               # nothing listens there: OCR is "down"
    for k in ("DEMO_MODE", "DOSING_DEMO_MODE", "OFFLINE_STRICT", "DOSING_FORMULARY_PATH"):
        monkeypatch.delenv(k, raising=False)
    return tmp_path


@pytest.fixture()
def app(env):
    from api.main import create_app
    return create_app(dist=env / "no_dist")


@pytest.fixture()
def anon(app):
    return TestClient(app)


@pytest.fixture()
def staff(app):
    return login(TestClient(app), "staff_t")


@pytest.fixture()
def doctor(app):
    return login(TestClient(app), "doctor_t")
