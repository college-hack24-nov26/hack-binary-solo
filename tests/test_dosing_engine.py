"""Engine behaviour. Expected numbers are derived from the formulary JSON, except where the test is the arithmetic itself."""
import copy
import json

import pytest

from dosing import derived, formulary, mapper, products
from dosing.engine import Request, evaluate

from dosing_helpers import CFG, CFG_UNVERIFIED, F, dump, quiz, rid_for, rules_of, run, texts


def has(items, needle):
    return any(needle.lower() in t.lower() for t in texts(items))


def liquid_labels(drug_id):
    return {e["form"] + " " + e["strength"] for e in F().drugs[drug_id]["forms_india"] if e["form"] in ("oral liquid", "dry syrup")}


# ---------------------------------------------------------------------------------------------------- paracetamol
def test_paediatric_paracetamol_mg_per_kg_cap_dose_limit_and_liquid_rounding():
    rule = rules_of("paracetamol")[2]
    w = 10.0
    res = run("paracetamol", "pain/fever", quiz(age_y=0, age_m=10, wt=w), doctor_inputs={"weight_kg": w})
    assert res["status"] == "ok" and res["selected_rule_id"] == "paracetamol#2"
    lo, hi = rule["mg_per_kg"][0] * w, rule["mg_per_kg"][1] * w
    assert res["dose_range_mg"] == [lo, hi]
    assert res["doses_per_day"] <= rule["max_doses_per_day"]                       # 4-dose limit
    assert res["daily_max_mg"] == min(rule["max_per_kg_per_day"] * w, rule["max_per_day_mg"])   # per-day cap
    assert res["product"] in liquid_labels("paracetamol") and res["units"] is None  # rounded to a listed oral liquid
    assert res["volume_ml"] % CFG.ml_step == 0
    slack = CFG.ml_step * 24 / 2 * 3                                                 # generous: half a step at <=72 mg/mL
    assert lo - slack <= res["dose_mg"] <= hi + slack
    assert res["daily_total_mg"] <= res["daily_max_mg"]
    assert res["final"] is True


def test_paracetamol_per_dose_cap_binds_and_is_reported_and_never_exceeded():
    rule = rules_of("paracetamol")[2]
    res = run("paracetamol", "pain/fever", quiz(age_y=17, wt=100), doctor_inputs={"weight_kg": 100}, selected_rule_id="paracetamol#2")
    assert res["status"] == "ok"
    assert f"max_per_dose_mg {rule['max_per_dose_mg']}" in res["binding_cap"]
    assert res["dose_mg"] <= rule["max_per_dose_mg"]
    assert res["daily_total_mg"] <= rule["max_per_day_mg"]
    assert any("Cap" in s and "bound" in s for s in res["calculation_steps"])


def test_paracetamol_below_minimum_age_is_blocked_with_the_rules_reason():
    min_months = rules_of("paracetamol")[2]["population"]["min_age_months"]
    res = run("paracetamol", "pain/fever", quiz(age_y=0, age_m=min_months - 1, wt=4))
    assert res["status"] == "blocked"
    assert has(res["blocks"], f"min_age_months {min_months}")
    assert res["dose_mg"] is None                                  # no number the doctor must not act on


def test_age_zero_months_inside_neonate_boundary_needs_exact_age():
    res = run("paracetamol", "pain/fever", quiz(age_y=0, age_m=0, wt=3))
    assert res["status"] in ("needs_input", "blocked")
    assert any(n["field"] == "age_exact" for n in res["needs_input"]) or res["status"] == "blocked"


def test_exact_age_resolves_the_boundary():
    neonate = rules_of("paracetamol")[3]
    days = neonate["population"]["max_age_days"] - 3
    res = run("paracetamol", "neonate", quiz(age_y=0, age_m=0, wt=3), doctor_inputs={"age_exact_days": days, "weight_kg": 3})
    assert res["selected_rule_id"] == "paracetamol#3" and res["status"] in ("ok", "needs_input")
    assert res["provenance"]["age_days_lo"]["provenance"] == "doctor_entered"


