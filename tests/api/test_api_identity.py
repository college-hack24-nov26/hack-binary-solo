"""Kiosk identity: register, login, lockout, consent, masking, encryption, token isolation, audit, and no plaintext on disk."""
import json
import logging

import pytest
from fastapi.testclient import TestClient

from api_helpers import H, login, new_kiosk
from records import identity, patients, store

MOBILE = "9876543210"
ABHA = "91-1234-5678-9012"
PIN = "4821"
CONSENT = {"agreed": True, "language": "en"}


def reg(c, kind="mobile", ident=MOBILE, pin=PIN, dev="dev-1"):
    return c.post("/api/kiosk/register", json={"type": kind, "identifier": ident, "pin": pin, "consent": CONSENT}, headers={**H, "X-Kiosk-Device": dev})


def log_in(c, kind="mobile", ident=MOBILE, pin=PIN, dev="dev-1"):
    return c.post("/api/kiosk/login", json={"type": kind, "identifier": ident, "pin": pin}, headers={**H, "X-Kiosk-Device": dev})


def test_normalise_and_mask_round_trip():
    assert identity.normalise("mobile", "98765 43210") == "+919876543210"
    assert identity.normalise("mobile", "+91-9876543210") == "+919876543210"
    assert identity.normalise("abha", ABHA) == "91123456789012"
    assert identity.mask("mobile", "+919876543210") == "+91 ••••• ••210"
    assert identity.mask("abha", "91123456789012") == "91-••••-••••-9012"
    for bad in ("12345", "5876543210", "98765432100"):
        with pytest.raises(identity.IdentifierError):
            identity.normalise("mobile", bad)
    with pytest.raises(identity.IdentifierError):
        identity.normalise("abha", "1234")


def test_encrypt_decrypt_and_lookup_hash(env):
    n = identity.normalise("mobile", MOBILE)
    tok = identity.encrypt(n)
    assert n not in tok and identity.decrypt(tok) == n
    assert identity.lookup_hash("mobile", n) == identity.lookup_hash("mobile", n)
    assert identity.lookup_hash("mobile", n) != identity.lookup_hash("abha", n)
    h = identity.hash_pin("x", PIN)
    assert identity.verify_pin("x", PIN, h) and not identity.verify_pin("x", "0000", h) and not identity.verify_pin("y", PIN, h)
    assert h.startswith("$argon2id$")
    assert (env / "data" / "identity.key").stat().st_mode & 0o077 == 0          # key file is private


def test_identify_register_login(anon):
    r = anon.post("/api/kiosk/identify", json={"type": "mobile", "identifier": MOBILE}, headers=H)
    assert r.json() == {"exists": False, "masked": "+91 ••••• ••210"}
    assert patients.list_all() == []                                            # identify writes nothing
    r = reg(anon)
    assert r.status_code == 200 and r.json()["returning"] is False and r.json()["masked"] == "+91 ••••• ••210"
    assert anon.post("/api/kiosk/identify", json={"type": "mobile", "identifier": MOBILE}, headers=H).json()["exists"] is True
    assert reg(anon).status_code == 409
    ok = log_in(anon)
    assert ok.status_code == 200 and ok.json()["returning"] is True
    (p,) = patients.list_all()
    assert p.consents[0].version and p.consents[0].language == "en" and p.consents[0].kioskId and p.consents[0].agreed


def test_format_errors_have_codes(anon):
    r = anon.post("/api/kiosk/identify", json={"type": "abha", "identifier": "123"}, headers=H)
    assert r.status_code == 422 and r.headers["x-error-code"] == "abha_format"
    r = reg(anon, pin="12a4")
    assert r.status_code == 422 and r.headers["x-error-code"] == "pin_format"


