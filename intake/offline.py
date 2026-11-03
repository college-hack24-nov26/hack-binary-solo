"""Offline proof: a truthful status check and an optional hard guard. No Streamlit import, so tests can use it directly.

* status(): the only allowed outbound target (local Ollama) and whether it answers, plus one short-timeout TCP probe to a
  public host. The probe runs in a background thread and its result is cached; callers never wait on it.
* OFFLINE_STRICT=1: install_guard() makes every socket connect to a non-loopback address raise OfflineViolation and logs it.
  The public probe is not run in strict mode (it would be a violation), and the badge says so."""
import ipaddress
import logging
import os
import socket
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlparse

log = logging.getLogger("offline")
_LOCAL_NAMES = {"localhost", "localhost.localdomain"}
_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex


class OfflineViolation(ConnectionError):
    """A non-localhost network call was attempted while OFFLINE_STRICT is on."""


def _flag(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


def strict() -> bool:
    return _flag("OFFLINE_STRICT")


def demo_mode() -> bool:
    return _flag("DEMO_MODE")


@dataclass(frozen=True)
class Probe:
    host: str
    port: int
    timeout_s: float
    interval_s: int


def probe_config() -> Probe:
    e = os.environ
    return Probe(host=e.get("OFFLINE_PROBE_HOST", "1.1.1.1"), port=int(e.get("OFFLINE_PROBE_PORT", "443")),
                 timeout_s=float(e.get("OFFLINE_PROBE_TIMEOUT_S", "2")), interval_s=int(e.get("OFFLINE_CHECK_INTERVAL_S", "30")))


def is_local_host(host) -> bool:
    if isinstance(host, bytes):
        host = host.decode()
    h = str(host).strip("[]").lower()
    if h in _LOCAL_NAMES:
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def _addr_host(addr):
    if isinstance(addr, tuple):
        return addr[0]
    return None        # AF_UNIX path (str/bytes): local by definition


def _check(sock, addr) -> None:
    if sock.family == getattr(socket, "AF_UNIX", -1):
        return
    host = _addr_host(addr)
    if host is not None and not is_local_host(host):
        msg = f"OFFLINE_STRICT: blocked connection to {host}"
        log.error(msg)
        raise OfflineViolation(msg)


def _guarded_connect(self, addr):
    _check(self, addr)
    return _real_connect(self, addr)


def _guarded_connect_ex(self, addr):
    _check(self, addr)
    return _real_connect_ex(self, addr)


def install_guard() -> bool:
    """Patch socket connects once. Returns True if the guard is active."""
    if socket.socket.connect is not _guarded_connect:
        socket.socket.connect = _guarded_connect
        socket.socket.connect_ex = _guarded_connect_ex
    return True


def remove_guard() -> None:
    socket.socket.connect = _real_connect
    socket.socket.connect_ex = _real_connect_ex


def install_if_strict() -> bool:
    return install_guard() if strict() else False


# ---- status -------------------------------------------------------------------------------------------------------------

def _ollama_url() -> str:
    return os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")


def local_services() -> list[dict]:
    """The only things this app may talk to, and where its data lives."""
    from records.store import data_dir
    u = urlparse(_ollama_url())
    return [{"name": "Local model server (Ollama)", "target": f"{u.hostname}:{u.port or 80}"},
            {"name": "Local file store (records, audit log)", "target": str(data_dir().parent)}]


def check_local_model(timeout_s: float = 1.0) -> dict:
    u = urlparse(_ollama_url())
    host, port = u.hostname or "", u.port or 80
    if not is_local_host(host):
        return {"host": host, "port": port, "reachable": False, "error": "OLLAMA_URL is not localhost"}
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return {"host": host, "port": port, "reachable": True, "error": None}
    except OSError as e:
        return {"host": host, "port": port, "reachable": False, "error": type(e).__name__}


def probe_internet(p: Probe | None = None) -> dict:
    """One short-timeout TCP connect to a public host. Never raises."""
    p = p or probe_config()
    t0 = time.monotonic()
    try:
        with socket.create_connection((p.host, p.port), timeout=p.timeout_s):
            ok = True
    except OSError:
        ok = False
    return {"host": p.host, "port": p.port, "reachable": ok, "timeout_s": p.timeout_s, "took_s": round(time.monotonic() - t0, 2),
            "checked_at": time.time()}


_lock = threading.Lock()
_state: dict = {"internet": None, "running": False}


def _bg_probe() -> None:
    try:
        res = probe_internet()
    finally:
        with _lock:
            _state["running"] = False
    with _lock:
        _state["internet"] = res


def internet_cached() -> dict | None:
    """Latest probe result (None before the first one finishes). Starts a refresh thread when stale; never blocks."""
    p = probe_config()
    with _lock:
        cur = _state["internet"]
        stale = cur is None or time.time() - cur["checked_at"] >= p.interval_s
        if stale and not _state["running"]:
            _state["running"] = True
            threading.Thread(target=_bg_probe, daemon=True, name="offline-probe").start()
        return cur


def status(include_internet: bool = True) -> dict:
    s = strict()
    out = {"strict": s, "local_model": check_local_model(), "services": local_services(), "internet": None, "internet_checked": False}
    if include_internet and not s:
        out["internet"] = internet_cached()
        out["internet_checked"] = out["internet"] is not None
    return out


def headline(st: dict) -> tuple[str, str]:
    """(level, text) for the badge. level: ok | warn | pending."""
    if st["strict"]:
        return "ok", "Offline mode: no internet used (strict: outside calls blocked)"
    net = st["internet"]
    if net is None:
        return "pending", "Offline mode: no internet used · checking network…"
    if net["reachable"]:
        return "warn", "Offline mode: no internet used · Internet: reachable (not used by this app)"
    return "ok", "Offline mode: no internet used · Internet: unreachable"
