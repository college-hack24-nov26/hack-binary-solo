"""End-to-end with a fake Ollama on localhost; fails if any non-local host is contacted."""
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image
import io

from ocr import service, session
from ocr.config import load_settings

REPLY = {"documentType": "prescription", "documentDate": None,
         "medications": [{"nameAsWritten": "Tab. Paracetamol", "frequencyAsWritten": "TDS", "confidence": 0.9}],
         "labResults": [], "diagnosesAsWritten": [], "unreadable": [], "warnings": []}
state = {"bad_first": False, "calls": 0, "last_body": None}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        self._send({"models": [{"name": "qwen3-vl:8b-instruct"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        state["calls"] += 1
        state["last_body"] = body
        content = "not json" if state["bad_first"] and state["calls"] == 1 else json.dumps(REPLY)
        self._send({"message": {"content": content}})

    def _send(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers()
        self.wfile.write(b)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    s = replace(load_settings(), ollama_url=f"http://localhost:{srv.server_port}", tmp_dir=tmp_path / "ocr")
    state.update(bad_first=False, calls=0, last_body=None)
    contacted = []
    real = socket.socket.connect

    def spy(self, addr):
        contacted.append(addr[0] if isinstance(addr, tuple) else str(addr))
        return real(self, addr)
    monkeypatch.setattr(socket.socket, "connect", spy)
    yield s, contacted
    srv.shutdown()


def img(w=3000, h=2000):
    b = io.BytesIO(); Image.new("RGB", (w, h), "white").save(b, "PNG"); return b.getvalue()


def test_only_localhost_contacted(env):
    s, contacted = env
    assert service.health(s)["modelPresent"]
    r = service.extract(img(), True, "doctor", s)
    assert r["ok"]
    assert contacted and set(contacted) <= {"127.0.0.1", "::1"}, contacted


def test_request_shape_temp0_format_keepalive_resize(env):
    s, _ = env
    service.extract(img(), True, "staff", s)
    b = state["last_body"]
    assert b["options"]["temperature"] == 0 and isinstance(b["format"], dict) and b["keep_alive"]
    import base64
    im = Image.open(io.BytesIO(base64.b64decode(b["messages"][1]["images"][0])))
    assert max(im.size) == s.max_edge


def test_consent_and_role_enforced(env):
    s, _ = env
    with pytest.raises(service.OcrRefused):
        service.extract(img(), False, "doctor", s)
    with pytest.raises(service.OcrRefused):
        service.extract(img(), True, "patient", s)
    assert state["calls"] == 0


def test_retry_once_then_success(env):
    s, _ = env
    state["bad_first"] = True
    r = service.extract(img(), True, "doctor", s)
    assert r["ok"] and r["attempts"] == 2


def test_failure_needs_manual_entry(env):
    s, _ = env
    bad = replace(s, ollama_url="http://localhost:9")  # nothing listening
    r = service.extract(img(), True, "doctor", bad)
    assert r == {"ok": False, "error": r["error"], "needsManualEntry": True}


def test_bad_image_manual_entry(env):
    s, _ = env
    assert service.extract(b"junk", True, "doctor", s)["needsManualEntry"]


def test_image_lifecycle_and_startup_purge(env):
    s, _ = env
    r = service.extract(img(), True, "doctor", s)
    assert session.read(s.tmp_dir, r["sessionId"]) is not None
    session.delete(s.tmp_dir, r["sessionId"])
    assert session.read(s.tmp_dir, r["sessionId"]) is None
    r2 = service.extract(img(), True, "doctor", s)
    assert session.sweep(s.tmp_dir, ttl_s=-1) == 1  # timeout path
    (s.tmp_dir / "stale.jpg").write_bytes(b"x")
    session._purged.discard(s.tmp_dir)
    session.purge_tmp(s.tmp_dir)
    assert list(s.tmp_dir.iterdir()) == []


def test_non_local_ollama_url_rejected(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://example.com:11434")
    with pytest.raises(ValueError):
        load_settings()