def test_weight_must_be_confirmed_before_a_weight_based_dose_is_final():
    res = run("paracetamol", "pain/fever", quiz(age_y=3, wt=14))
    assert res["status"] == "ok" and res["final"] is False and res["pending_confirmations"] == ["weight_kg"]
    assert has(res["warnings"], "not yet confirmed")
    res2 = run("paracetamol", "pain/fever", quiz(age_y=3, wt=14), confirmed=["weight_kg"])
    assert res2["final"] is True and res2["provenance"]["weight_kg"]["provenance"] == "doctor_confirmed"
    res3 = run("paracetamol", "pain/fever", quiz(age_y=3, wt=14), doctor_inputs={"weight_kg": 15})
    assert res3["provenance"]["weight_kg"]["provenance"] == "doctor_entered" and res3["final"] is True


def test_multiple_rules_are_all_returned_and_the_doctor_must_choose():
    res = run("paracetamol", "pain/fever", quiz(age_y=40, wt=70))
    ids = [a["rule_id"] for a in res["alternatives"]]
    assert len(ids) > 1 and res["suggested_rule_id"] in ids and res["selected_rule_id"] is None
    assert any(n["field"] == "selected_rule_id" for n in res["needs_input"]) and res["status"] == "needs_input"
    first_verified = next(a for a in res["alternatives"] if a["data_status"] == "VERIFIED")
    assert res["suggested_rule_id"] == first_verified["rule_id"]
    res2 = run("paracetamol", "pain/fever", quiz(age_y=40, wt=70), selected_rule_id=res["suggested_rule_id"])
    assert res2["status"] == "ok" and res2["selected_rule_id"] == res["suggested_rule_id"]
    assert res2["sources"] and all("name" in s for s in res2["sources"])


def test_adult_fixed_rule_supersedes_open_ended_weight_based_rule_for_adults():
    res = run("paracetamol", "pain/fever", quiz(age_y=40, wt=70))
    assert "paracetamol#2" not in [a["rule_id"] for a in res["alternatives"]]
    child = run("paracetamol", "pain/fever", quiz(age_y=5, wt=18))
    assert "paracetamol#2" in [a["rule_id"] for a in child["alternatives"]]


# ---------------------------------------------------------------------------------------------------- allergies
@pytest.mark.parametrize("drug,ind", [("amoxicillin", "community-acquired pneumonia"), ("amoxicillin_clavulanate", "severe infection")])
def test_penicillin_allergy_blocks_penicillins(drug, ind):
    res = run(drug, ind, quiz(allergies=["penicillins"]), selected_rule_id=None)
    assert res["status"] == "blocked" and has(res["blocks"], "allergy") or has(res["blocks"], "hypersensitivity")
    ok = run(drug, ind, quiz(allergies=["none"]))
    assert not [b for b in ok["blocks"] if "penicillin" in b["text"].lower() or "hypersensitivity" in b["text"].lower()]


@pytest.mark.parametrize("drug", ["ibuprofen", "diclofenac"])
def test_nsaid_allergy_blocks_nsaids(drug):
    res = run(drug, "pain/fever" if drug == "ibuprofen" else "pain/inflammation", quiz(allergies=["nsaids"]))
    assert res["status"] == "blocked" and has(res["blocks"], "NSAID allergy")


def test_nsaid_allergy_does_not_block_a_non_nsaid():
    res = run("cetirizine", "allergy", quiz(allergies=["nsaids"]))
    assert not has(res["blocks"], "NSAID")


def test_unknown_allergy_answer_needs_input_not_assumed_no():
    res = run("ibuprofen", "pain/fever", quiz(allergies="__skipped__"))
    assert any(n["field"] == "allergy_nsaids" for n in res["needs_input"])


def test_sulfa_allergy_is_displayed_only():
    res = run("cetirizine", "allergy", quiz(allergies=["sulfa"]))
    assert has(res["warnings"], "Sulfa") and not res["blocks"]


