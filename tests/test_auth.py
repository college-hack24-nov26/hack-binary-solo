import json
import os
import stat
import time

import pytest

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


