"""Quiz answers -> PatientContext: every node in the mapping table, skipped branches, 'not sure', age boundaries."""
import pytest

from dosing import mapper
from dosing.context import DERIVED, PATIENT, UNKNOWN
from intake.conditions import SKIPPED, UNSURE
from intake.models import load_graph

from dosing_helpers import quiz


def M(**kw):
    return mapper.map_quiz(quiz(**kw))


# -- age
def test_age_under_one_year_uses_months_with_no_window():
    c = M(age_y=0, age_m=7, sex="female", pregnancy=None)
    assert c.get("age_months") == 7 and c.get("age_window_months") == 0
    lo, hi = c.age_days()
    assert hi - lo == pytest.approx(30.4375)


def test_age_in_years_is_months_times_twelve_with_an_eleven_month_window():
    c = M(age_y=5)
    assert c.get("age_months") == 60 and c.get("age_window_months") == 11
    lo, hi = c.age_days()
    assert hi - lo == pytest.approx(12 * 30.4375)


@pytest.mark.parametrize("years,months", [(17, 204), (18, 216)])
def test_age_17_and_18_boundaries(years, months):
    c = M(age_y=years, sex="male")
    assert c.get("age_months") == months


def test_age_skipped_is_unknown():
    c = M(age_y=SKIPPED)
    assert c.get("age_months") is None and c.prov("age_months") == UNKNOWN


def test_under_one_year_without_months_is_unknown():
    a = quiz(age_y=0, age_m=3)
    del a["age_months"]
    assert mapper.map_quiz(a).get("age_months") is None


# -- sex
def test_sex_other_is_unknown_for_formulas():
    c = M(sex="other", pregnancy="no")
    assert c.get("sex") == "other" and c.get("sex_for_formula") is None
    assert M(sex="female", pregnancy="no").get("sex_for_formula") == "female"


# -- pregnancy
def test_pregnancy_answers():
    assert M(sex="female", pregnancy="yes").get("pregnant") == "yes"
    assert M(sex="female", pregnancy="no").get("pregnant") == "no"
    c = M(sex="female", pregnancy=UNSURE)
    assert c.get("pregnant") == "possible" and c.prov("pregnant") == PATIENT


def test_pregnancy_skipped_is_unknown_not_no():
    c = M(sex="female", pregnancy=SKIPPED)
    assert c.get("pregnant") is None and c.tri("pregnant") == "unknown"


@pytest.mark.parametrize("sex,age", [("male", 30), ("female", 11), ("female", 56), ("male", 5)])
def test_pregnancy_not_asked_is_a_derived_no_only_when_the_quiz_did_not_ask(sex, age):
    c = M(sex=sex, age_y=age)
    assert c.get("pregnant") == "no" and c.prov("pregnant") == DERIVED


@pytest.mark.parametrize("age", [12, 55])
def test_pregnancy_age_band_edges_are_asked_by_the_graph(age):
    graph = load_graph()
    from intake.engine import recompute_path
    path = recompute_path(graph, quiz(age_y=age, sex="female")).path
    assert "pregnancy" in path
    c = M(sex="female", age_y=age)                       # asked but not answered: unknown, never 'no'
    assert c.get("pregnant") is None


def test_pregnancy_unknown_when_quiz_never_reached_the_question():
    c = mapper.map_quiz({"consent": "agree", "age_years": 30, "sex": "female"})
    assert c.get("pregnant") is None


def test_pregnancy_bleeding_is_context():
    assert M(sex="female", pregnancy="yes", preg_bleeding="yes").tri("pregnancy_bleeding") == "yes"
    assert M(sex="female", pregnancy="yes").tri("pregnancy_bleeding") == "unknown"


# -- weight
def test_weight_is_patient_reported_and_plausibility_flags_without_correcting():
    c = M(age_y=0, age_m=3, wt=60)
    assert c.get("weight_kg") == 60.0 and c.prov("weight_kg") == PATIENT
    assert c.get("weight_implausible")["w"] == 60.0
    assert M(age_y=0, age_m=6, wt=7).get("weight_implausible") is None


def test_weight_skipped_is_unknown():
    assert M(wt=SKIPPED).get("weight_kg") is None