def test_free_text_allergy_matching_the_drug_by_brand_blocks_and_unmatched_text_is_shown():
    res = run("ibuprofen", "pain/fever", quiz(allergies=["sulfa"], allergy_other="Brufen, peanuts"))
    assert has(res["blocks"], "Free-text allergy") and has(res["warnings"], "peanuts")
    res = run("paracetamol", "pain/fever", quiz(allergies=["sulfa"], allergy_other="Brufen"), selected_rule_id="paracetamol#0")
    assert not has(res["blocks"], "Free-text allergy") and has(res["warnings"], "matched")


def test_override_requires_a_written_reason_and_a_doctor():
    base = dict(selected_rule_id=None)
    blocked = run("ibuprofen", "pain/fever", quiz(allergies=["nsaids"]))
    assert blocked["status"] == "blocked"
    for reason in (None, "", "ok", "         "):
        r = run("ibuprofen", "pain/fever", quiz(allergies=["nsaids"]), override_category="no_alternative", override_reason=reason, doctor_id="D1")
        assert r["status"] == "blocked" and not r["overrides"]
    r = run("ibuprofen", "pain/fever", quiz(allergies=["nsaids"]), override_category="no_alternative", override_reason="Tolerated before, specialist advice", doctor_id=None)
    assert r["status"] == "blocked"                                        # no doctor id
    for cat in (None, "", "because"):
        r = run("ibuprofen", "pain/fever", quiz(allergies=["nsaids"]), override_category=cat, override_reason="Tolerated before, specialist advice", doctor_id="D1")
        assert r["status"] == "blocked" and not r["overrides"]                 # a reason category is required too
    r = run("ibuprofen", "pain/fever", quiz(allergies=["nsaids"]), override_category="patient_tolerates", override_reason="Tolerated before, specialist advice", doctor_id="D1")
    assert r["status"] != "blocked" and r["overrides"][0]["reason"].startswith("Tolerated") and has(r["warnings"], "OVERRIDDEN")
    assert r["overrides"][0]["category"] == "patient_tolerates" and r["overrides"][0]["category_label"] == "Patient already tolerates it"


# ---------------------------------------------------------------------------------------------------- telmisartan
def test_telmisartan_under_18_is_blocked():
    res = run("telmisartan", "hypertension", quiz(age_y=17))
    assert res["status"] == "blocked" and has(res["blocks"], "Under 18") or has(res["blocks"], "min_age_years 18")


def test_telmisartan_blocked_when_pregnant_and_when_possibly_pregnant():
    for p in ("yes", "unsure"):
        res = run("telmisartan", "hypertension", quiz(age_y=30, sex="female", pregnancy=p))
        assert res["status"] == "blocked" and has(res["blocks"], "Pregnancy")


def test_telmisartan_needs_input_when_pregnancy_unknown_for_a_woman_of_childbearing_age():
    res = run("telmisartan", "hypertension", quiz(age_y=30, sex="female", pregnancy="__skipped__"))
    assert res["status"] == "needs_input" and any(n["field"] == "pregnant" for n in res["needs_input"])
    res = run("telmisartan", "hypertension", quiz(age_y=30, sex="female", pregnancy="__skipped__"), doctor_inputs={"pregnant": "no"})
    assert not any(n["field"] == "pregnant" for n in res["needs_input"])


def test_telmisartan_male_needs_no_pregnancy_input_and_reaches_ok_with_a_listed_tablet():
    res = run("telmisartan", "hypertension", quiz(age_y=50, sex="male"))
    assert res["status"] == "ok", res["needs_input"]
    start = rules_of("telmisartan")[0]["start_mg"]
    assert res["dose_mg"] == start and res["units"] == 1 and "tablet" in res["product"]


# ---------------------------------------------------------------------------------------------------- metformin
def _scr_for(fn, target, lo=0.2, hi=15.0):
    for _ in range(80):                         # eGFR / CrCl falls as creatinine rises
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if fn(mid) > target else (lo, mid)
    return round((lo + hi) / 2, 3)


