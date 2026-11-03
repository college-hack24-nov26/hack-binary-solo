"""Quiz answers (keyed by node id) -> PatientContext. Pure. 'Not asked' and 'not sure' are unknown, never 'no'.
Whether a node was asked comes from the quiz graph itself (recompute_path), so no age/sex gates are copied here."""
import json
from pathlib import Path
from typing import Any, Optional

from intake.conditions import SKIPPED, is_unsure
from intake.engine import recompute_path
from intake.models import Graph, load_graph

from . import meds as medsmod, ocr_meds
from .context import DERIVED, PATIENT, UNKNOWN, PatientContext

ALLERGY_CLASSES = ("penicillins", "sulfa", "nsaids")
DAYS_PER_MONTH = 30.4375
PLAUSIBILITY = Path(__file__).resolve().parent / "data" / "plausibility.json"


def _real(answers: dict, node: str):
    """The answer if it is a real value; None for not asked, skipped or 'not sure'."""
    if node not in answers:
        return None
    v = answers[node]
    return None if v == SKIPPED or is_unsure(v) else v


def _tri(ctx: PatientContext, name: str, answers: dict, node: str) -> None:
    v = _real(answers, node)
    if v in ("yes", "no"):
        ctx.set(name, v, PATIENT)
    else:
        ctx.set(name, "unknown", UNKNOWN, "skipped or not sure" if node in answers else "not asked")


def _from_list(ctx: PatientContext, name: str, answers: dict, node: str, option: str) -> None:
    v = _real(answers, node)
    if isinstance(v, list):
        ctx.set(name, "yes" if option in v else "no", PATIENT)
    else:
        ctx.set(name, "unknown", UNKNOWN, "skipped or not sure" if node in answers else "not asked")


def set_age(ctx: PatientContext, months: int, window_months: int, prov: str = PATIENT) -> None:
    ctx.set("age_months", months, prov)
    ctx.set("age_window_months", window_months, prov)
    ctx.set("age_days_lo", months * DAYS_PER_MONTH, prov)
    ctx.set("age_days_hi", (months + window_months + 1) * DAYS_PER_MONTH, prov)   # true age < this (completed months)


GROWTH = Path(__file__).resolve().parent / "data" / "growth_reference.json"


def _cited_range(age_months: int, sex):
    """(lo, hi, table ids) from filled-in cited tables (about -3 SD to +3 SD), or None while the file still says 'needs data'."""
    tabs = json.loads(GROWTH.read_text(encoding="utf-8"))["tables"]
    sexes = [sex] if sex in ("male", "female") else ["male", "female"]
    pri = {"WHO_CGS": 0, "WHO_2007": 1, "IAP_2015": 2, "adult_loose": 3}
    lows, highs, ids = [], [], []
    for sx in sexes:
        best = None
        for t in tabs:
            lo_a, hi_a = t["age_range_months"]
            if t["sex"] in (sx, "any") and lo_a <= age_months <= hi_a and t["rows"]:
                rank = next(v for k, v in pri.items() if t["id"].startswith(k))
                rows = [r for r in t["rows"] if r["age_months"] <= age_months]
                if rows and (best is None or rank < best[0]):
                    r = max(rows, key=lambda r: r["age_months"])
                    best = (rank, r["minus3sd_kg"], r["plus3sd_kg"], t["id"])
        if best is None:
            return None
        lows.append(best[1]); highs.append(best[2]); ids.append(best[3])
    return min(lows), max(highs), ids


def plausibility(age_months: int, weight: float, sex=None):
    """-> None if plausible, else (lo, hi, source). Cited tables first; the labelled draft table only while they are empty."""
    cited = _cited_range(age_months, sex)
    if cited:
        lo, hi, ids = cited
        return None if lo <= weight <= hi else (lo, hi, "cited: " + ", ".join(ids))
    for r in json.loads(PLAUSIBILITY.read_text(encoding="utf-8"))["rows"]:
        if age_months <= r["max_age_months"]:
            return None if r["min_kg"] <= weight <= r["max_kg"] else (r["min_kg"], r["max_kg"], "DRAFT table, not cited")
    return None


