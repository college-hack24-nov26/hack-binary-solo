"""Kiosk scans with a fake OCR backend: lifecycle, progress, retake, OCR unavailable, correction, confirm, delete, isolation,
the doctor's unverified panel and the one path into the dosage check. The real model is never called."""
import io
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from api_helpers import H, login, new_kiosk
from records import patients, scanfiles, store

MOBILE = "9876543210"
FIXTURE = [("Amoxicillin", "500 mg", "1-0-1", 0.95), ("Paracetamol", "650 mg", None, 0.4)]


def page_jpeg(bad: str | None = None) -> bytes:
    im = Image.new("RGB", (900, 1200), "white")
    d = ImageDraw.Draw(im)
    for y in range(40, 1150, 22):
        d.text((40, y), "Tab. Amoxicillin 500 mg 1-0-1 x 5 days  #%d" % y, fill="black")
    if bad == "dark":
        im = im.point(lambda v: int(v * 0.15))
    out = io.BytesIO()
    im.save(out, "JPEG")
    return out.getvalue()


def fake_ocr(raw, consent, role, s=None, progress=None):
    assert role == "kiosk" and consent is True
    for n in (0, 100, 250):
        progress("reading", n)
        time.sleep(0.01)
    progress("structuring", 0)
    meds = [{"nameAsWritten": n, "strength": st, "frequencyAsWritten": fr, "confidence": c} for n, st, fr, c in FIXTURE]
    return {"ok": True, "sessionId": None, "latencyS": 0.1, "attempts": 1, "jpeg": raw,
            "result": {"documentType": "prescription", "documentDate": "03/09/2026", "medications": meds, "labResults": [],
                       "diagnosesAsWritten": ["Fever"], "unreadable": [], "warnings": []}}


@pytest.fixture()
def kc(app):
    app.state.ocr_fn = fake_ocr
    c = TestClient(app)
    r = c.post("/api/kiosk/register", json={"type": "mobile", "identifier": MOBILE, "pin": "4821", "consent": {"agreed": True, "language": "en"}}, headers=H)
    ident = r.json()["identityToken"]
    token, kh = new_kiosk(c)
    h = {**kh, "X-Kiosk-Identity": ident}
    assert c.post(f"/api/kiosk/sessions/{token}/bind", headers=h).status_code == 200
    return c, token, h


def upload(c, token, h, jpeg=None):
    return c.post(f"/api/kiosk/sessions/{token}/scans", files={"image": ("p.jpg", jpeg or page_jpeg(), "image/jpeg")}, headers=h)


def wait_done(c, token, h, sid, want=("done", "failed")):
    for _ in range(200):
        r = c.get(f"/api/kiosk/sessions/{token}/scans/{sid}", headers=h).json()
        if r["status"] in want:
            return r
        time.sleep(0.02)
    raise AssertionError("job never ended")


def test_scan_lifecycle_extracts_fields_and_flags_low_confidence(kc):
    c, token, h = kc
    r = upload(c, token, h)
    assert r.status_code == 200 and r.json()["status"] in ("queued", "preparing", "reading", "done")
    sid = r.json()["id"]
    done = wait_done(c, token, h, sid)
    assert done["status"] == "done" and done["unverified"] is True and done["progress"] == 1.0
    assert done["docType"] == "prescription" and done["docDate"]["value"] == "03/09/2026" and "Fever" in done["freeText"]
    a, b = done["medicines"]
    assert a["name"]["value"] == "Amoxicillin" and a["dose"]["value"] == "500 mg" and a["frequency"]["check"] is False
    assert b["name"]["check"] is True and b["frequency"]["value"] is None and b["frequency"]["check"] is True      # low confidence, missing


def test_progress_is_real_stage_data(kc, monkeypatch):
    c, token, h = kc
    from api import scan_jobs
    snaps = []

    def slow(raw, consent, role, s=None, progress=None):
        progress("reading", 0)
        snaps.append(scan_jobs.progress_of({"id": next(iter(scan_jobs.LIVE)), "status": "reading"}))
        progress("reading", 250)
        snaps.append(scan_jobs.progress_of({"id": next(iter(scan_jobs.LIVE)), "status": "reading"}))
        return fake_ocr(raw, consent, role, s, lambda *_: None)
    c.app.state.ocr_fn = slow
    sid = upload(c, token, h).json()["id"]
    wait_done(c, token, h, sid)
    (st0, p0, _), (st1, p1, _) = snaps
    assert st0 == st1 == "reading" and 0.1 <= p0 < p1 < 0.93