# -- allergies
def test_allergy_none_is_exclusive_and_means_known_no():
    c = M(allergies=["none"])
    assert [c.tri(f"allergy_{k}") for k in ("penicillins", "sulfa", "nsaids")] == ["no", "no", "no"]


def test_allergy_classes_selected():
    c = M(allergies=["penicillins", "nsaids"])
    assert (c.tri("allergy_penicillins"), c.tri("allergy_nsaids"), c.tri("allergy_sulfa")) == ("yes", "yes", "no")


@pytest.mark.parametrize("v", [SKIPPED, UNSURE])
def test_allergy_skipped_or_unsure_is_unknown(v):
    assert M(allergies=v).tri("allergy_penicillins") == "unknown"


def test_allergy_other_free_text_kept():
    assert M(allergies=["sulfa"], allergy_other=" peanuts ").allergy_other_raw == "peanuts"


# -- current medicines
def test_meds_none_is_a_known_empty_list():
    c = M(meds_any="no")
    assert c.get("meds_known") == "yes" and c.meds == []


def test_meds_free_text_generic_brand_and_unparsed():
    c = M(meds_any="yes", meds_list="Tab Dolo 650, warfarin 5mg; Zorbitex")
    assert {m.generic for m in c.meds} == {"paracetamol", "warfarin"} and c.unparsed_meds == ["Zorbitex"]


@pytest.mark.parametrize("a", [{"meds_any": UNSURE}, {"meds_any": SKIPPED}, {"meds_any": "yes", "meds_list": SKIPPED}])
def test_meds_unsure_or_skipped_is_unknown(a):
    assert M(**a).get("meds_known") != "yes"


# -- conditions
@pytest.mark.parametrize("node,field", [("kidney", "kidney_disease"), ("liver", "liver_disease"), ("diabetes", "diabetes"),
                                       ("hypertension", "hypertension"), ("asthma", "asthma")])
def test_condition_yes_no_unsure_skipped(node, field):
    assert M(**{node: "yes"}).tri(field) == "yes"
    assert M(**{node: "no"}).tri(field) == "no"
    assert M(**{node: UNSURE}).tri(field) == "unknown"
    assert M(**{node: SKIPPED}).tri(field) == "unknown"


def test_hx_abdomen_only_on_the_abdominal_branch():
    c = M(hx_abdomen=["ulcer", "alcohol"])
    assert (c.tri("ulcer"), c.tri("alcohol"), c.tri("stones")) == ("yes", "yes", "no")
    c = M()
    assert c.tri("ulcer") == "unknown" and c.tri("alcohol") == "unknown"        # not asked is not 'no'


def test_gi_bleed_from_danger_signs():
    assert M(danger_signs=["vomit_blood"]).tri("gi_bleed") == "yes"
    assert M(danger_signs=["black_stool", "confusion"]).tri("gi_bleed") == "yes"
    assert M(danger_signs=["none"]).tri("gi_bleed") == "no"
    assert M(danger_signs=None).tri("gi_bleed") == "unknown"


def test_hx_chest_heart_only_on_the_chest_pain_branch():
    assert M(hx_chest=["heart", "smoking"]).tri("heart_disease") == "yes"
    assert M(hx_chest=["cholesterol"]).tri("heart_disease") == "no"
    assert M().tri("heart_disease") == "unknown"
    assert M(hx_cough=["smoking"]).tri("smoking") == "yes"


def test_complaint_and_red_flags_are_context_only():
    c = mapper.map_quiz(quiz(chief_complaint="chest_pain"), red_flags=[{"ruleId": "RF_X", "severity": "high", "label": "draft"}])
    assert c.get("complaint") == "chest_pain" and c.red_flags[0]["ruleId"] == "RF_X"


def test_mapper_does_not_modify_the_answers():
    a = quiz(allergies=["none"], meds_any="yes", meds_list="crocin")
    before = dict(a)
    mapper.map_quiz(a)
    assert a == before


def test_provenance_values_are_valid():
    from dosing.context import PROVENANCE
    c = M(sex="female", pregnancy="no", meds_any="yes", meds_list="crocin")
    assert {v["provenance"] for v in c.provenance_dict().values()} <= set(PROVENANCE)
