"""Against a real uvicorn server (threadpool, real concurrency): the write lock keeps the audit hash chain intact under
20 parallel evaluate+confirm calls, and the SSE stream delivers events to staff and doctor only."""
import json
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
import uvicorn

from api_helpers import H, PASSWORDS, save_demo


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def server(app):
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", workers=1))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    th.join(5)


def _client(base: str, user: str | None = None) -> httpx.Client:
    c = httpx.Client(base_url=base, headers=H, timeout=60)
    if user:
        r = c.post("/api/auth/login", json={"username": user, "password": PASSWORDS[user]})
        assert r.status_code == 200, r.text
    return c


def test_parallel_evaluate_and_confirm_keep_the_audit_chain(server):
    from dosing import audit
    from records import store
    rec = save_demo("child_fever")
    doc = _client(server, "doctor_t")
    items = doc.post("/api/dosing/history-items", json={"token": rec.token, "drug": "paracetamol"}).json()
    r = doc.post(f"/api/patients/{rec.token}/history", json={"answers": {i["field"]: "no" for i in items["unknown"]}})
    assert r.status_code == 200, r.text

    def one(_):
        c = _client(server)
        c.cookies = doc.cookies
        ev = c.post("/api/dosing/evaluate", json={"token": rec.token, "drug": "paracetamol", "indication": "pain/fever",
                                                  "confirmed": ["weight_kg"]})
        assert ev.status_code == 200, ev.text
        body = ev.json()
        assert body["result"]["status"] == "ok" and body["canConfirm"], body["card"]
        cf = c.post("/api/dosing/confirm", json={"token": rec.token, "resultId": body["resultId"], "acknowledged": False})
        assert cf.status_code == 200, cf.text
        return True

    with ThreadPoolExecutor(20) as ex:
        assert all(ex.map(one, range(20)))
    assert audit.verify() is True
    entries = audit.read()
    assert sum(e["event"] == "evaluate" for e in entries) == 20 and sum(e["event"] == "confirm" for e in entries) == 20
    assert len(store.load(rec.token).dosingChecks) == 20           # no lost update on the record either
    v = doc.get("/api/audit/verify").json()
    assert v == {"ok": True, "entries": len(entries), "firstBadIndex": None}


def test_events_stream_reaches_staff_and_refuses_anonymous(server):
    assert _client(server).get("/api/events").status_code == 401
    staff = _client(server, "staff_t")
    got: list = []

    def listen():
        with staff.stream("GET", "/api/events", timeout=10) as r:
            assert r.status_code == 200
            ev = None
            for line in r.iter_lines():
                if line.startswith("event: "):
                    ev = line[7:]
                elif line.startswith("data: ") and ev:
                    got.append((ev, json.loads(line[6:])))
                    if ev == "help.requested":
                        return
    th = threading.Thread(target=listen, daemon=True)
    th.start()
    time.sleep(0.5)
    kiosk = _client(server)
    s = kiosk.post("/api/kiosk/sessions", json={"language": "en"}).json()
    assert kiosk.post(f"/api/kiosk/sessions/{s['token']}/help", headers={"X-Kiosk-Key": s["kioskKey"]}).status_code == 204
    th.join(10)
    assert ("help.requested", {"token": s["token"], "id": 1, "at": got[-1][1]["at"]}) in got
    assert staff.get("/api/staff/help-requests").json()["items"][0]["token"] == s["token"]