def test_blurry_or_dark_picture_asks_for_a_retake_and_stores_nothing(kc):
    c, token, h = kc
    r = upload(c, token, h, page_jpeg("dark"))
    assert r.json()["status"] == "retake" and r.json()["message"] == "dark"
    blur = io.BytesIO()
    Image.open(io.BytesIO(page_jpeg())).filter(__import__("PIL.ImageFilter", fromlist=["x"]).GaussianBlur(8)).save(blur, "JPEG")
    r = upload(c, token, h, blur.getvalue())
    assert r.json()["status"] == "retake" and r.json()["message"] == "blurry"
    assert store.load(token).kioskScans == [] and list(scanfiles.folder().iterdir()) == []


def test_ocr_unavailable_keeps_the_picture_for_the_doctor(kc, app):
    c, token, h = kc
    c.app.state.ocr_fn = __import__("ocr.service", fromlist=["x"]).extract       # the real one; env OLLAMA_URL points nowhere
    r = upload(c, token, h)
    assert r.json()["status"] == "unavailable" and r.json()["message"] == "model_down" and r.json()["hasImage"]
    sid = r.json()["id"]
    assert c.post(f"/api/kiosk/sessions/{token}/scans/{sid}/confirm", headers=h).json()["confirmed"] is True
    assert c.get(f"/api/kiosk/sessions/{token}/scans/{sid}/image", headers=h).status_code == 200


def test_ocr_failure_ends_the_job(kc):
    c, token, h = kc
    c.app.state.ocr_fn = lambda *a, **k: {"ok": False, "error": "x", "needsManualEntry": True}
    sid = upload(c, token, h).json()["id"]
    assert wait_done(c, token, h, sid)["status"] == "failed"


def test_patient_corrects_confirms_and_deletes(kc, monkeypatch):
    c, token, h = kc
    sid = upload(c, token, h).json()["id"]
    wait_done(c, token, h, sid)
    base = f"/api/kiosk/sessions/{token}/scans/{sid}"
    r = c.patch(base, json={"medicines": [{"name": "Paracetamol", "dose": "500 mg", "frequency": "SOS"}]}, headers=H | h)
    assert r.json()["medicines"][0]["frequency"] == {"value": "SOS", "confidence": None, "check": False}
    monkeypatch.setenv("KIOSK_SCAN_KEEP_IMAGE", "0")
    assert c.post(base + "/confirm", headers=h).json()["hasImage"] is False
    assert c.get(base + "/image", headers=h).status_code == 404 and scanfiles.read(sid) is None
    assert c.patch(base, json={"freeText": "x"}, headers=h).status_code == 409           # confirmed papers are locked
    assert c.delete(base, headers=h).status_code == 204
    assert c.get(base, headers=h).status_code == 404 and store.load(token).kioskScans == []


def test_end_discards_unconfirmed_scans_but_keeps_confirmed(kc):
    c, token, h = kc
    a = upload(c, token, h).json()["id"]
    b = upload(c, token, h).json()["id"]
    wait_done(c, token, h, a)
    wait_done(c, token, h, b)
    c.post(f"/api/kiosk/sessions/{token}/scans/{a}/confirm", headers=h)
    assert c.post(f"/api/kiosk/sessions/{token}/end", headers=h).status_code == 204
    assert [s["id"] for s in store.load(token).kioskScans] == [a] and scanfiles.read(b) is None and scanfiles.read(a)


def test_walk_in_and_anonymous_cannot_scan(app):
    app.state.ocr_fn = fake_ocr
    c = TestClient(app)
    ident = c.post("/api/kiosk/walk-in", json={"language": "en"}, headers=H).json()["identityToken"]
    token, kh = new_kiosk(c)
    h = {**kh, "X-Kiosk-Identity": ident}
    c.post(f"/api/kiosk/sessions/{token}/bind", headers=h)
    c.post(f"/api/kiosk/sessions/{token}/consent", json={"choice": "agree"}, headers=kh)
    r = upload(c, token, h)
    assert r.status_code == 403 and r.headers["x-error-code"] == "walkin_no_scans"
    t2, k2 = new_kiosk(c)                                                                 # anonymous: no identity at all
    assert upload(c, t2, k2).status_code == 401