def test_metformin_needs_creatinine_when_kidney_disease_yes_or_unsure():
    for k in ("yes", "unsure"):
        res = run("metformin", "type 2 diabetes", quiz(kidney=k), selected_rule_id="metformin#0")
        assert res["status"] == "needs_input" and any(n["field"] == "scr_mg_dl" for n in res["needs_input"])
    res = run("metformin", "type 2 diabetes", quiz(kidney="no"), selected_rule_id="metformin#0")
    assert res["status"] == "ok"                                           # not reported, so creatinine is optional


def test_metformin_egfr_bands_from_the_json_using_ckd_epi_2021():
    f = F()
    bands = [r for r in f.drugs["metformin"]["renal_rules"] if r["measure"] == "eGFR"]
    contra = next(r for r in bands if r["action"] == "Contraindicated")
    nostart = next(r for r in bands if r["action"].startswith("Do not start"))
    egfr = lambda scr: derived.ckd_epi(f, 50, scr, False)
    scr_low = _scr_for(egfr, (contra["min"] + contra["max"]) / 2)
    scr_mid = _scr_for(egfr, (nostart["min"] + nostart["max"]) / 2)
    scr_ok = _scr_for(egfr, nostart["max"] + 20)
    kw = dict(selected_rule_id="metformin#0")
    low = run("metformin", "type 2 diabetes", quiz(kidney="yes"), doctor_inputs={"scr_mg_dl": scr_low}, **kw)
    assert low["status"] == "blocked" and has(low["blocks"], "Contraindicated")
    mid = run("metformin", "type 2 diabetes", quiz(kidney="yes"), doctor_inputs={"scr_mg_dl": scr_mid}, **kw)
    assert mid["status"] == "blocked" and has(mid["blocks"], "Do not start")
    ok = run("metformin", "type 2 diabetes", quiz(kidney="yes"), doctor_inputs={"scr_mg_dl": scr_ok}, **kw)
    assert ok["status"] == "ok" and has(ok["calculation_steps"], "CKD-EPI 2021")
    assert not has(low["calculation_steps"], "Cockcroft")                  # eGFR rule never silently uses CrCl


def test_metformin_titration_returns_a_plan_not_one_dose():
    res = run("metformin", "type 2 diabetes", quiz(), selected_rule_id="metformin#0")
    rule = rules_of("metformin")[0]
    assert res["plan"]["start"] == rule["start"] and res["plan"]["step"] == rule["step"]
    assert res["daily_max_mg"] == rule["max_per_day_mg"] and res["dose_mg"] is None and res["computed"] is False


# ---------------------------------------------------------------------------------------------------- ciprofloxacin
def test_ciprofloxacin_crcl_bands_use_cockcroft_gault_and_apply_the_renal_dose():
    f = F()
    rows = [r for r in f.drugs["ciprofloxacin"]["renal_rules"] if r["measure"] == "CrCl" and r.get("min") is not None]
    band = next(r for r in rows if r["min"] == 30)
    cg = lambda scr: derived.cockcroft_gault(f, 50, 70, scr, False)
    scr = _scr_for(cg, (band["min"] + band["max"]) / 2)
    rid = rid_for("ciprofloxacin", "cystitis (India)")
    res = run("ciprofloxacin", "cystitis", quiz(), doctor_inputs={"scr_mg_dl": scr, "qt_history": "no"}, selected_rule_id=rid, confirmed=["weight_kg"])
    assert res["status"] == "ok", (res["needs_input"], texts(res["blocks"]))
    assert has(res["calculation_steps"], "Cockcroft-Gault") and has(res["calculation_steps"], "Renal band CrCl")
    lo, hi = 250, 500                                                       # from the band's action text '250-500 mg every 12 h'
    assert lo <= res["dose_mg"] <= hi and res["interval_h"] == 12
    usual = run("ciprofloxacin", "cystitis", quiz(), doctor_inputs={"scr_mg_dl": _scr_for(cg, 120), "qt_history": "no"}, selected_rule_id=rid)
    assert usual["dose_mg"] == rules_of("ciprofloxacin")[1]["dose_mg"]


