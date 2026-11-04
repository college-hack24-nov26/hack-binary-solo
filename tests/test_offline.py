"""Offline proof: truthful status, non-blocking probe, static check for outside URLs, and the OFFLINE_STRICT guard."""
import logging
import re
import socket
import threading
import time
from pathlib import Path

import pytest

from intake import offline

ROOT = Path(__file__).resolve().parent.parent
APP_DIRS = ["intake", "ocr", "dosing", "records", "scripts", "api"]
APP_FILES: list[str] = []      # the Streamlit entry points were removed; the app is api/ + web/
WEB_DIRS = ["web/src", "web/index.html"]        # the React app: no CDN, fonts or icons from outside
WEB_EXT = {".ts", ".tsx", ".js", ".jsx", ".css", ".html", ".json", ".svg"}
URL = re.compile(r"""https?://([A-Za-z0-9.\-\[\]:]+)""")
XML_NAMESPACES = {"www.w3.org"}      # SVG xmlns strings are identifiers, not requests


def app_sources():
    for d in APP_DIRS:
        yield from (ROOT / d).rglob("*.py")
    for f in APP_FILES:
        if (ROOT / f).exists():
            yield ROOT / f
    for d in WEB_DIRS:
        p = ROOT / d
        if p.is_file():
            yield p
        elif p.is_dir():
            yield from (f for f in p.rglob("*") if f.suffix in WEB_EXT)


def test_no_non_localhost_urls_in_app_code():
    bad = []
    for p in app_sources():
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for m in URL.finditer(line):
                host = m.group(1).split(":")[0].rstrip(".")
                if not offline.is_local_host(host) and host not in XML_NAMESPACES:
                    bad.append(f"{p.relative_to(ROOT)}:{n}: {m.group(0)}")
    assert bad == [], bad


@pytest.fixture()
def guard():
    offline.install_guard()
    yield
    offline.remove_guard()


def test_strict_guard_blocks_and_logs_non_local(guard, caplog):
    with caplog.at_level(logging.ERROR, logger="offline"):
        with pytest.raises(offline.OfflineViolation):
            socket.create_connection(("93.184.216.34", 80), timeout=1)
    assert any("93.184.216.34" in r.message for r in caplog.records)


def test_strict_guard_allows_localhost(guard):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    with socket.create_connection(("127.0.0.1", srv.getsockname()[1]), timeout=1):
        pass
    srv.close()


def test_install_if_strict_follows_the_flag(monkeypatch):
    monkeypatch.delenv("OFFLINE_STRICT", raising=False)
    assert offline.install_if_strict() is False and socket.socket.connect is not offline._guarded_connect
    monkeypatch.setenv("OFFLINE_STRICT", "1")
    try:
        assert offline.install_if_strict() is True and socket.socket.connect is offline._guarded_connect
    finally:
        offline.remove_guard()


def test_status_in_strict_mode_skips_the_public_probe(monkeypatch):
    monkeypatch.setenv("OFFLINE_STRICT", "1")
    st = offline.status()
    assert st["internet"] is None and st["strict"] is True and "strict" in offline.headline(st)[1]


def test_probe_reports_unreachable_and_respects_timeout(monkeypatch):
    def fake(addr, timeout=None):
        assert timeout == 2.0
        raise OSError("no route")
    monkeypatch.setattr(socket, "create_connection", fake)
    r = offline.probe_internet()
    assert r["reachable"] is False and r["timeout_s"] == 2.0


def test_probe_reports_reachable_in_amber(monkeypatch):
    class C:
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(socket, "create_connection", lambda a, timeout=None: C())
    st = {"strict": False, "internet": offline.probe_internet()}
    level, text = offline.headline(st)
    assert level == "warn" and "reachable (not used by this app)" in text


def test_cached_probe_never_blocks_the_caller(monkeypatch):
    gate = threading.Event()
    monkeypatch.setattr(offline, "_state", {"internet": None, "running": False})
    monkeypatch.setattr(offline, "probe_internet", lambda p=None: (gate.wait(5), {"reachable": False, "checked_at": time.time(), "took_s": 0})[1])
    t0 = time.monotonic()
    assert offline.internet_cached() is None
    assert time.monotonic() - t0 < 0.5
    gate.set()
    for _ in range(50):
        if offline.internet_cached() is not None:
            break
        time.sleep(0.05)
    assert offline.internet_cached()["reachable"] is False


def test_local_model_check_reports_unreachable(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://localhost:9")
    assert offline.check_local_model()["reachable"] is False


def test_probe_config_is_configurable(monkeypatch):
    monkeypatch.setenv("OFFLINE_PROBE_HOST", "8.8.8.8")
    monkeypatch.setenv("OFFLINE_PROBE_TIMEOUT_S", "0.5")
    p = offline.probe_config()
    assert (p.host, p.timeout_s) == ("8.8.8.8", 0.5)