def test_identity_token_isolation(app):
    c = TestClient(app)
    reg = lambda cl, ident: cl.post("/api/kiosk/register", json={"type": "mobile", "identifier": ident, "pin": "4821", "consent": {"agreed": True, "language": "en"}}, headers=H).json()["identityToken"]   # noqa: E731
    ia, ib = reg(c, MOBILE), reg(c, "9000000001")
    h = {"X-Kiosk-Identity": ia}
    for url in ("/api/patients", "/api/audit", "/api/auth/me", "/api/dosing/drugs", "/api/staff/help-requests", "/api/staff/patients"):
        assert TestClient(app).get(url, headers=h).status_code in (401, 403), url
    assert TestClient(app).post("/api/staff/patients/PID-AAAAAAAA/reset-pin", json={}, headers={**H, **h}).status_code in (401, 403)
    tb, khb = new_kiosk(c)
    c.post(f"/api/kiosk/sessions/{tb}/bind", headers={**khb, "X-Kiosk-Identity": ib})
    ta, kha = new_kiosk(c)
    c.post(f"/api/kiosk/sessions/{ta}/bind", headers={**kha, "X-Kiosk-Identity": ia})
    assert c.get(f"/api/kiosk/sessions/{tb}/scans", headers={**khb, "X-Kiosk-Identity": ia}).status_code == 404     # B's key, A's identity
    assert c.get(f"/api/kiosk/sessions/{tb}/scans", headers={**kha, "X-Kiosk-Identity": ia}).status_code == 403     # A's key on B's visit
    assert c.get(f"/api/kiosk/sessions/{ta}/scans", headers=kha).status_code == 401
    assert c.get(f"/api/kiosk/sessions/{ta}/scans", headers={**kha, "X-Kiosk-Identity": ia + "x"}).status_code == 401
    assert c.get(f"/api/kiosk/sessions/{ta}/scans", headers={**kha, "X-Kiosk-Identity": ia}).status_code == 200


def test_doctor_sees_unverified_papers_and_only_a_doctor_action_reaches_the_dosage_context(kc, app, doctor, staff):
    c, token, h = kc
    sid = upload(c, token, h).json()["id"]
    wait_done(c, token, h, sid)
    assert doctor.get(f"/api/doctor/visits/{token}/scans").json()["scans"] == []          # unconfirmed papers are not shown
    c.post(f"/api/kiosk/sessions/{token}/scans/{sid}/confirm", headers=h)
    d = doctor.get(f"/api/doctor/visits/{token}/scans").json()
    assert d["scans"][0]["label"] == "Patient-supplied, unverified text" and d["scans"][0]["medicines"][0]["name"] == "Amoxicillin"
    assert doctor.get(f"/api/doctor/visits/{token}/scans/{sid}/image").status_code == 200
    assert staff.get(f"/api/doctor/visits/{token}/scans").status_code == 403
    # before the doctor acts, the engine sees nothing from the scan
    from dosing import mapper
    rec = store.load(token)
    ctx = mapper.map_record(rec)
    assert ctx.ocr_meds == [] and rec.timeline == []
    r = doctor.post(f"/api/doctor/visits/{token}/scans/{sid}/use-as-current-medicines", json={}, headers=H)
    assert r.status_code == 200 and r.json()["added"] == 2
    assert doctor.post(f"/api/doctor/visits/{token}/scans/{sid}/use-as-current-medicines", json={}, headers=H).status_code == 409
    rec = store.load(token)
    assert all(i["provenance"] == "patient_scan_unverified_doctor_used" for i in rec.timeline[0].items) and rec.timeline[0].confirmedBy == "doctor_t"
    ctx = mapper.map_record(rec)
    assert {m.name.lower() if hasattr(m, "name") else str(m).lower() for m in ctx.ocr_meds} and ctx.ocr_meds[0].source == "ocr_doctor_confirmed"


def test_previous_visits_timeline_for_a_returning_patient(kc, doctor):
    c, token, h = kc
    from records.build import build_record  # noqa: F401
    p = patients.list_all()[0]
    from intake.models import load_graph
    from intake.redflags import load_rules
    from intake.synthetic import run_bank
    old = run_bank(load_graph(), load_rules(), token="PT-OLDVST").finish().model_copy(update={"queueNumber": 4, "queueDate": "2026-10-01", "patientId": p.id})
    store.save(old)
    p.visitIds.insert(0, "PT-OLDVST")
    patients.save(p)
    v = doctor.get(f"/api/doctor/visits/{token}/previous").json()["visits"]
    assert [x["token"] for x in v] == ["PT-OLDVST"] and v[0]["date"] == "2026-10-01"


def test_slip_and_board_show_papers_and_masked_identifier(kc, staff):
    c, token, h = kc
    sid = upload(c, token, h).json()["id"]
    wait_done(c, token, h, sid)
    c.post(f"/api/kiosk/sessions/{token}/scans/{sid}/confirm", headers=h)
    row = [r for r in staff.get("/api/patients").json()["rows"] if r["token"] == token][0]
    assert row["identifierMasked"] == "+91 ••••• ••210" and row["identityState"] == "new" and row["papersCount"] == 1
    assert row["statusText"] == "Identified, no token yet"


def test_scan_audit_entries(kc):
    from dosing import audit
    c, token, h = kc
    sid = upload(c, token, h).json()["id"]
    wait_done(c, token, h, sid)
    c.post(f"/api/kiosk/sessions/{token}/scans/{sid}/confirm", headers=h)
    c.delete(f"/api/kiosk/sessions/{token}/scans/{sid}", headers=h)
    ev = [e["event"] for e in audit.read()]
    for want in ("scan.created", "scan.read", "scan.confirmed", "scan.deleted"):
        assert want in ev, want
    assert audit.verify()