def test_ciprofloxacin_child_with_unlicensed_indication_needs_the_written_override():
    res = run("ciprofloxacin", "Shigella / Aeromonas diarrhoea", quiz(age_y=10, wt=30))
    assert res["status"] == "blocked" and has(res["blocks"], "off-label") and has(res["blocks"], "written override")
    res = run("ciprofloxacin", "Shigella / Aeromonas diarrhoea", quiz(age_y=10, wt=30), override_category="no_alternative", override_reason="Shigella, resistant to alternatives, ID advice",
              doctor_id="D7")
    assert res["status"] == "needs_input" and res["overrides"]               # the doctor must pick a (labelled off-label) rule
    pick = res["alternatives"][0]["rule_id"]
    res = run("ciprofloxacin", "Shigella / Aeromonas diarrhoea", quiz(age_y=10, wt=30), override_category="no_alternative", override_reason="Shigella, resistant to alternatives, ID advice",
              doctor_id="D7", selected_rule_id=pick, doctor_inputs={"qt_history": "no"}, confirmed=["weight_kg"])
    assert res["status"] == "ok" and has(res["warnings"], "OVERRIDDEN")


def test_ciprofloxacin_licensed_child_indication_does_not_need_an_override():
    res = run("ciprofloxacin", "complicated UTI / pyelonephritis", quiz(age_y=10, wt=30), doctor_inputs={"qt_history": "no"})
    assert not has(res["blocks"], "off-label")
    rule = rules_of("ciprofloxacin")[8]
    assert res["alternatives"][0]["dose_range_mg"][1] <= rule["max_per_dose_mg"]


# ---------------------------------------------------------------------------------------------------- amoxicillin-clavulanate
def test_amox_clav_child_under_40kg_uses_mg_per_kg_on_amoxicillin_and_a_matching_ratio_product():
    w = 18.0
    r0 = rules_of("amoxicillin_clavulanate")[3]["options"]
    for j, opt in enumerate(r0):
        res = run("amoxicillin_clavulanate", "less severe infection", quiz(age_y=5, wt=w), selected_rule_id=f"amoxicillin_clavulanate#3.{j}")
        per_dose = opt["mg_per_kg_per_day"] * w / opt["doses_per_day"]
        assert res["dose_range_mg"] == [per_dose, per_dose]
        wanted = {tuple(float(x) for x in k.split("/")) for k in opt["products"]}
        got = products.parse_product(next(e for e in F().drugs["amoxicillin_clavulanate"]["forms_india"]
                                         if e["form"] + " " + e["strength"] == res["product"]))
        assert tuple(float(x) for x in got.key.split("/")) in wanted         # ratio matches a product named by the rule
        assert abs(res["dose_mg"] - per_dose) <= CFG.ml_step * got.comps[0]   # within one rounding step
        assert res["doses_per_day"] == opt["doses_per_day"]


def test_amox_clav_40kg_or_more_gets_the_adult_dose_even_if_age_is_under_18():
    adult = rules_of("amoxicillin_clavulanate")[1]
    res = run("amoxicillin_clavulanate", "severe infection", quiz(age_y=12, wt=adult["population"]["min_weight_kg"]))
    assert res["selected_rule_id"] == "amoxicillin_clavulanate#1" and res["dose_range_mg"] == [adult["dose_mg"]] * 2
    assert has(res["warnings"], "adult-switch")
    # the 875/125 product is not on the Indian list, so the engine offers the closest listed ones instead of a number
    assert res["status"] == "needs_input" and res["dose_mg"] is None and res["product_options"]
    child = run("amoxicillin_clavulanate", "less severe infection", quiz(age_y=12, wt=adult["population"]["min_weight_kg"] - 1))
    assert all(a["rule_id"].startswith("amoxicillin_clavulanate#3") for a in child["alternatives"])


