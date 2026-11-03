import json

import pytest

from intake.bodymap import make_answer
from intake.conditions import SKIPPED, UNSURE
from intake.models import load_graph
from intake.redflags import DRAFT_LABEL, REVIEW_STATUS, RedFlagRule, evaluate_rules, load_rules
from intake.synthetic import BANK, run_bank

G, RULES = load_graph(), load_rules()


def fired(overrides=None, **kw):
    return {t.ruleId for t in run_bank(G, RULES, overrides, **kw).red_flags}


def test_benign_baseline_triggers_nothing():
    assert fired() == set()
    for cc in ["fever", "cough_breath", "abdominal_pain", "headache", "chest_pain", "other"]:
        assert fired({"chief_complaint": cc}) == set(), cc


CHEST = {"chief_complaint": "chest_pain"}
BM = lambda regs, mode="map": make_answer(regs, mode)
LEFT_CHEST = BM(["chest_left"])
# (rule id, answers that must trigger it, answers that must NOT)
CASES = [
    ("RF_CHEST_PAIN_RADIATION_SWEATING",
     [{**CHEST, "cp_assoc": ["sweating"]}, {**CHEST, "cp_assoc": ["nausea", "sweating"]},
      {**CHEST, "cp_site": BM(["chest_center"]), "body_map_radiation": BM(["jaw_front"])},            # centre chest -> jaw
      {**CHEST, "cp_site": LEFT_CHEST, "body_map_radiation": BM(["upper_arm_left"])},                # left chest -> arm
      {**CHEST, "cp_site": LEFT_CHEST, "body_map_radiation": BM(["hand_left", "forearm_left"], "list")},
      {**CHEST, "cp_site": BM(["chest_left", "chest_right"]), "body_map_radiation": BM(["neck_front"])}],
     [CHEST,                                                                                          # right chest, no spread
      {**CHEST, "cp_site": BM(["chest_right"]), "body_map_radiation": BM(["upper_arm_right"])},      # not left/centre
      {**CHEST, "cp_site": LEFT_CHEST, "body_map_radiation": BM(["lower_back_left"])},               # spreads, but not arm/jaw
      {**CHEST, "cp_site": LEFT_CHEST, "body_map_radiation": UNSURE},
      {**CHEST, "cp_site": LEFT_CHEST, "body_map_radiation": make_answer([], "list", "tell_doctor")},
      {**CHEST, "cp_site": LEFT_CHEST, "body_map_radiation": make_answer([], "list", "none")},
      {**CHEST, "cp_site": UNSURE, "body_map_radiation": BM(["upper_arm_left"])},
      {**CHEST, "cp_assoc": ["breathless", "nausea"]}, {**CHEST, "cp_assoc": [UNSURE]}, {**CHEST, "cp_assoc": SKIPPED},
      {"chief_complaint": "abdominal_pain", "body_map_radiation": BM(["upper_arm_left"])}]),         # not a chest complaint
    ("RF_BREATHLESS_AT_REST",
     [{"chief_complaint": "cough_breath", "cb_rest": "yes"},
      {"chief_complaint": "cough_breath", "cb_main": "breathless_only", "cb_rest": "yes"}],
     [{"chief_complaint": "cough_breath", "cb_rest": "no"}, {"chief_complaint": "cough_breath", "cb_rest": "unsure"},
      {"chief_complaint": "cough_breath", "cb_main": "cough_only"}]),
    ("RF_SUDDEN_SEVERE_HEADACHE",
     [{"chief_complaint": "headache", "hd_worst": "yes"},
      {"chief_complaint": "headache", "hd_onset": "sudden", "hd_severity": 8},
      {"chief_complaint": "headache", "hd_onset": "sudden", "hd_severity": 10}],
     [{"chief_complaint": "headache", "hd_onset": "sudden", "hd_severity": 7},            # sudden but not severe
      {"chief_complaint": "headache", "hd_onset": "days", "hd_severity": 10},            # severe but gradual
      {"chief_complaint": "headache", "hd_worst": "unsure"}, {"chief_complaint": "headache", "hd_worst": "no"},
      {"chief_complaint": "headache", "hd_onset": "sudden", "hd_severity": UNSURE}]),
    ("RF_FEVER_NECK_STIFFNESS",
     [{"fev_assoc": ["neck_stiffness"]}, {"fev_assoc": ["chills", "neck_stiffness"]},
      {"chief_complaint": "headache", "hd_assoc": ["fever", "neck_stiffness"]}],
     [{"fev_assoc": ["chills"]}, {"chief_complaint": "headache", "hd_assoc": ["neck_stiffness"]},
      {"chief_complaint": "headache", "hd_assoc": ["fever"]}, {"chief_complaint": "cough_breath"}]),
    ("RF_VOMITING_BLOOD_OR_BLACK_STOOL",
     [{"danger_signs": ["vomit_blood"]}, {"danger_signs": ["black_stool"]}],
     [{"danger_signs": ["none"]}, {"danger_signs": [UNSURE]}, {"danger_signs": ["seizure"]}]),
    ("RF_INFANT_FEVER_UNDER_3_MONTHS",
     [{"age_years": 0, "age_months": 0}, {"age_years": 0, "age_months": 2}],
     [{"age_years": 0, "age_months": 3}, {"age_years": 0, "age_months": 11}, {"age_years": 1},
      {"age_years": 0, "age_months": UNSURE}, {"age_years": UNSURE},
      {"age_years": 0, "age_months": 1, "chief_complaint": "headache"}]),
    ("RF_PREGNANCY_BLEEDING",
     [{"sex": "female", "pregnancy": "yes", "preg_bleeding": "yes"}],
     [{"sex": "female", "pregnancy": "yes", "preg_bleeding": "no"}, {"sex": "female", "pregnancy": "yes", "preg_bleeding": "unsure"},
      {"sex": "female", "pregnancy": "no"}, {"sex": "female", "pregnancy": "unsure"}, {"sex": "male"}]),
    ("RF_CONFUSION", [{"danger_signs": ["confusion"]}], [{"danger_signs": ["none"]}, {"danger_signs": ["seizure"]}]),
    ("RF_SEIZURE", [{"danger_signs": ["seizure"]}, {"danger_signs": ["seizure", "confusion"]}],
     [{"danger_signs": ["none"]}, {"danger_signs": ["confusion"]}]),
    ("RF_SUDDEN_WEAKNESS_OR_SPEECH", [{"danger_signs": ["weakness"]}, {"danger_signs": ["speech"]}],
     [{"danger_signs": ["none"]}, {"danger_signs": ["confusion"]}]),
]
# the infant rule needs fever as the complaint; spell that out once
for i, (rid, pos, neg) in enumerate(CASES):
    if rid == "RF_INFANT_FEVER_UNDER_3_MONTHS":
        CASES[i] = (rid, [{**p, "chief_complaint": "fever"} for p in pos],
                    [n if "chief_complaint" in n else {**n, "chief_complaint": "fever"} for n in neg])
    if rid == "RF_FEVER_NECK_STIFFNESS":
        CASES[i] = (rid, [p if "chief_complaint" in p else {**p, "chief_complaint": "fever"} for p in pos],
                    [n if "chief_complaint" in n else {**n, "chief_complaint": "fever"} for n in neg])