def test_lockout_after_five_wrong_pins_then_staff_reset(anon, staff):
    reg(anon)
    left = []
    for i in range(4):
        r = log_in(anon, pin="0000")
        assert r.status_code == 401 and r.headers["x-error-code"] == "wrong_pin"
        left.append(r.headers["x-attempts-left"])
    assert left == ["4", "3", "2", "1"]
    r = log_in(anon, pin="0000")
    assert r.status_code == 423 and r.headers["x-error-code"] == "locked"
    r = log_in(anon, pin=PIN)                                                     # the right PIN is refused while locked
    assert r.status_code == 423
    pid = patients.list_all()[0].id
    r = staff.post(f"/api/staff/patients/{pid}/reset-pin", json={}, headers=H)
    assert r.status_code == 200
    new = r.json()["pin"]
    assert len(new) == 4 and new.isdigit()
    if new != PIN:
        assert log_in(anon, pin=PIN).status_code == 401                          # the old PIN no longer works
    assert log_in(anon, pin=new).status_code == 200
    ev = [e["event"] for e in __import__("dosing.audit", fromlist=["x"]).read()]
    assert ev.count("identity.login_failed") >= 4 and "identity.locked" in ev and "identity.pin_reset" in ev


def test_lock_survives_a_restart(env, app):
    c = TestClient(app)
    reg(c)
    for _ in range(5):
        log_in(c, pin="0000")
    from api.main import create_app
    c2 = TestClient(create_app(dist=env / "no_dist"))
    assert log_in(c2).status_code == 423


def test_device_rate_limit(anon, monkeypatch):
    monkeypatch.setenv("IDENTITY_DEVICE_RATE", "5")
    codes = [anon.post("/api/kiosk/identify", json={"type": "mobile", "identifier": f"98765432{i:02d}"}, headers={**H, "X-Kiosk-Device": "d"}).status_code for i in range(8)]
    assert codes[:5] == [200] * 5 and 429 in codes[5:]


def test_bind_records_identity_on_the_visit_and_skips_quiz_consent(anon):
    ident = reg(anon).json()["identityToken"]
    token, kh = new_kiosk(anon)
    r = anon.post(f"/api/kiosk/sessions/{token}/bind", headers={**kh, "X-Kiosk-Identity": ident})
    assert r.status_code == 200 and r.json()["stage"] == "question" and r.json()["node"]["id"] != "consent"
    rec = store.load(token)
    assert rec.identifierMasked == "+91 ••••• ••210" and rec.patientId and rec.returning is False and rec.consent.given
    # a later answer keeps the identity fields (build_for_save carries them)
    anon.post(f"/api/kiosk/sessions/{token}/answers", json={"nodeId": "age_years", "value": 40}, headers=kh)
    assert store.load(token).patientId == rec.patientId
    # second visit is "returning"
    ident2 = log_in(anon).json()["identityToken"]
    t2, kh2 = new_kiosk(anon)
    anon.post(f"/api/kiosk/sessions/{t2}/bind", headers={**kh2, "X-Kiosk-Identity": ident2})
    assert store.load(t2).returning is True


def test_declined_identity_path_stores_nothing(anon):
    token, kh = new_kiosk(anon)
    r = anon.post(f"/api/kiosk/sessions/{token}/consent", json={"choice": "decline"}, headers=kh)
    assert r.json()["stage"] == "declined"
    assert patients.list_all() == [] and store.load(token) is None


def test_walk_in_is_completed_by_staff(anon, staff):
    r = anon.post("/api/kiosk/walk-in", json={"language": "hi"}, headers=H)
    ident = r.json()["identityToken"]
    assert r.json()["walkIn"] is True
    token, kh = new_kiosk(anon)
    b = anon.post(f"/api/kiosk/sessions/{token}/bind", headers={**kh, "X-Kiosk-Identity": ident})
    assert b.json()["stage"] == "consent"                                          # a walk-in still answers the quiz consent
    (p,) = patients.list_all()
    assert p.needsStaff and p.identifierType == "walk_in"
    r = staff.post(f"/api/staff/patients/{p.id}/walk-in-complete", json={"type": "mobile", "identifier": "9123456780"}, headers=H)
    assert r.status_code == 200 and len(r.json()["pin"]) == 4 and r.json()["patient"]["masked"].endswith("780")
    assert patients.load(p.id).needsStaff is False
    assert log_in(anon, ident="9123456780", pin=r.json()["pin"]).status_code == 200


