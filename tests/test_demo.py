from intake.demo import DEMO_SCENARIO, load_demo
from intake.models import load_graph
from intake.redflags import load_rules


def test_demo_session_is_complete_synthetic_chest_pain_with_red_flag():
    s = load_demo(load_graph(), load_rules(), "mr", token="PT-DEMOAA")
    assert DEMO_SCENARIO == "adult_chest_pain" and s.complete and s.language == "mr"
    assert s.answers["chief_complaint"] == "chest_pain"
    assert s.answers["cp_site"]["regions"] == ["chest_center"]
    rf = s.red_flags[0]
    assert rf.ruleId == "RF_CHEST_PAIN_RADIATION_SWEATING" and rf.draft
    assert rf.triggeredBy["cp_assoc"] == ["sweating", "nausea"]


def test_demo_keeps_unsure_distinct_from_skipped():
    rec = load_demo(load_graph(), load_rules()).finish()
    assert "diabetes" in rec.dosingInputs.missing and rec.answers["diabetes"] == "unsure"
