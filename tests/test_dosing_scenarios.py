"""End-to-end demo scenarios (quiz answers in, result out), History check, demo mode and the growth-reference file."""
import json

import pytest

from dosing import audit, demo, formulary, history, mapper, service
from dosing.config import Config, DEMO_BANNER
from dosing.engine import apply_inputs, evaluate, Request
from dosing.safety import qfield

from dosing_helpers import F, quiz, rules_of

NOW = None


@pytest.fixture(autouse=True)
def datadir(tmp_path, monkeypatch):
    monkeypatch.setenv("INTAKE_DATA_DIR", str(tmp_path))
    return tmp_path


def kw(**o):
    return dict(doctor_id="demo_doctor", cfg=demo.DEMO_CFG, **o)


# ---------------------------------------------------------------- a) child with fever
def test_scenario_a_child_fever_paracetamol_syrup_and_daily_cap():
    rec = demo.none_apply(demo.record("child_fever"), "paracetamol", "demo_doctor")
    res = service.evaluate_for_record(rec, "paracetamol", "pain/fever", confirmed=["weight_kg"], **kw())
    rule, w = rules_of("paracetamol")[2], 16.0
    assert res["status"] == "ok" and res["final"] and res["demo_banner"] == DEMO_BANNER
    assert res["dose_range_mg"] == [rule["mg_per_kg"][0] * w, rule["mg_per_kg"][1] * w]
    assert res["product"] in {e["form"] + " " + e["strength"] for e in F().drugs["paracetamol"]["forms_india"] if e["form"] == "oral liquid"}
    assert res["volume_ml"] and res["daily_max_mg"] == min(rule["max_per_kg_per_day"] * w, rule["max_per_day_mg"])
    assert res["daily_total_mg"] <= res["daily_max_mg"]
    text = demo.render_text(res)
    assert DEMO_BANNER in text and "DAILY MAX" in text and "mL" in text


# ---------------------------------------------------------------- b) diabetes + kidney disease
def test_scenario_b_metformin_needs_creatinine_then_applies_the_egfr_band():
    rec = demo.none_apply(demo.record("diabetes_kidney"), "metformin", "demo_doctor")
    miss = service.evaluate_for_record(rec, "metformin", "type 2 diabetes", selected_rule_id="metformin#0", confirmed=["weight_kg"], **kw())
    assert miss["status"] == "needs_input" and any(n["field"] == "scr_mg_dl" for n in miss["needs_input"])
    band = next(r for r in F().drugs["metformin"]["renal_rules"] if r["action"].startswith("Do not start"))
    scr = demo.scr_for_egfr((band["min"] + band["max"]) / 2)
    res = service.evaluate_for_record(rec, "metformin", "type 2 diabetes", selected_rule_id="metformin#0", confirmed=["weight_kg"],
                                      doctor_inputs={"scr_mg_dl": scr}, **kw())
    assert res["status"] == "blocked" and any("Do not start" in b["text"] for b in res["blocks"])
    assert any("CKD-EPI 2021" in s for s in res["calculation_steps"])
    ok = service.evaluate_for_record(rec, "metformin", "type 2 diabetes", selected_rule_id="metformin#0", confirmed=["weight_kg"],
                                     doctor_inputs={"scr_mg_dl": demo.scr_for_egfr(band["max"] + 25)}, **kw())
    assert ok["status"] == "ok"


# ---------------------------------------------------------------- c) penicillin allergy
def test_scenario_c_amoxicillin_blocked_override_needs_category_and_reason_and_is_audited():
    rec = demo.none_apply(demo.record("penicillin_allergy"), "amoxicillin", "demo_doctor")
    base = dict(selected_rule_id="amoxicillin#0")
    assert service.evaluate_for_record(rec, "amoxicillin", "community-acquired pneumonia", **base, **kw())["status"] == "blocked"
    for cat, why in ((None, "Specialist advised it"), ("other", "short"), ("not_a_category", "Specialist advised it")):
        r = service.evaluate_for_record(rec, "amoxicillin", "community-acquired pneumonia", override_category=cat, override_reason=why, **base, **kw())
        assert r["status"] == "blocked" and not r["overrides"]
    n_before = len(audit.read())
    r = service.evaluate_for_record(rec, "amoxicillin", "community-acquired pneumonia", override_category="benefit_outweighs_risk",
                                    override_reason="Mild reaction only; ID consult done", **base, **kw())
    assert r["status"] != "blocked" and r["overrides"][0]["category"] == "benefit_outweighs_risk"
    new = audit.read()[n_before:]
    ov = [e for e in new if e["event"] == "override"]
    assert ov and ov[0]["override_category"] == "benefit_outweighs_risk" and ov[0]["override_reason"].startswith("Mild")
    assert audit.verify()
    assert any("OVERRIDE" in l for l in demo.render_text(r).splitlines())


def test_demo_script_runs_all_three_scenarios_and_prints_text():
    out = demo.run_all()
    assert len(out) == 3
    text = "\n".join(demo.render_text(res) for _, steps in out for _, res in steps)
    assert text.count(DEMO_BANNER) == sum(len(s) for _, s in out)               # banner on every result
    assert audit.verify()