def _flat(cases):
    for rid, pos, neg in cases:
        for p in pos:
            yield pytest.param(rid, p, True, id=f"{rid}-pos-{json.dumps(p, sort_keys=True)[:60]}")
        for n in neg:
            yield pytest.param(rid, n, False, id=f"{rid}-neg-{json.dumps(n, sort_keys=True)[:60]}")


@pytest.mark.parametrize("rid,ov,should", list(_flat(CASES)))
def test_rule_positive_and_negative(rid, ov, should):
    hit = rid in fired(ov, allow_unused=True)
    assert hit is should


def test_every_rule_has_positive_and_negative_case():
    assert {c[0] for c in CASES} == {r.id for r in RULES}
    assert all(c[1] and c[2] for c in CASES)


def test_unsure_never_triggers_any_rule():
    """'Not sure' is a real answer but must not be read as 'yes'."""
    ov = {"cb_rest": UNSURE, "hd_worst": UNSURE, "pregnancy": UNSURE, "danger_signs": [UNSURE]}
    assert fired({**ov, "chief_complaint": "cough_breath", "sex": "female"}, allow_unused=True) == set()


def test_flags_update_after_every_answer_and_clear_when_answer_changes():
    s = run_bank(G, RULES, stop_at="cb_rest", overrides={"chief_complaint": "cough_breath"}, allow_unused=True)
    assert s.red_flags == []
    s.answer("cb_rest", "yes")
    assert [t.ruleId for t in s.red_flags] == ["RF_BREATHLESS_AT_REST"]     # evaluated immediately, before the end
    assert not s.complete
    s.answer("cb_rest", "no")
    assert s.red_flags == []