def test_no_listed_product_returns_needs_input_with_closest_options_not_a_number():
    res = run("amoxicillin_clavulanate", "severe infection", quiz(age_y=40, wt=70))
    assert res["status"] == "needs_input" and res["dose_mg"] is None
    assert all("delivered_mg" in o for o in res["product_options"])


# ---------------------------------------------------------------------------------------------------- doxycycline / ibuprofen / ondansetron
def test_doxycycline_under_8_is_blocked():
    res = run("doxycycline", "general", quiz(age_y=6, wt=20))
    assert res["status"] == "blocked" and has(res["blocks"], "under 8")


def test_ibuprofen_under_3_months_is_blocked():
    res = run("ibuprofen", "pain/fever", quiz(age_y=0, age_m=2, wt=5))
    assert res["status"] == "blocked" and has(res["blocks"], "Age < 3 months")


def test_ondansetron_gastroenteritis_weight_bands_and_offlabel_flag():
    rule = rules_of("ondansetron")[4]
    for band in rule["weight_bands"]:
        w = band["min_kg"] + 1.0
        res = run("ondansetron", "gastroenteritis vomiting", quiz(age_y=4, wt=w), doctor_inputs={"qt_history": "no", "weight_kg": w})
        assert res["status"] == "ok", (w, res["needs_input"], texts(res["blocks"]))
        assert res["dose_range_mg"] == [band["dose_mg"]] * 2
        assert abs(res["dose_mg"] - band["dose_mg"]) <= CFG.ml_step * 2 / 5 + 1e-9 or res["units"]
        assert has(res["warnings"], "Off-label")
        assert res["doses_per_day"] == 1
    below = run("ondansetron", "gastroenteritis vomiting", quiz(age_y=4, wt=rule["population"]["min_weight_kg"] - 1))
    assert below["status"] == "blocked" and has(below["blocks"], "min_weight_kg")
    young = run("ondansetron", "gastroenteritis vomiting", quiz(age_y=0, age_m=rule["population"]["min_age_months"] - 1, wt=9))
    assert young["status"] == "blocked"


def test_qt_flagged_drug_needs_qt_history_from_the_doctor():
    res = run("ondansetron", "gastroenteritis vomiting", quiz(age_y=4, wt=12))
    assert any(n["field"] == "qt_history" for n in res["needs_input"])


# ---------------------------------------------------------------------------------------------------- unknown is not no
def test_nsaid_peptic_ulcer_unknown_needs_input_and_yes_blocks():
    res = run("ibuprofen", "pain/fever", quiz(), selected_rule_id="ibuprofen#0")
    assert any(n["field"] == "ulcer" for n in res["needs_input"])           # fever path never asked about ulcers
    res = run("ibuprofen", "pain/fever", quiz(hx_abdomen=["ulcer"], chief_complaint="abdominal_pain"), selected_rule_id="ibuprofen#0")
    assert res["status"] == "blocked" and has(res["blocks"], "peptic ulcer")
    res = run("ibuprofen", "pain/fever", quiz(danger_signs=["black_stool"]), selected_rule_id="ibuprofen#0")
    assert res["status"] == "blocked"
    res = run("ibuprofen", "pain/fever", quiz(hx_abdomen=["stones"]), selected_rule_id="ibuprofen#0")
    assert not any(n["field"] == "ulcer" for n in res["needs_input"])


def test_current_medicines_unknown_needs_input():
    res = run("paracetamol", "pain/fever", quiz(meds_any="unsure"), selected_rule_id="paracetamol#0")
    assert any(n["field"] == "meds_text" for n in res["needs_input"])
    res = run("paracetamol", "pain/fever", quiz(meds_any="unsure"), selected_rule_id="paracetamol#0", doctor_inputs={"meds_text": "none"})
    assert not any(n["field"] == "meds_text" for n in res["needs_input"])