# ---------------------------------------------------------------- demo mode
def test_demo_mode_forces_allow_unverified_and_banner(monkeypatch):
    monkeypatch.setenv("DOSING_DEMO_MODE", "1")
    monkeypatch.delenv("DOSING_ALLOW_UNVERIFIED", raising=False)
    cfg = Config.from_env()
    assert cfg.demo_mode and cfg.allow_unverified
    res = evaluate(Request("paracetamol", mapper.map_quiz(quiz()), "pain/fever", selected_rule_id="paracetamol#0"), cfg)
    assert res["demo"] and res["demo_banner"] == "DEMO - UNVERIFIED DATA"
    assert not Config().demo_mode and not Config().allow_unverified
    off = evaluate(Request("paracetamol", mapper.map_quiz(quiz()), "pain/fever", selected_rule_id="paracetamol#0"), Config())
    assert off["demo"] is False and off["demo_banner"] is None


# ---------------------------------------------------------------- History check
def test_history_items_cover_unknowns_with_exact_formulary_text():
    f = F()
    ctx = mapper.map_quiz(quiz(chief_complaint="fever"))
    items = {i.field: i for i in history.items_for(f, f.drugs["diclofenac"], ctx)}
    heart = [c["text"] for c in f.drugs["diclofenac"]["contraindications"] if c["text"].startswith("Established congestive heart failure")][0]
    q = items[qfield(heart)]
    assert heart in q.question and q.required and q.value == "unknown"
    for fld in ("ulcer", "gi_bleed", "allergy_nsaids"):
        assert fld in items
    assert items["allergy_nsaids"].value == "no" and items["ulcer"].value == "unknown"
    assert [i for i in history.unknown_items(history.items_for(f, f.drugs["diclofenac"], ctx)) if i.field == "allergy_nsaids"] == []


def test_history_answers_are_doctor_confirmed_reused_across_drugs_and_audited():
    rec = demo.record("child_fever")
    rec = service.save_history(rec, {"alcohol": "no", "ulcer": "no"}, doctor_id="D1")
    assert rec.visitHistory == {"alcohol": "no", "ulcer": "no"} and rec.visitHistoryBy == "D1"
    assert audit.read()[-1]["event"] == "history" and audit.read()[-1]["provenance"]["ulcer"]["provenance"] == "doctor_confirmed"
    for drug, ind in (("ibuprofen", "pain/fever"), ("paracetamol", "pain/fever")):
        res = service.evaluate_for_record(rec, drug, ind, doctor_id="D1", cfg=demo.DEMO_CFG)
        assert res["provenance"]["ulcer"]["provenance"] == "doctor_confirmed"
        assert not any(n["field"] == "ulcer" for n in res["needs_input"])
    with pytest.raises(ValueError):
        service.save_history(rec, {"ulcer": "maybe"}, doctor_id="D1")


def test_none_of_these_apply_sets_listed_unknowns_to_no_and_unanswered_stays_unknown():
    f = F()
    rec = demo.record("child_fever")
    before = history.unknown_items(history.items_for(f, f.drugs["ibuprofen"], mapper.map_record(rec)))
    assert before
    rec2 = demo.none_apply(rec, "ibuprofen", "D1")
    ctx = apply_inputs(mapper.map_record(rec2), {}, [], rec2.visitHistory)
    assert all(rec2.visitHistory[i.field] == "no" for i in before)
    assert history.unknown_items(history.items_for(f, f.drugs["ibuprofen"], ctx)) == []
    assert history.unknown_items(history.items_for(f, f.drugs["ibuprofen"], mapper.map_record(rec)))      # original record untouched
    unsure = apply_inputs(mapper.map_record(rec), {}, [], {"ulcer": "unsure"})
    assert unsure.tri("ulcer") == "unknown"


def test_unsure_pregnancy_in_history_means_possible():
    ctx = apply_inputs(mapper.map_quiz(quiz(sex="female", pregnancy="__skipped__", age_y=30)), {}, [], {"pregnant": "unsure"})
    assert ctx.get("pregnant") == "possible" and ctx.prov("pregnant") == "doctor_confirmed"


# ---------------------------------------------------------------- growth reference
def test_growth_reference_is_structure_only_and_marked_needs_data():
    doc = json.loads((mapper.GROWTH).read_text())
    assert doc["status"] == "needs data" and all(t["rows"] == [] for t in doc["tables"])
    ids = {t["id"] for t in doc["tables"]}
    assert any(i.startswith("WHO_CGS") for i in ids) and any(i.startswith("WHO_2007") for i in ids) and any(i.startswith("IAP_2015") for i in ids)
    assert json.loads(mapper.PLAUSIBILITY.read_text())["status"] == "DRAFT"


def test_cited_tables_are_used_when_filled_and_flag_outside_3sd(monkeypatch, tmp_path):
    doc = json.loads(mapper.GROWTH.read_text())
    for t in doc["tables"]:
        if t["id"] == "WHO_CGS_weight_for_age_boys_0_5y":
            t["rows"] = [{"age_months": 0, "minus3sd_kg": 2.1, "plus3sd_kg": 5.0}, {"age_months": 12, "minus3sd_kg": 6.9, "plus3sd_kg": 12.0}]
    p = tmp_path / "g.json"
    p.write_text(json.dumps(doc))
    monkeypatch.setattr(mapper, "GROWTH", p)
    assert mapper.plausibility(12, 20.0, "male")[2].startswith("cited: WHO_CGS")
    assert mapper.plausibility(12, 9.0, "male") is None
    c = mapper.map_quiz(quiz(age_y=0, age_m=12, sex="male", wt=20))
    assert c.get("weight_implausible")["source"].startswith("cited")
    assert c.get("weight_kg") == 20.0                                    # never corrected
