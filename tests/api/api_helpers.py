"""Shared helpers for the API tests (imported by conftest.py and the test modules)."""
import json

from fastapi.testclient import TestClient

H = {"X-Requested-With": "medikiosk"}
PASSWORDS = {"staff_t": "staff-pass-123", "doctor1": "doctor-pass-123", "doctor_t": "doctor-pass-456"}


def login(client: TestClient, username: str) -> TestClient:
    r = client.post("/api/auth/login", json={"username": username, "password": PASSWORDS[username]}, headers=H)
    assert r.status_code == 200, r.text
    return client


def new_kiosk(client: TestClient, language: str = "en") -> tuple[str, dict]:
    r = client.post("/api/kiosk/sessions", json={"language": language}, headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    return body["token"], {**H, "X-Kiosk-Key": body["kioskKey"]}


def save_demo(key: str):
    from dosing import demo
    from records import store
    rec = demo.record(key)
    store.save(rec)
    return rec


def dumps(x) -> str:
    return json.dumps(x, sort_keys=True, ensure_ascii=False)