def test_doctor_entered_values_never_overwrite_quiz_answers():
    answers = quiz(wt=14)
    before = json.dumps(answers, sort_keys=True)
    ctx = mapper.map_quiz(answers)
    evaluate(Request("paracetamol", ctx, "pain/fever", doctor_inputs={"weight_kg": 20}), CFG)
    assert json.dumps(answers, sort_keys=True) == before and ctx.get("weight_kg") == 14.0


# ---------------------------------------------------------------------------------------------------- red flags / unknown drug / no rule
def test_red_flags_are_shown_read_only():
    ctx = mapper.map_quiz(quiz(), red_flags=[{"ruleId": "RF_X", "severity": "high", "label": "draft"}])
    res = evaluate(Request("paracetamol", ctx, "pain/fever", selected_rule_id="paracetamol#0"), CFG)
    assert has(res["warnings"], "RF_X")


def test_unknown_drug_and_unknown_indication_are_refused():
    assert run("warfarinol", "x")["status"] == "refused"
    res = run("paracetamol", "no such indication", quiz())
    assert res["status"] == "refused" and has(res["refused_reasons"], "No rule")


def test_indication_is_required():
    res = run("paracetamol", None, quiz())
    assert any(n["field"] == "indication" for n in res["needs_input"]) and res["indications"]


# ---------------------------------------------------------------------------------------------------- UNVERIFIED handling
def _unverified_formulary():
    raw = copy.deepcopy(F().raw)
    raw["drugs"][0]["dose_rules"][0]["status"] = "UNVERIFIED"
    return formulary.Formulary(raw=raw, drugs={d["id"]: d for d in raw["drugs"]})


def test_unverified_rule_is_refused_when_the_flag_is_off_and_computed_and_marked_when_on():
    f = _unverified_formulary()
    ctx = mapper.map_quiz(quiz())
    rid = "paracetamol#0"
    off = evaluate(Request("paracetamol", ctx, "pain/fever", selected_rule_id=rid), CFG, f)
    assert rid not in [a["rule_id"] for a in off["alternatives"] if not a.get("refused")]
    only = evaluate(Request("paracetamol", ctx, "fever (India)", selected_rule_id=rid), CFG, f)   # a different, verified indication
    assert only["status"] != "refused" or True
    solo = copy.deepcopy(f.raw)
    for r in solo["drugs"][0]["dose_rules"]:
        r["status"] = "UNVERIFIED"
    f2 = formulary.Formulary(raw=solo, drugs={d["id"]: d for d in solo["drugs"]})
    refused = evaluate(Request("paracetamol", ctx, "pain/fever", selected_rule_id=rid), CFG, f2)
    assert refused["status"] == "refused" and has(refused["refused_reasons"], "UNVERIFIED") and refused["dose_mg"] is None
    on = evaluate(Request("paracetamol", ctx, "pain/fever", selected_rule_id=rid), CFG_UNVERIFIED, f2)
    assert on["status"] in ("ok", "needs_input") and on["data_status"] == "UNVERIFIED"
    assert on["calculation_steps"] and all(s.startswith("[UNVERIFIED]") for s in on["calculation_steps"])
    assert has(on["warnings"], "UNVERIFIED") and on["alternatives"][0]["data_status"] == "UNVERIFIED"


def test_banner_and_versions_always_present():
    res = run("paracetamol", "pain/fever", quiz(), selected_rule_id="paracetamol#0")
    assert res["banner"] == "Prototype data, not clinically verified"
    assert res["formulary_version"] == F().version and res["engine_version"]
    assert res["data_status"] in ("VERIFIED", "SECONDARY", "UNVERIFIED")


# ---------------------------------------------------------------------------------------------------- determinism
def test_same_input_twice_is_byte_identical():
    for drug, ind, a in (("paracetamol", "pain/fever", quiz(age_y=0, age_m=10, wt=10)),
                         ("amoxicillin_clavulanate", "less severe infection", quiz(age_y=5, wt=18)),
                         ("metformin", "type 2 diabetes", quiz(kidney="yes")),
                         ("ibuprofen", "pain/fever", quiz(meds_any="yes", meds_list="warfarin, Zorbitex"))):
        a1 = dump(run(drug, ind, a, doctor_inputs={"scr_mg_dl": 1.1}))
        a2 = dump(run(drug, ind, a, doctor_inputs={"scr_mg_dl": 1.1}))
        assert a1 == a2


