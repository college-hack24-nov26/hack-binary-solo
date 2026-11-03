"""One command for the FastAPI + React app: builds web/ if needed, then starts uvicorn (one worker) on the LAN.

  .venv/bin/python scripts/run_server.py                     # http://<this-computer>:8000  (tablets use /kiosk)
  DEMO_MODE=1 .venv/bin/python scripts/run_server.py         # "Load demo patient", red DEMO bar, /gallery
  OFFLINE_STRICT=1 DEMO_MODE=1 .venv/bin/python scripts/run_server.py   # any non-localhost connect raises and is logged
  options: --port 8000 --host 0.0.0.0 --rebuild --no-build --check-only

One worker only: records are JSON files and the audit log is a hash chain guarded by a process-wide lock (api/deps.py)."""
import argparse
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def _newest(paths) -> float:
    return max((p.stat().st_mtime for d in paths for p in Path(d).rglob("*") if p.is_file()), default=0.0)


def build_if_needed(force: bool) -> bool:
    dist = WEB / "dist" / "index.html"
    stale = force or not dist.exists() or _newest([WEB / "src"]) > dist.stat().st_mtime
    if not stale:
        return True
    npm = shutil.which("npm")
    if not npm:
        print("web/dist is missing or old and npm is not installed. Install Node.js, then: npm --prefix web ci && npm --prefix web run build")
        return dist.exists()
    if not (WEB / "node_modules").exists():
        print("Installing web dependencies (once; needs the npm registry or a local cache)…")
        subprocess.check_call([npm, "ci"], cwd=WEB)
    print("Building the web app…")
    subprocess.check_call([npm, "run", "build"], cwd=WEB)
    return True


def lan_addresses() -> list[str]:
    out = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            out.add(info[4][0])
    except OSError:
        pass
    return sorted(a for a in out if not a.startswith("127."))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--check-only", action="store_true")
    a = ap.parse_args()

    import startup_check
    checks = startup_check.check_all()
    for c in checks:
        print(f"[{c.mark}] {c.name}: {c.detail}")
    if any(not c.ok and c.critical for c in checks):
        print("\nNot ready: fix the FAIL lines above (pip install -r requirements.txt).")
        return 1
    if a.check_only:
        return 0
    if not a.no_build and not build_if_needed(a.rebuild):
        return 1
    from ocr.auth import has_users
    from ocr.config import load_settings
    if not has_users(load_settings().users_file):
        print("\nNo logins yet. Create one:  .venv/bin/python scripts/create_user.py <name> <doctor|staff>")
    print(f"\nOn this computer:  http://localhost:{a.port}/")
    for ip in lan_addresses():
        print(f"On the clinic LAN: http://{ip}:{a.port}/kiosk  (tablet)   http://{ip}:{a.port}/staff   http://{ip}:{a.port}/doctor")
    print("Ctrl+C to stop.\n")
    import uvicorn
    uvicorn.run("api.main:create_app", factory=True, host=a.host, port=a.port, workers=1, proxy_headers=False, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
