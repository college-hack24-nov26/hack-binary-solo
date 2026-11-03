"""Print the three synthetic dosing scenarios as readable text (demo script). Uses a temporary data folder.
Run: .venv/bin/python scripts/dosing_demo.py"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("INTAKE_DATA_DIR", tempfile.mkdtemp(prefix="dosing_demo_"))

from dosing import audit, demo  # noqa: E402

for title, steps in demo.run_all():
    print("=" * 100, f"\n{title}\n" + "=" * 100)
    for label, res in steps:
        print(f"\n--- {label} ---")
        print(demo.render_text(res))
print("\nAudit log:", audit.log_path(), f"({len(audit.read())} entries, chain valid: {audit.verify()})")