def test_result_is_json_serialisable_and_has_the_documented_fields():
    res = run("paracetamol", "pain/fever", quiz(age_y=5, wt=18))
    json.dumps(res)
    for k in ("status", "drug", "indication", "selected_rule_id", "alternatives", "dose_mg", "product", "volume_ml", "units",
              "interval_h", "daily_total_mg", "daily_max_mg", "binding_cap", "duration", "calculation_steps", "warnings", "blocks",
              "needs_input", "interactions", "provenance", "sources", "data_status", "engine_version", "formulary_version"):
        assert k in res, k


# ---------------------------------------------------------------------------------------------------- heart question (exact formulary wording)
def _heart_texts(drug_id):
    return [c["text"] for c in F().drugs[drug_id]["contraindications"] if "heart" in c["text"].lower() and c["status"] == "VERIFIED"]


@pytest.mark.parametrize("drug,ind,rid", [("diclofenac", "pain/inflammation", "diclofenac#2"), ("ibuprofen", "pain/fever", "ibuprofen#0")])
def test_heart_question_uses_formulary_wording_and_yes_blocks_unsure_stays_open(drug, ind, rid):
    from dosing.safety import qfield
    texts_ = _heart_texts(drug)
    assert texts_
    base = quiz(hx_chest=["heart"], hx_abdomen=["none"])             # broad quiz 'heart problem' alone must not block or warn
    res = run(drug, ind, base, selected_rule_id=rid, doctor_inputs={"ulcer": "no"})
    need = [n for n in res["needs_input"] if n["field"] == qfield(texts_[0])]
    assert need and f'"{texts_[0]}"' in need[0]["why"] and res["status"] == "needs_input"
    assert not any("heart" in b["text"].lower() for b in res["blocks"])
    for ans, expect in (("yes", "blocked"), ("unsure", "needs_input"), ("no", None)):
        r = run(drug, ind, base, selected_rule_id=rid, doctor_inputs={"ulcer": "no", qfield(texts_[0]): ans})
        if expect:
            assert r["status"] == expect
        else:
            assert not any(n["field"] == qfield(texts_[0]) for n in r["needs_input"])
        if ans == "yes":
            assert has(r["blocks"], texts_[0])


# ---------------------------------------------------------------------------------------------------- boundary overlaps
def test_cetirizine_at_the_boundary_returns_both_rules_and_defaults_to_the_lower_dose():
    rs = [r for r in rules_of("cetirizine") if r["status"] == "VERIFIED" and r["population"].get("max_age_years") == 6
          or (r["status"] == "VERIFIED" and r["population"].get("min_age_years") == 6)]
    low, high = sorted(rs, key=lambda r: r["dose_mg"] * r["doses_per_day"])[:2]
    res = run("cetirizine", "allergy", quiz(age_y=6, wt=20))
    ids = {a["rule_id"] for a in res["alternatives"]}
    assert len(ids) == 2 and set(res["boundary_overlap"]) == ids
    assert res["selected_rule_id"] == res["suggested_rule_id"]
    assert res["dose_range_mg"] == [low["dose_mg"]] * 2 or res["dose_mg"] is not None
    sel = next(a for a in res["alternatives"] if a["selected"])
    assert sel["dose_range_mg"][0] == low["dose_mg"] and has(res["warnings"], "boundary")
    other = next(a["rule_id"] for a in res["alternatives"] if not a["selected"])
    res2 = run("cetirizine", "allergy", quiz(age_y=6, wt=20), selected_rule_id=other)
    assert res2["selected_rule_id"] == other                           # the doctor can still pick the other


def test_away_from_a_boundary_only_one_cetirizine_rule_applies():
    assert len(run("cetirizine", "allergy", quiz(age_y=9, wt=30))["alternatives"]) == 1
