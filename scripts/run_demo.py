"""One-command demo launcher: startup check, demo login and synthetic patients if none exist, then Streamlit.
Run: python3 scripts/run_demo.py [--port 8501] [--demo-mode] [--no-seed] [--check-only]
Works without Ollama (OCR scan is then unavailable; quiz, staff board, doctor summary and dosing work)."""
import argparse
import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8501)
    ap.add_argument("--demo-mode", action="store_true", help="red DEMO banner and UNVERIFIED rules allowed (DOSING_DEMO_MODE=1)")
    ap.add_argument("--no-seed", action="store_true", help="do not add the three synthetic dosing patients")
    ap.add_argument("--check-only", action="store_true")
    a = ap.parse_args()
    if a.demo_mode:
        os.environ["DOSING_DEMO_MODE"] = "1"

    import startup_check
    checks = startup_check.check_all()
    for c in checks:
        print(f"[{c.mark}] {c.name}: {c.detail}")
    if any(not c.ok and c.critical for c in checks):
        print("\nNot ready: fix the FAIL lines above (pip install -r requirements.txt).")
        return 1
    if a.check_only:
        return 0

    from ocr.auth import add_user, has_users
    from ocr.config import load_settings
    s = load_settings()
    if not has_users(s.users_file):
        pw = secrets.token_urlsafe(9)
        add_user(s.users_file, "demo", pw, "doctor")
        print(f"\nCreated demo login ->  username: demo   password: {pw}   (role: doctor; shown once)")
    if not a.no_seed:
        from dosing import demo
        from records import store
        if not store.list_records():
            for key in demo.DEMO_PATIENTS:
                store.save(demo.record(key))
            print("Added 3 synthetic dosing patients: " + ", ".join(p["token"] for p in demo.DEMO_PATIENTS.values()))
    print(f"\nStarting the app: http://localhost:{a.port}   (Ctrl+C to stop)\n")
    return subprocess.call([sys.executable, "-m", "streamlit", "run", str(ROOT / "main_app.py"), "--server.port", str(a.port),
                            "--server.headless", "false"], cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main())
