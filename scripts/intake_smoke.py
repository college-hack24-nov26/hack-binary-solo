"""Run 3 synthetic patients end to end (no UI, no network) and print record + doctor summary.
Each patient's clock advances 2 s per call so the printed duration is deterministic."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intake.models import load_graph  # noqa: E402
from intake.redflags import load_rules  # noqa: E402
from intake.summary import build_summary, render_text  # noqa: E402
from intake.synthetic import PATIENTS, run_bank  # noqa: E402
from ocr.timeline import to_timeline_entry  # noqa: E402
from records.schema import TimelineEntry  # noqa: E402

OCR_SAMPLE = {  # synthetic, shaped like the OCR module's confirmed result
    "documentType": "prescription", "documentDate": "2025-08-14",
    "medications": [{"nameAsWritten": "Tab. Paracetamol", "strength": "500 mg", "frequencyAsWritten": "TDS"}],
    "labResults": [], "diagnosesAsWritten": []}


def ticking_clock(step_s: int = 2):
    t = [datetime(2026, 11, 3, 10, 0, 0, tzinfo=timezone.utc)]

    def now():
        t[0] += timedelta(seconds=step_s)
        return t[0]
    return now


def main() -> int:
    graph, rules = load_graph(), load_rules()
    for i, (name, overrides) in enumerate(PATIENTS.items()):
        s = run_bank(graph, rules, overrides, clock=ticking_clock(), token=f"PT-SMOKE{i + 2}")
        if name == "woman_cough_no_flags":
            s.timeline = [TimelineEntry.model_validate(to_timeline_entry(OCR_SAMPLE, []))]
        rec = s.finish()
        print("=" * 78, f"\nPATIENT {name}  ({s.questions_after_basics()} questions after safety basics)\n" + "=" * 78)
        print(json.dumps(json.loads(rec.model_dump_json()), indent=1, ensure_ascii=False))
        print("-" * 78)
        print(render_text(build_summary(rec)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
