import json
import os
import stat
import time

import pytest
from streamlit.testing.v1 import AppTest

from ocr import auth

APP = os.path.join(os.path.dirname(__file__), "..", "app.py")


@pytest.fixture()
def users(tmp_path):
    f = tmp_path / "users.json"
    auth.add_user(f, "Dr.Test", "correct-horse", "doctor")
    auth.add_user(f, "nurse1", "another-pass1", "staff")
    return f


def test_hash_is_salted_and_verifies():
    a, b = auth.hash_password("secret-pw-1"), auth.hash_password("secret-pw-1")
    assert a != b and "secret-pw-1" not in a
    assert auth.verify_password("secret-pw-1", a) and not auth.verify_password("wrong", a)
    assert not auth.verify_password("x", "garbage")


def test_user_file_private_and_plaintext_free(users):
    assert stat.S_IMODE(os.stat(users).st_mode) == 0o600
    raw = users.read_text()
    assert "correct-horse" not in raw and json.loads(raw)["dr.test"]["role"] == "doctor"


def test_add_user_validation(users):
    with pytest.raises(ValueError): auth.add_user(users, "x", "short", "doctor")
    with pytest.raises(ValueError): auth.add_user(users, "y", "long-enough-1", "patient")
    with pytest.raises(ValueError): auth.add_user(users, "dr.test", "long-enough-1", "doctor")


def test_login_success_and_failure(users):
    a = auth.Authenticator(users)
    assert a.login(" DR.test ", "correct-horse")[0] == {"username": "dr.test", "role": "doctor"}
    assert a.login("dr.test", "nope")[0] is None
    assert a.login("ghost", "whatever")[0] is None


def test_lockout_and_recovery(users):
    now = [1000.0]
    a = auth.Authenticator(users, max_failures=3, lockout_s=60, clock=lambda: now[0])
    for _ in range(3):
        assert a.login("dr.test", "bad")[0] is None
    user, msg = a.login("dr.test", "correct-horse")  # right password still blocked while locked
    assert user is None and "Too many" in msg
    now[0] += 61
    assert a.login("dr.test", "correct-horse")[0] is not None


def test_idle_expiry():
    assert auth.idle_expired(time.time() - 1000, 900)
    assert not auth.idle_expired(time.time() - 10, 900)


def _app(users, monkeypatch):
    monkeypatch.setenv("OCR_USERS_FILE", str(users))
    return AppTest.from_file(APP, default_timeout=60)


def test_app_blocks_until_login(users, monkeypatch):
    at = _app(users, monkeypatch).run()
    assert not at.exception
    assert [b.label for b in at.button] == ["Sign in"]  # only the login form
    assert at.text_input[1].proto.type == 1  # masked password field
    assert not at.file_uploader and not at.checkbox  # no OCR controls before login


def test_app_login_flow_and_role_gating(users, monkeypatch):
    at = _app(users, monkeypatch).run()
    at.text_input[0].input("nurse1"); at.text_input[1].input("wrong-pass"); at.button[0].click().run()
    assert at.session_state["auth"] is None and at.error
    at.text_input[0].input("nurse1"); at.text_input[1].input("another-pass1"); at.button[0].click().run()
    assert at.session_state["auth"]["role"] == "staff" and at.checkbox  # consent box now visible


def test_app_idle_timeout_drops_session(users, monkeypatch):
    at = _app(users, monkeypatch).run()
    at.text_input[0].input("dr.test"); at.text_input[1].input("correct-horse"); at.button[0].click().run()
    assert at.session_state["auth"]
    at.session_state["auth"]["last_seen"] = time.time() - 99999
    at.run()
    assert at.session_state["auth"] is None and not at.checkbox
