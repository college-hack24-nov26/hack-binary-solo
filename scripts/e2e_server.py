"""Server for the Playwright suites: a fresh temporary data folder and users file (synthetic logins with known test passwords),
DEMO_MODE on, then uvicorn on 127.0.0.1. Never point this at real data.  Usage: scripts/e2e_server.py [--port 8765] [--strict]"""
import argparse
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

USERS = {"staff_e2e": ("staff-e2e-pass", "staff"), "doctor1": ("doctor-e2e-pass", "doctor")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--strict", action="store_true", help="OFFLINE_STRICT=1")
    ap.add_argument("--no-demo", action="store_true")
    a = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="medikiosk_e2e_"))
    os.environ["INTAKE_DATA_DIR"] = str(tmp / "data")
    os.environ["OCR_USERS_FILE"] = str(tmp / "users.json")
    os.environ["OCR_TMP_DIR"] = str(tmp / "ocr")
    os.environ.setdefault("OLLAMA_URL", "http://localhost:9")       # OCR "down" unless the caller sets a real local Ollama
    if not a.no_demo:
        os.environ["DEMO_MODE"] = "1"
    if a.strict:
        os.environ["OFFLINE_STRICT"] = "1"
    from ocr.auth import add_user
    for u, (pw, role) in USERS.items():
        add_user(tmp / "users.json", u, pw, role)
    print(f"e2e data folder: {tmp}", flush=True)
    import uvicorn
    uvicorn.run("api.main:create_app", factory=True, host="127.0.0.1", port=a.port, workers=1, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
