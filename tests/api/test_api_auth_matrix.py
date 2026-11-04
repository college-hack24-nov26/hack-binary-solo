"""Every route, hit as anonymous, kiosk, staff and doctor. Refused roles get 401/403; allowed roles never do.
The table must list every API route, so a new endpoint fails this test until its permissions are written down."""
import pytest
from fastapi.testclient import TestClient

from api_helpers import H, login, new_kiosk, save_demo

PUBLIC = {"anon", "kiosk", "staff", "doctor"}
SD = {"staff", "doctor"}
D = {"doctor"}
K = {"kiosk"}
KS = "/api/kiosk/sessions/{token}"
P = "/api/patients/{token}"

EXPECT = {
    ("GET", "/api/system/health"): PUBLIC, ("GET", "/api/system/config"): PUBLIC, ("GET", "/api/system/offline-status"): SD,
    ("POST", "/api/auth/login"): PUBLIC, ("POST", "/api/auth/logout"): SD, ("GET", "/api/auth/me"): SD,
    ("POST", "/api/kiosk/sessions"): PUBLIC,
    ("POST", "/api/kiosk/identify"): PUBLIC, ("POST", "/api/kiosk/register"): PUBLIC, ("POST", "/api/kiosk/login"): PUBLIC,
    ("POST", "/api/kiosk/walk-in"): PUBLIC, ("POST", KS + "/end"): K,
    ("POST", KS + "/bind"): K,
    ("POST", KS + "/scans"): K, ("GET", KS + "/scans"): K, ("GET", KS + "/scans/{sid}"): K, ("PATCH", KS + "/scans/{sid}"): K,
    ("GET", KS + "/scans/{sid}/image"): K, ("POST", KS + "/scans/{sid}/confirm"): K, ("DELETE", KS + "/scans/{sid}"): K,
    ("GET", "/api/doctor/visits/{token}/scans"): D, ("GET", "/api/doctor/visits/{token}/scans/{sid}/image"): D,
    ("POST", "/api/doctor/visits/{token}/scans/{sid}/use-as-current-medicines"): D, ("GET", "/api/doctor/visits/{token}/previous"): D,
    ("GET", "/api/staff/patients"): SD, ("GET", "/api/staff/patients/{pid}"): SD,
    ("POST", "/api/staff/patients/{pid}/reset-pin"): SD, ("POST", "/api/staff/patients/{pid}/walk-in-complete"): SD,
    ("GET", KS): K, ("POST", KS + "/consent"): K, ("POST", KS + "/answers"): K, ("POST", KS + "/bodymap"): K,
    ("POST", KS + "/skip"): K, ("POST", KS + "/back"): K, ("PUT", KS + "/language"): K, ("GET", KS + "/review"): K,
    ("POST", KS + "/doctor"): K, ("POST", KS + "/finish"): K, ("POST", KS + "/help"): K,
    ("GET", "/api/intake/body-regions"): PUBLIC, ("GET", "/api/doctors"): PUBLIC,
    ("GET", "/api/patients"): SD, ("GET", P): SD, ("PUT", P + "/vitals"): SD, ("PUT", P + "/doctor"): SD,
    ("GET", "/api/events"): SD,
    ("GET", "/api/staff/help-requests"): SD, ("POST", "/api/staff/help-requests/{rid}/dismiss"): SD,
    ("GET", P + "/summary"): D, ("PATCH", P + "/summary"): D, ("POST", P + "/summary/paragraph"): D, ("PUT", P + "/notes"): D,
    ("GET", P + "/timeline"): D, ("POST", P + "/timeline/{i}/confirm"): D, ("POST", P + "/timeline/{i}/discard"): D,
    ("GET", P + "/scans/{sid}/image"): SD, ("POST", P + "/scans"): SD,
    ("GET", "/api/dosing/drugs"): D, ("POST", "/api/dosing/history-items"): D, ("POST", P + "/history"): D,
    ("POST", "/api/dosing/evaluate"): D, ("POST", "/api/dosing/confirm"): D,
    ("GET", "/api/audit"): D, ("GET", "/api/audit/verify"): D, ("GET", "/api/audit/entries/{index}"): D, ("GET", "/api/audit/export"): D,
    ("GET", "/api/demo/fixtures"): D, ("POST", "/api/demo/load/{key}"): D, ("POST", "/api/demo/kiosk-patient"): SD,
}
IDENTITY_GATED = {("POST", KS + "/bind"), ("POST", KS + "/scans"), ("GET", KS + "/scans"), ("GET", KS + "/scans/{sid}"),
                  ("PATCH", KS + "/scans/{sid}"), ("GET", KS + "/scans/{sid}/image"), ("POST", KS + "/scans/{sid}/confirm"), ("DELETE", KS + "/scans/{sid}")}      # also need an X-Kiosk-Identity token; the allowed side is covered in test_api_identity.py
