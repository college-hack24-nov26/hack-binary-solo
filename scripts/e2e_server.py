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


def fake_ocr(raw, consent, role, s=None, progress=None):
    """Stand-in for the local vision model in browser tests: takes about 2 s, reports real stage and token progress, returns one
    clear and one low-confidence medicine. The real model is covered by scripts/ocr_smoke.py (needs Ollama)."""
    import time
    progress("reading", 0)
    for n in range(0, 450, 50):
        time.sleep(0.2)
        progress("reading", n)
    progress("structuring", 0)
    meds = [{"nameAsWritten": "Amoxicillin", "strength": "500 mg", "frequencyAsWritten": "1-0-1", "confidence": 0.95},
            {"nameAsWritten": "Paracetamol", "strength": None, "frequencyAsWritten": "SOS", "confidence": 0.4}]
    return {"ok": True, "sessionId": None, "latencyS": 2.0, "attempts": 1, "jpeg": raw,
            "result": {"documentType": "prescription", "documentDate": "03/09/2026", "medications": meds, "labResults": [],
                       "diagnosesAsWritten": [], "unreadable": [], "warnings": []}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--strict", action="store_true", help="OFFLINE_STRICT=1")
    ap.add_argument("--no-demo", action="store_true")
    ap.add_argument("--real-ocr", action="store_true", help="use the real OCR backend for the kiosk scan step (needs Ollama)")
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
    from api.main import create_app
    app = create_app()
    if not a.real_ocr:
        app.state.ocr_fn = fake_ocr
    uvicorn.run(app, host="127.0.0.1", port=a.port, workers=1, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
