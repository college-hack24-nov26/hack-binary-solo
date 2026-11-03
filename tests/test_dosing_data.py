"""The formulary shapes the engine must understand, formula arithmetic, and the synonym table's tie to the formulary."""
import math

import pytest

from dosing import derived, formulary, meds, mapper
from dosing.engine import Request, evaluate
from dosing.rules import indications

from dosing_helpers import CFG_UNVERIFIED, F, quiz


def test_validator_finds_no_unsupported_dose_type_or_field():
    assert formulary.validate(F().raw) == []


def test_validator_fails_loudly_on_unknown_dose_type_and_field():
    raw = {"meta": {}, "sources": {}, "formulas": {}, "defaults": {}, "interactions": [], "drugs": [
        {"id": "x", "forms_india": [], "dose_rules": [{"indication": "i", "population": {"min_weight": 3, "bad": 1}, "dose_type": "pk_model",
                                                        "mystery": 1}]}]}
    issues = formulary.validate(raw)
    assert any("unsupported dose_type 'pk_model'" in i for i in issues)
    assert any("mystery" in i for i in issues)
    assert any("unknown population keys" in i for i in issues)
    with pytest.raises(ValueError):
        formulary.check_at_startup(formulary.Formulary(raw=raw), strict=True)


def test_fifteen_drugs_and_every_drug_has_a_synonym_entry_with_its_class_label():
    f = F()
    assert len(f.drugs) == 15
    for d in f.drugs.values():
        labs = [meds.canon(l) for l in meds.labels_for_drug(d["id"])]
        assert meds.canon(d["duplicate_class"]) in labs, d["id"]
        if d.get("qt_risk"):
            assert "qt-prolonging" in labs, d["id"]


def test_every_rule_in_the_formulary_is_handled_without_error():
    """Each rule, evaluated for an adult and a child with all doctor inputs supplied, ends in a defined status."""
    f = F()
    inputs = {"scr_mg_dl": 1.0, "height_cm": 150, "doses_per_day": 2, "mg_per_kg_per_day": 10, "qt_history": "no", "ulcer": "no",
              "heart_disease": "no", "child_pugh_class": "A", "child_pugh_score": 5, "lactating": "no", "alcohol": "no"}
    for did, d in f.drugs.items():
        for ind in indications(d):
            for answers in (quiz(age_y=40, wt=70), quiz(age_y=0, age_m=8, wt=8), quiz(age_y=9, wt=28)):
                res = evaluate(Request(did, mapper.map_quiz(answers), ind["key"], doctor_inputs=dict(inputs)), CFG_UNVERIFIED)
                assert res["status"] in ("ok", "needs_input", "blocked", "refused")


def test_every_rule_reaches_a_defined_calc_outcome_for_every_dose_type():
    """Calling the calculator directly on every (expanded) rule: it computes, plans, gives text, or says exactly what is missing."""
    from dosing import calc, rules
    f, cfg = F(), CFG_UNVERIFIED
    types = set()
    for did, d in f.drugs.items():
        for r0 in d["dose_rules"]:
            types.add(r0["dose_type"])
            for _, r in rules.expand(r0):
                for answers in (quiz(age_y=40, wt=70), quiz(age_y=0, age_m=8, wt=8)):
                    c = calc.compute(f, d, r, mapper.map_quiz(answers), {"doses_per_day": 2, "mg_per_kg_per_day": 10}, cfg)
                    assert c.kind in ("numeric", "text", "plan", "duration") or c.needs or c.refused, (did, r["indication"])
                    if c.kind == "numeric":
                        assert c.lo is not None and c.hi >= c.lo > 0
    assert types == formulary.SUPPORTED_DOSE_TYPES


def test_formulas_are_evaluated_from_the_json_strings():
    f = F()
    assert derived.cockcroft_gault(f, 50, 70, 1.0, False) == pytest.approx((140 - 50) * 70 / (72 * 1.0))
    assert derived.cockcroft_gault(f, 50, 70, 1.0, True) == pytest.approx((140 - 50) * 70 / (72 * 1.0) * 0.85)
    k, a = f.formulas["ckd_epi_2021"]["k"]["male"], f.formulas["ckd_epi_2021"]["a"]["male"]
    expect = 142 * min(1.0 / k, 1) ** a * max(1.0 / k, 1) ** -1.2 * 0.9938 ** 50
    assert derived.ckd_epi(f, 50, 1.0, False) == pytest.approx(expect)
    assert derived.ckd_epi(f, 50, 1.0, True) == pytest.approx(
        142 * min(1.0 / 0.7, 1) ** -0.241 * max(1.0 / 0.7, 1) ** -1.2 * 0.9938 ** 50 * 1.012)
    assert derived.schwartz(f, 120, 0.6) == pytest.approx(0.413 * 120 / 0.6)
    assert derived.bsa(f, 170, 70) == pytest.approx(math.sqrt(170 * 70 / 3600))
    ibw, abw, fac = derived.body_weights(f, 170, 90, True, None)
    assert fac == f.formulas["adjusted_body_weight"]["factor_default"]
    assert abw == pytest.approx(ibw + fac * (90 - ibw))
    assert derived.body_weights(f, 170, 90, True, 0.3)[2] == 0.3        # configurable


def test_safe_eval_rejects_anything_but_arithmetic():
    for bad in ("__import__('os').system('x')", "(1).__class__", "a.b", "[1,2]", "lambda: 1"):
        with pytest.raises(Exception):
            derived.safe_eval(bad, {"a": 1})
