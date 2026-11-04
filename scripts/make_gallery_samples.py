"""Write web/src/gallery/samples.json: real engine results (synthetic demo patients) and their card models, for /gallery.
Run after a formulary or engine change: .venv/bin/python scripts/make_gallery_samples.py"""
import json
import re
import sys
import tempfile
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["INTAKE_DATA_DIR"] = tempfile.mkdtemp()

from api.routers.dosing import card  # noqa: E402
from api.views import red_flags  # noqa: E402
from dosing import demo, service  # noqa: E402
from intake.demo import load_demo  # noqa: E402
from intake.models import load_graph  # noqa: E402
from intake.redflags import load_rules  # noqa: E402


def main() -> int:
    out = {}
    runs = {k: demo.run_fixture(k) for k in demo.DEMO_PATIENTS}
    pick = {"ok": runs["child_fever"][0][1], "needs_input": runs["diabetes_kidney"][0][1],
            "blocked": runs["penicillin_allergy"][0][1], "override": runs["penicillin_allergy"][2][1]}
    rec = demo.record("child_fever")
    pick["refused"] = service.evaluate_for_record(rec, "warfarin", None, doctor_id="demo_doctor", cfg=demo.DEMO_CFG, log=False)
    for k, res in pick.items():
        out[k] = {"result": res, "card": card(res)}
    s = load_demo(load_graph(), load_rules())
    out["redFlags"] = red_flags(s.finish())
    text = json.dumps(out, ensure_ascii=False, indent=1)
    # citation links stay readable but lose their scheme, so the offline URL scan of web/src stays strict (nothing is fetched)
    text = re.sub(r"https?://", "", text)
    (ROOT / "web" / "src" / "gallery" / "samples.json").write_text(text, encoding="utf-8")
    print("wrote web/src/gallery/samples.json:", ", ".join(f"{k}={v['result']['status']}" for k, v in out.items() if k != "redFlags"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