def test_identity_session_expires_when_idle(app, anon):
    ident = reg(anon).json()["identityToken"]
    for s in app.state.identity_sessions._s.values():
        s.last_seen -= 901
    token, kh = new_kiosk(anon)
    r = anon.post(f"/api/kiosk/sessions/{token}/bind", headers={**kh, "X-Kiosk-Identity": ident})
    assert r.status_code == 401 and r.headers["x-error-code"] == "identity_expired"


def test_end_drops_the_identity_session(anon):
    ident = reg(anon).json()["identityToken"]
    token, kh = new_kiosk(anon)
    h = {**kh, "X-Kiosk-Identity": ident}
    assert anon.post(f"/api/kiosk/sessions/{token}/end", headers=h).status_code == 204
    assert anon.post(f"/api/kiosk/sessions/{token}/bind", headers=h).status_code == 401


def test_staff_view_is_masked(anon, staff):
    reg(anon)
    pid = patients.list_all()[0].id
    r = staff.get(f"/api/staff/patients/{pid}")
    assert r.status_code == 200
    assert MOBILE not in r.text and "9876543210"[:7] not in r.text and r.json()["masked"] == "+91 ••••• ••210"
    assert staff.get("/api/staff/patients", params={"q": "210"}).json()["patients"][0]["id"] == pid
    assert staff.get("/api/staff/patients", params={"q": MOBILE}).json()["patients"][0]["id"] == pid       # full number: hashed lookup
    assert MOBILE not in staff.get("/api/staff/patients", params={"q": MOBILE}).text


def test_audit_entries_for_each_action_and_chain_holds(anon, staff):
    from dosing import audit
    ident = reg(anon).json()["identityToken"]
    log_in(anon, pin="0000")
    token, kh = new_kiosk(anon)
    anon.post(f"/api/kiosk/sessions/{token}/bind", headers={**kh, "X-Kiosk-Identity": ident})
    pid = patients.list_all()[0].id
    staff.post(f"/api/staff/patients/{pid}/reset-pin", json={}, headers=H)
    events = [e["event"] for e in audit.read()]
    for want in ("identity.register", "consent.recorded", "identity.login_failed", "visit.bound", "identity.pin_reset"):
        assert want in events, want
    assert audit.verify()


def test_no_plaintext_identifier_or_pin_on_disk_or_in_logs(env, anon, staff, caplog):
    caplog.set_level(logging.DEBUG)
    ident = reg(anon, kind="abha", ident=ABHA, pin="7391").json()["identityToken"]
    reg(anon, ident=MOBILE, pin=PIN)
    log_in(anon, pin="1111")
    token, kh = new_kiosk(anon)
    anon.post(f"/api/kiosk/sessions/{token}/bind", headers={**kh, "X-Kiosk-Identity": ident})
    anon.post(f"/api/kiosk/sessions/{token}/answers", json={"nodeId": "age_years", "value": 40}, headers=kh)
    pid = patients.list_all()[0].id
    tmp = staff.post(f"/api/staff/patients/{pid}/reset-pin", json={}, headers=H).json()["pin"]
    secrets_ = [MOBILE, "+91" + MOBILE, ABHA, "91123456789012", "1234-5678-9012", "12345678", "98765"]
    blob = ""
    for f in (env / "data").rglob("*"):
        if f.is_file() and f.name != "identity.key":
            blob += f.read_text(errors="ignore")
    blob += caplog.text
    for s in secrets_:
        assert s not in blob, s
    assert f'"{PIN}"' not in blob and "7391" not in blob and f'"{tmp}"' not in blob
    assert (env / "data" / "patients").is_dir() and any((env / "data" / "patients").iterdir())


def test_otp_provider_is_a_stub_that_refuses():
    from api.identity_provider import OtpProvider
    with pytest.raises(NotImplementedError):
        OtpProvider().authenticate(None, "123456")


def test_old_records_without_identity_fields_still_load():
    from intake.models import load_graph
    from intake.redflags import load_rules
    from intake.synthetic import run_bank
    from records.schema import PatientRecord
    raw = json.loads(run_bank(load_graph(), load_rules(), token="PT-OLDAAC").finish().model_dump_json())
    for k in ("patientId", "identifierType", "identifierMasked", "returning", "kioskScans"):
        del raw[k]
    old = PatientRecord.model_validate(raw)
    assert (old.patientId, old.kioskScans, old.returning) == (None, [], False)