STREAMING = {("GET", "/api/events")}      # infinite stream: allowed roles are checked against a live server in test_api_live.py


def api_routes(app):
    for path, ops in app.openapi()["paths"].items():
        for m in ops:
            yield m.upper(), path


def test_every_route_has_a_permission_entry(app):
    assert set(api_routes(app)) == set(EXPECT)


@pytest.fixture()
def clients(app, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    rec = save_demo("child_fever")
    anon = TestClient(app)
    kc = TestClient(app)
    token, kh = new_kiosk(kc)
    kc.headers.update(kh)
    return {"anon": anon, "kiosk": kc, "staff": login(TestClient(app), "staff_t"), "doctor": login(TestClient(app), "doctor_t"),
            "_kiosk_token": token, "_patient": rec.token}


def _url(path: str, role: str, c: dict) -> str:
    token = c["_kiosk_token"] if path.startswith("/api/kiosk/") else c["_patient"]
    return (path.replace("{token}", token).replace("{i}", "0").replace("{sid}", "abc").replace("{rid}", "1")
            .replace("{index}", "0").replace("{pid}", "PID-AAAAAAAA").replace("{key}", "child_fever"))


def _call(client: TestClient, method: str, url: str):
    if method == "GET":
        return client.get(url)
    if method == "DELETE":
        return client.delete(url, headers=H)
    return client.request(method, url, json={}, headers=H)


@pytest.mark.parametrize("role", ["anon", "kiosk", "staff", "doctor"])
def test_role_matrix(clients, role):
    c = clients[role]
    wrong = []
    routes = sorted(EXPECT, key=lambda mp: mp[1] == "/api/auth/logout")       # sign out last
    for method, path in routes:
        allowed = role in EXPECT[(method, path)]
        if allowed and ((method, path) in STREAMING or (method, path) in IDENTITY_GATED):
            continue
        r = _call(c, method, _url(path, role, clients))
        refused = r.status_code in (401, 403)
        if allowed == refused:
            wrong.append(f"{role} {method} {path} -> {r.status_code} {r.text[:120]}")
    assert wrong == []


def test_kiosk_key_opens_only_its_own_token(app):
    c = TestClient(app)
    t1, k1 = new_kiosk(c)
    t2, k2 = new_kiosk(c)
    assert c.get(f"/api/kiosk/sessions/{t1}", headers=k1).status_code == 200
    assert c.get(f"/api/kiosk/sessions/{t2}", headers=k1).status_code == 403
    assert c.post(f"/api/kiosk/sessions/{t2}/consent", json={"choice": "agree"}, headers=k1).status_code == 403
    assert c.get(f"/api/kiosk/sessions/{t1}").status_code == 401
    assert c.get("/api/patients", headers=k1).status_code == 401          # a kiosk key is not a login


def test_mutations_need_the_csrf_header(app):
    c = TestClient(app)
    r = c.post("/api/kiosk/sessions", json={"language": "en"})
    assert r.status_code == 403 and "X-Requested-With" in r.json()["detail"]
    r = c.post("/api/auth/login", json={"username": "doctor_t", "password": "x"})
    assert r.status_code == 403


def test_login_cookie_is_httponly_and_strict(app):
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": "doctor_t", "password": "doctor-pass-456"}, headers=H)
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "secure" not in cookie


def test_lockout_after_five_failures(app):
    c = TestClient(app)
    for _ in range(5):
        assert c.post("/api/auth/login", json={"username": "staff_t", "password": "wrong"}, headers=H).status_code == 401
    r = c.post("/api/auth/login", json={"username": "staff_t", "password": "staff-pass-123"}, headers=H)
    assert r.status_code == 401 and "Too many failed attempts" in r.json()["detail"]


def test_idle_session_expires(app):
    c = login(TestClient(app), "doctor_t")
    store = app.state.sessions
    for u in store._s.values():
        u.last_seen -= store.idle_s + 1
    r = c.get("/api/auth/me")
    assert r.status_code == 401 and "inactivity" in r.json()["detail"]


def test_staff_view_has_no_doctor_fields(staff, doctor):
    rec = save_demo("child_fever")
    sv = staff.get(f"/api/patients/{rec.token}").json()
    dv = doctor.get(f"/api/patients/{rec.token}").json()
    for k in ("doctorNotes", "dosingChecks", "visitHistory", "socrates"):
        assert sv[k] is None and dv[k] is not None