def map_quiz(answers: dict, graph: Optional[Graph] = None, red_flags: Optional[list] = None) -> PatientContext:
    graph = graph or load_graph()
    res = recompute_path(graph, answers)
    ans, path = res.answers, set(res.path)
    ans = {**answers, **ans}            # answers off the current path are kept for reading but 'asked' uses `path`
    ctx = PatientContext()

    # -- age
    yrs = _real(answers, "age_years")
    if yrs is None:
        ctx.set("age_months", None, UNKNOWN, "age skipped or not asked")
    elif yrs == 0:
        m = _real(answers, "age_months")
        if m is None:
            ctx.set("age_months", None, UNKNOWN, "under 1 year but months not given")
        else:
            set_age(ctx, int(m), 0)
    else:
        set_age(ctx, int(yrs) * 12, 11)
        ctx.set("age_years_reported", yrs, PATIENT)

    # -- sex
    sex = _real(answers, "sex")
    ctx.set("sex", sex, PATIENT) if sex in ("female", "male", "other") else ctx.set("sex", None, UNKNOWN)
    if sex == "other" or sex is None:
        ctx.set("sex_for_formula", None, UNKNOWN, "doctor to choose for sex-specific formulas")
    else:
        ctx.set("sex_for_formula", sex, DERIVED)

    # -- pregnancy: asked only on the graph's own condition; a derived 'no' only when the quiz went past that point
    p = _real(answers, "pregnancy")
    if p == "yes":
        ctx.set("pregnant", "yes", PATIENT)
    elif p == "no":
        ctx.set("pregnant", "no", PATIENT)
    elif "pregnancy" in answers and is_unsure(answers["pregnancy"]):
        ctx.set("pregnant", "possible", PATIENT, "patient not sure")
    elif "pregnancy" in path:
        ctx.set("pregnant", None, UNKNOWN, "skipped" if "pregnancy" in answers else "not answered yet")
    elif "weight_kg" in path and "sex" in answers and "age_years" in answers:
        ctx.set("pregnant", "no", DERIVED, "not asked: male, or outside the age band the quiz asks pregnancy for")
    else:
        ctx.set("pregnant", None, UNKNOWN, "quiz did not reach the pregnancy decision")
    _tri(ctx, "pregnancy_bleeding", answers, "preg_bleeding")

    # -- weight
    w = _real(answers, "weight_kg")
    ctx.set("weight_kg", float(w) if w is not None else None, PATIENT)
    if w is not None and ctx.get("age_months") is not None:
        bad = plausibility(ctx.get("age_months"), float(w), sex)
        if bad:
            ctx.set("weight_implausible", {"w": float(w), "lo": bad[0], "hi": bad[1], "source": bad[2]}, DERIVED)

    # -- allergies: 'none' is exclusive; an answered list means every class not ticked is a known 'no'
    al = _real(answers, "allergies")
    for c in ALLERGY_CLASSES:
        if isinstance(al, list):
            ctx.set(f"allergy_{c}", "yes" if c in al else "no", PATIENT)
        else:
            ctx.set(f"allergy_{c}", "unknown", UNKNOWN, "skipped or not sure" if "allergies" in answers else "not asked")
    other = _real(answers, "allergy_other")
    ctx.allergy_other_raw = other.strip() if isinstance(other, str) else ""

    # -- current medicines
    mq = _real(answers, "meds_any")
    if mq == "no":
        ctx.set("meds_known", "yes", PATIENT, "none")
    elif mq == "yes":
        txt = _real(answers, "meds_list")
        if isinstance(txt, str) and txt.strip():
            ctx.set("meds_known", "yes", PATIENT)
            ctx.meds, ctx.unparsed_meds = medsmod.parse_names(txt)
            ctx.set("meds_text", txt.strip(), PATIENT)
        else:
            ctx.set("meds_known", "no_list", UNKNOWN, "taking medicines but list skipped")
    else:
        ctx.set("meds_known", None, UNKNOWN, "skipped, not sure or not asked")

    # -- conditions
    _tri(ctx, "kidney_disease", answers, "kidney")
    _tri(ctx, "liver_disease", answers, "liver")
    _tri(ctx, "diabetes", answers, "diabetes")
    _tri(ctx, "hypertension", answers, "hypertension")
    _tri(ctx, "asthma", answers, "asthma")
    for name, option in (("ulcer", "ulcer"), ("stones", "stones"), ("abdominal_surgery", "surgery"), ("alcohol", "alcohol")):
        _from_list(ctx, name, answers, "hx_abdomen", option)
    ds = _real(answers, "danger_signs")
    if isinstance(ds, list):
        ctx.set("gi_bleed", "yes" if ({"vomit_blood", "black_stool"} & set(ds)) else "no", PATIENT)
    else:
        ctx.set("gi_bleed", "unknown", UNKNOWN, "danger signs skipped or not asked")
    for name, option in (("heart_disease", "heart"), ("cholesterol", "cholesterol"), ("family_heart", "family")):
        _from_list(ctx, name, answers, "hx_chest", option)
    hc, hh = _real(answers, "hx_chest"), _real(answers, "hx_cough")
    if isinstance(hc, list) or isinstance(hh, list):
        ctx.set("smoking", "yes" if ("smoking" in (hc or []) or "smoking" in (hh or [])) else "no", PATIENT)
    else:
        ctx.set("smoking", "unknown", UNKNOWN, "not asked on this path")

    # -- context only
    cc = _real(answers, "chief_complaint")
    ctx.set("complaint", cc, PATIENT)
    ctx.red_flags = [dict(x) for x in (red_flags or [])]
    return ctx


def map_record(rec, graph: Optional[Graph] = None) -> PatientContext:
    """From a saved PatientRecord: raw answers plus the red flags the red-flag service already computed (read-only)."""
    flags = [{"ruleId": r.ruleId, "severity": r.severity, "label": r.label} for r in rec.redFlags]
    ctx = map_quiz(rec.answers, graph, flags)
    ocr_meds.apply_to_context(ctx, rec.timeline)         # doctor-confirmed scans only
    return ctx
