"""Three synthetic demo patients (quiz answers in, dosing result out) and a readable text renderer for the demo script.
Synthetic data only. Uses DEMO_MODE, so every result carries the red 'DEMO - UNVERIFIED DATA' banner."""
import json
from datetime import datetime
from pathlib import Path

from records.schema import PatientRecord

from . import derived, formulary, history, mapper, service
from .config import Config
from .engine import apply_inputs

DEMO_CFG = Config(demo_mode=True)

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "demo"


def load_fixtures(directory: Path = FIXTURE_DIR) -> dict:
    """Synthetic patients as JSON (quiz answers keyed by graph node id, plus the check to run and the expected status of each run)."""
    out = {}
    for f in sorted(directory.glob("demo_patient_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        out[d["key"]] = d
    return out


DEMO_PATIENTS = load_fixtures()
DEMO_TOKENS = {p["token"] for p in DEMO_PATIENTS.values()}


def record(key: str) -> PatientRecord:
    """The fixture's answers replayed through the real IntakeSession (consent, path, red flags, record builder), so a loaded
    demo patient is exactly what the quiz would have produced. Nodes the fixture does not mention get the benign synthetic bank value."""
    from intake.models import load_graph
    from intake.redflags import load_rules
    from intake.synthetic import run_bank
    fx = DEMO_PATIENTS[key]
    return run_bank(load_graph(), load_rules(), dict(fx["answers"]), token=fx["token"], allow_unused=True).finish()


def none_apply(rec: PatientRecord, drug_id: str, doctor_id: str, now=None) -> PatientRecord:
    """The History check's 'None of these apply' button: every unknown listed item becomes no, saved doctor-confirmed."""
    f = formulary.load(DEMO_CFG.formulary_path)
    ctx = apply_inputs(mapper.map_record(rec), {}, [], rec.visitHistory)
    todo = history.unknown_items(history.items_for(f, f.drugs[drug_id], ctx))
    return service.save_history(rec, {i.field: "no" for i in todo}, doctor_id=doctor_id, now=now) if todo else rec


def scr_for_egfr(target: float, age_years: int = 58, female: bool = False) -> float:
    """Serum creatinine giving about `target` eGFR (CKD-EPI 2021 from the formulary formula), by bisection."""
    f = formulary.load(DEMO_CFG.formulary_path)
    lo, hi = 0.2, 15.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if derived.ckd_epi(f, age_years, mid, female) > target else (lo, mid)
    return round((lo + hi) / 2, 2)


def render_text(res: dict, width: int = 100) -> str:
    L = []
    if res.get("demo"):
        L.append("*** " + res["demo_banner"] + " ***")
    L.append(f"{res['banner']}  |  data status: {res['data_status']}")
    L.append(f"STATUS: {res['status'].upper()}   drug: {res['drug']}   indication: {res['indication']}   rule: {res['selected_rule_id']}")
    if res["dose_mg"] is not None:
        qty = f"{res['volume_ml']:g} mL" if res["volume_ml"] else f"{res['units']:g} unit(s)"
        L.append(f"DOSE: {res['dose_mg']:g} mg = {qty} of {res['product']}   interval/frequency: {res['interval_h'] or res['doses_per_day']}")
        L.append(f"DAILY TOTAL: {res['daily_total_mg']} mg   DAILY MAX: {res['daily_max_mg']} mg   binding cap: {res['binding_cap'] or 'none'}   final: {res['final']}")
    if res.get("plan"):
        L.append(f"PLAN: {res['plan']}")
    for b in res["blocks"]:
        L.append("BLOCK: " + b["text"])
    for n in res["needs_input"]:
        L.append(f"NEEDS INPUT [{n['field']}]: {n['why']}")
    for r in res["refused_reasons"]:
        L.append("REFUSED: " + r)
    for o in res["overrides"]:
        L.append(f"OVERRIDE by {o['doctor_id']} [{o['category_label']}]: {o['reason']}")
    for w in res["warnings"][:6]:
        L.append("warning: " + w["text"][:width * 2])
    if res["calculation_steps"]:
        L.append("steps:")
        L += ["  - " + s for s in res["calculation_steps"]]
    if res["sources"]:
        L.append("sources: " + "; ".join(sorted({(s['id'] or s['name'][:30]) for s in res['sources']})))
    return "\n".join(L)


def run_fixture(key: str, doctor_id: str = "demo_doctor", now: datetime | None = None, cfg: Config | None = None) -> list[tuple[dict, dict]]:
    """Run one fixture through the real dosing service (writes audit entries). -> [(run spec, result)]"""
    fx, cfg = DEMO_PATIENTS[key], cfg or DEMO_CFG
    chk = fx["check"]
    rec = record(key)
    if chk.get("history") == "none_apply":
        rec = none_apply(rec, chk["drug"], doctor_id, now)
    out = []
    for run in fx["runs"]:
        res = service.evaluate_for_record(rec, chk["drug"], chk["indication"], doctor_id=doctor_id, cfg=cfg, now=now,
                                          selected_rule_id=chk.get("selected_rule_id"), doctor_inputs=run.get("doctor_inputs"),
                                          confirmed=run.get("confirmed"), override_reason=run.get("override_reason"),
                                          override_category=run.get("override_category"))
        out.append((run, res))
    return out


def run_all(doctor_id: str = "demo_doctor", now: datetime | None = None) -> list[tuple[str, list[tuple[str, dict]]]]:
    """Run the fixtures end to end. Writes audit entries under INTAKE_DATA_DIR. -> [(title, [(step, result)])]"""
    return [(fx["title"], [(run["label"], res) for run, res in run_fixture(k, doctor_id, now)]) for k, fx in DEMO_PATIENTS.items()]