def test_flag_records_triggering_answers_and_draft_label():
    site, rad = BM(["chest_left"]), BM(["upper_arm_left"])
    s = run_bank(G, RULES, {**CHEST, "cp_site": site, "body_map_radiation": rad, "cp_assoc": ["nausea"]})
    (t,) = s.red_flags
    assert t.triggeredBy == {"chief_complaint": "chest_pain", "cp_assoc": ["nausea"], "cp_site": site, "body_map_radiation": rad}
    assert t.draft and t.label == DRAFT_LABEL and t.patientMessage["en"] == "Please tell the staff now."


def test_urgent_before_soon_and_file_order_kept():
    mk = lambda i, sev, node: RedFlagRule.model_validate({
        "id": i, "condition": {"equals": [node, "yes"]}, "severity": sev, "staffMessage": i,
        "patientMessage": {"en": "a", "hi": "b", "mr": "c"}})
    rules = [mk("S1", "soon", "a"), mk("U1", "urgent", "b"), mk("S2", "soon", "c"), mk("U2", "urgent", "d")]
    out = evaluate_rules(rules, {"a": "yes", "b": "yes", "c": "yes", "d": "yes"})
    assert [t.ruleId for t in out] == ["U1", "U2", "S1", "S2"]


def test_checked_source_changes_label_and_clears_draft_flag():
    r = RedFlagRule.model_validate({
        "id": "X", "condition": {"answered": "a"}, "severity": "soon", "staffMessage": "m",
        "patientMessage": {"en": "a", "hi": "b", "mr": "c"}, "sourceChecked": True,
        "source": {"name": "Doc", "section": "4.2", "url": "https://x", "accessedOn": "2026-01-01"}})
    (t,) = evaluate_rules([r], {"a": 1})
    assert not t.draft and t.label == "Doc, 4.2"
    # sourceChecked without a source is still a draft
    r2 = r.model_copy(update={"source": None})
    assert r2.is_draft


def test_shipped_rules_are_unsourced_drafts():
    for r in RULES:
        assert r.source is None and r.sourceChecked is False and r.reviewStatus == REVIEW_STATUS
        assert r.severity in ("urgent", "soon")
        assert all(r.patientMessage.get(l) for l in ("en", "hi", "mr"))
    raw = json.loads((__import__("intake.redflags", fromlist=["x"]).RULES_PATH).read_text())
    assert all(r["source"] is None and r["sourceChecked"] is False for r in raw["rules"])


def test_list_unsourced_script(capsys):
    import runpy, sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    ns = runpy.run_path(str(Path(__file__).resolve().parent.parent / "scripts" / "list_unsourced_rules.py"))
    assert ns["main"]() == 1
    out = capsys.readouterr().out
    assert all(r.id in out for r in RULES) and f"{len(RULES)} of {len(RULES)} rules need a source" in out


def test_validate_script_passes(capsys):
    import runpy
    from pathlib import Path
    ns = runpy.run_path(str(Path(__file__).resolve().parent.parent / "scripts" / "validate_graph.py"))
    assert ns["main"]() == 0
