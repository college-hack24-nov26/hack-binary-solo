import pytest

from intake.conditions import SKIPPED, UNSURE
from intake.engine import answer_label, next_node, recompute_path, validate_answer
from intake.models import END, load_graph
from intake.redflags import load_rules
from intake.session import ConsentRequired, IntakeSession
from intake.synthetic import BANK, run_bank

G = load_graph()
RULES = load_rules()
ADULT_F = {"age_years": 30, "sex": "female"}

# (node, answers, expected next). Together these must exercise every rule and every default.
BRANCHES = [
    ("consent", {"consent": "agree"}, "age_years"),
    ("consent", {"consent": "decline"}, END),
    ("age_years", {"age_years": 0}, "age_months"),
    ("age_years", {"age_years": 5}, "sex"),
    ("age_years", {"age_years": UNSURE}, "sex"),
    ("age_months", {"age_months": 2}, "sex"),
    # pregnancy is only asked where relevant
    ("sex", {"age_years": 30, "sex": "female"}, "pregnancy"),
    ("sex", {"age_years": 30, "sex": "male"}, "weight_kg"),
    ("sex", {"age_years": 8, "sex": "female"}, "weight_kg"),
    ("sex", {"age_years": 11, "sex": "female"}, "weight_kg"),
    ("sex", {"age_years": 12, "sex": "female"}, "pregnancy"),
    ("sex", {"age_years": 55, "sex": "female"}, "pregnancy"),
    ("sex", {"age_years": 56, "sex": "female"}, "weight_kg"),
    ("sex", {"age_years": UNSURE, "sex": "female"}, "pregnancy"),
    ("sex", {"age_years": 30, "sex": "other"}, "pregnancy"),
    ("sex", {"age_years": 30, "sex": UNSURE}, "pregnancy"),
    ("sex", {"age_years": 30, "sex": SKIPPED}, "pregnancy"),
    ("pregnancy", {"pregnancy": "yes"}, "preg_bleeding"),
    ("pregnancy", {"pregnancy": "no"}, "weight_kg"),
    ("pregnancy", {"pregnancy": "unsure"}, "weight_kg"),
    ("preg_bleeding", {"preg_bleeding": "no"}, "weight_kg"),
    ("weight_kg", {"weight_kg": 60}, "allergies"),
    ("allergies", {"allergies": ["none"]}, "meds_any"),
    ("allergies", {"allergies": ["sulfa"]}, "allergy_other"),
    ("allergies", {"allergies": [UNSURE]}, "allergy_other"),
    ("allergy_other", {"allergy_other": "x"}, "meds_any"),
    ("meds_any", {"meds_any": "yes"}, "meds_list"),
    ("meds_any", {"meds_any": "no"}, "kidney"),
    ("meds_any", {"meds_any": "unsure"}, "kidney"),
    ("meds_list", {"meds_list": "x"}, "kidney"),
    ("kidney", {}, "liver"), ("liver", {}, "diabetes"), ("diabetes", {}, "hypertension"),
    ("hypertension", {}, "asthma"), ("asthma", {}, "chief_complaint"),
    ("chief_complaint", {"chief_complaint": "fever"}, "fev_site"),
    ("chief_complaint", {"chief_complaint": "cough_breath"}, "cb_main"),
    ("chief_complaint", {"chief_complaint": "abdominal_pain"}, "ab_site"),
    ("chief_complaint", {"chief_complaint": "headache"}, "hd_site"),
    ("chief_complaint", {"chief_complaint": "chest_pain"}, "cp_site"),
    ("chief_complaint", {"chief_complaint": "other"}, "other_text"),
    ("other_text", {}, "danger_signs"),
    # fever module (linear)
    ("fev_site", {}, "fev_onset"), ("fev_onset", {}, "fev_course"), ("fev_course", {}, "fev_temp"), ("fev_temp", {}, "fev_assoc"),
    ("fev_assoc", {}, "fev_relieve"), ("fev_relieve", {}, "fev_severity"), ("fev_severity", {}, "danger_signs"),
    # cough module: skips what earlier answers settle
    ("cb_main", {"cb_main": "both"}, "cb_site"), ("cb_site", {}, "cb_onset"),
    ("cb_onset", {"cb_main": "cough_only"}, "cb_sputum"),
    ("cb_onset", {"cb_main": "breathless_only"}, "cb_rest"),
    ("cb_onset", {"cb_main": "both"}, "cb_rest"),
    ("cb_rest", {"cb_main": "breathless_only"}, "cb_assoc"),
    ("cb_rest", {"cb_main": "both"}, "cb_sputum"),
    ("cb_sputum", {}, "cb_assoc"), ("cb_assoc", {}, "cb_pattern"), ("cb_pattern", {}, "cb_severity"),
    ("cb_severity", {}, "cb_relieve"), ("cb_relieve", {}, "danger_signs"),
    # abdominal
    ("ab_site", {}, "ab_onset"), ("ab_onset", {}, "ab_character"), ("ab_character", {}, "body_map_radiation"),
    ("body_map_radiation", {"chief_complaint": "abdominal_pain"}, "ab_assoc"), ("ab_assoc", {}, "ab_pattern"), ("ab_pattern", {}, "ab_severity"),
    # region-driven follow-ups (more in test_region_followups.py)
    ("ab_assoc", {"ab_site": {"regions": ["upper_abdomen_left"]}}, "abx_meals"),
    ("ab_assoc", {"ab_site": {"regions": ["pelvic_area"]}}, "abx_urine_stool"),
    ("abx_meals", {}, "ab_pattern"), ("abx_urine_stool", {}, "ab_pattern"),
    ("ab_severity", {}, "ab_relieve"), ("ab_relieve", {}, "danger_signs"),
    # headache
    ("hd_site", {}, "hd_onset"), ("hd_onset", {}, "hd_character"), ("hd_character", {}, "hd_worst"),
    ("hd_worst", {}, "hd_assoc"), ("hd_assoc", {}, "hd_course"),
    ("hd_assoc", {"hd_site": {"regions": ["head_front"]}}, "hdx_eyes_nose"),
    ("hd_assoc", {"hd_site": {"regions": ["neck_back"]}}, "hdx_neck_tight"),
    ("hdx_eyes_nose", {}, "hd_course"), ("hdx_neck_tight", {}, "hd_course"), ("hd_course", {}, "hd_severity"),
    ("hd_severity", {}, "hd_trigger"), ("hd_trigger", {}, "hd_relieve"), ("hd_relieve", {}, "danger_signs"),
    # chest pain
    ("cp_site", {}, "cp_onset"), ("cp_onset", {}, "cp_char"), ("cp_char", {}, "body_map_radiation"),
    ("body_map_radiation", {"chief_complaint": "chest_pain"}, "cp_assoc"), ("cp_assoc", {}, "cp_course"), ("cp_course", {}, "cp_exac"),
    ("cp_assoc", {"cp_site": {"regions": ["chest_center"]}}, "cpx_episode_len"),
    ("cp_assoc", {"cp_site": {"regions": ["chest_right"]}}, "cpx_skin"),
    ("cpx_episode_len", {}, "cpx_arm_numb"), ("cpx_arm_numb", {}, "cp_course"), ("cpx_skin", {}, "cp_course"),
    ("cp_exac", {}, "cp_relieve"), ("cp_relieve", {}, "cp_severity"), ("cp_severity", {}, "danger_signs"),
    # shared tail, routed back to a complaint-specific history question
    ("danger_signs", {"chief_complaint": "fever"}, "hx_fever"),
    ("danger_signs", {"chief_complaint": "cough_breath"}, "hx_cough"),
    ("danger_signs", {"chief_complaint": "abdominal_pain"}, "hx_abdomen"),
    ("danger_signs", {"chief_complaint": "headache"}, "hx_head"),
    ("danger_signs", {"chief_complaint": "chest_pain"}, "hx_chest"),
    ("danger_signs", {"chief_complaint": "other"}, "hx_similar"),
    ("hx_fever", {}, "hx_similar"), ("hx_cough", {}, "hx_similar"), ("hx_abdomen", {}, "hx_similar"),
    ("hx_head", {}, "hx_similar"), ("hx_chest", {}, "hx_similar"),
    ("hx_similar", {}, END),
]


@pytest.mark.parametrize("node,answers,expected", BRANCHES, ids=lambda x: x if isinstance(x, str) else None)
def test_next_node(node, answers, expected):
    assert next_node(G, answers, node) == expected


def test_branch_table_covers_every_node_and_every_rule():
    assert {n for n, _, _ in BRANCHES} == set(G.ids())
    for node in G.nodes:
        gotos = {r.goto for r in node.next.rules} | {node.next.default}
        hit = {e for n, _, e in BRANCHES if n == node.id}
        assert gotos <= hit, (node.id, gotos - hit)


def test_every_branch_is_reachable_on_a_real_run():
    """Table rows are conditions in isolation; also walk each complaint end to end."""
    for cc in ["fever", "cough_breath", "abdominal_pain", "headache", "chest_pain", "other"]:
        s = run_bank(G, RULES, {"chief_complaint": cc})
        assert s.complete and s.path[-1] == "hx_similar"


# ------------------------------------------------------------ skipping settled questions
def test_cough_only_skips_breathlessness_at_rest():
    s = run_bank(G, RULES, {"chief_complaint": "cough_breath", "cb_main": "cough_only"})
    assert "cb_rest" not in s.path and "cb_sputum" in s.path


def test_breathless_only_skips_sputum():
    s = run_bank(G, RULES, {"chief_complaint": "cough_breath", "cb_main": "breathless_only"})
    assert "cb_sputum" not in s.path and "cb_rest" in s.path


def test_months_only_for_under_one_and_pregnancy_only_where_relevant():
    assert "age_months" not in run_bank(G, RULES).path
    assert "age_months" in run_bank(G, RULES, {"age_years": 0}).path
    assert "pregnancy" not in run_bank(G, RULES).path                      # adult male
    assert "pregnancy" in run_bank(G, RULES, {"sex": "female"}).path
    s = run_bank(G, RULES, {"sex": "female", "pregnancy": "no"})
    assert "preg_bleeding" not in s.path
    assert "preg_bleeding" in run_bank(G, RULES, {"sex": "female", "pregnancy": "yes"}).path


def test_no_allergy_skips_free_text_and_no_meds_skips_list():
    s = run_bank(G, RULES)
    assert "allergy_other" not in s.path and "meds_list" not in s.path


# ------------------------------------------------------------ recompute on back / change
def test_changing_complaint_drops_old_module_answers():
    s = run_bank(G, RULES, {"chief_complaint": "chest_pain"})
    assert "cp_site" in s.answers
    s.answer("chief_complaint", "headache")
    assert "cp_site" not in s.answers and "cp_severity" not in s.answers
    assert s.pending == "hd_site"
    assert "age_years" in s.answers and "weight_kg" in s.answers       # earlier answers kept


def test_changing_back_to_old_complaint_asks_again():
    s = run_bank(G, RULES, {"chief_complaint": "chest_pain"})
    s.answer("chief_complaint", "headache")
    s.answer("chief_complaint", "chest_pain")
    assert s.pending == "cp_site"


def test_changing_age_to_infant_adds_months_question_and_drops_pregnancy():
    s = run_bank(G, RULES, {"sex": "female", "pregnancy": "yes", "preg_bleeding": "yes"})
    assert s.red_flags
    s.answer("age_years", 0)
    assert s.pending == "age_months"
    assert "pregnancy" not in s.answers and "preg_bleeding" not in s.answers
    assert s.red_flags == []                       # flag disappears with the answers behind it


def test_changing_an_answer_that_does_not_alter_path_keeps_everything():
    s = run_bank(G, RULES)
    before = dict(s.answers)
    s.answer("weight_kg", 71)
    assert s.complete and s.answers == {**before, "weight_kg": 71}


def test_previous_walks_the_path_back():
    s = IntakeSession(G, RULES)
    s.answer("consent", "agree"); s.answer("age_years", 40)
    assert s.pending == "sex" and s.previous("sex") == "age_years" and s.previous("consent") is None


def test_recompute_path_pure_and_stops_at_first_unanswered():
    res = recompute_path(G, {"consent": "agree", "age_years": 40, "ghost": 1})
    assert res.path == ["consent", "age_years", "sex"] and res.pending == "sex"
    assert "ghost" not in res.answers and not res.complete


def test_recompute_detects_cycle():
    from copy import deepcopy
    g = deepcopy(G)
    g.node("weight_kg").next.default = "sex"
    ans = {"consent": "agree", "age_years": 40, "sex": "male", "weight_kg": 70}
    with pytest.raises(RuntimeError):
        recompute_path(g, ans)


# ------------------------------------------------------------ consent
def test_no_questions_without_consent():
    s = IntakeSession(G, RULES)
    assert s.pending == "consent" and s.consent_at is None
    with pytest.raises(ConsentRequired):
        s.answer("age_years", 30)
    s.answer("consent", "decline")
    assert s.declined and s.pending is None and not s.complete and s.consent_at is None
    with pytest.raises(ConsentRequired):
        s.answer("age_years", 30)


def test_consent_timestamp_recorded_once():
    ticks = iter(range(100))
    from datetime import datetime, timedelta, timezone
    clock = lambda: datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=next(ticks))
    s = IntakeSession(G, RULES, clock=clock)
    s.answer("consent", "agree")
    t = s.consent_at
    assert t is not None
    s.answer("consent", "agree")
    assert s.consent_at == t


def test_withdrawing_consent_erases_answers():
    s = run_bank(G, RULES)
    s.answer("consent", "decline")
    assert s.answers == {"consent": "decline"} and s.consent_at is None


def test_consent_cannot_be_unsure_or_skipped():
    s = IntakeSession(G, RULES)
    for bad in (UNSURE, SKIPPED, None, "maybe"):
        with pytest.raises(ValueError):
            s.answer("consent", bad)


def test_cannot_answer_off_path_node():
    s = IntakeSession(G, RULES)
    s.answer("consent", "agree")
    with pytest.raises(ValueError):
        s.answer("cp_site", "centre")


# ------------------------------------------------------------ answer validation
@pytest.mark.parametrize("nid,val", [
    ("sex", "robot"), ("sex", ["male"]), ("allergies", []), ("allergies", ["none", "sulfa"]), ("allergies", ["x"]),
    ("allergies", ["sulfa", "sulfa"]), ("allergies", "sulfa"), ("age_years", "ten"), ("age_years", True),
    ("age_years", -1), ("age_years", 121), ("age_months", 12), ("weight_kg", 0), ("weight_kg", 301),
    ("cp_severity", 11), ("cp_severity", -1), ("cp_severity", 3.5), ("meds_list", "  "), ("meds_list", 5),
    ("pregnancy", "maybe"),
])
def test_invalid_answers_rejected(nid, val):
    with pytest.raises(ValueError):
        validate_answer(G.node(nid), val)


@pytest.mark.parametrize("nid,val", [
    ("sex", "female"), ("allergies", ["sulfa", "nsaids"]), ("allergies", ["none"]), ("age_years", 0),
    ("age_years", 120), ("weight_kg", 7.5), ("cp_severity", 0), ("cp_severity", 10), ("meds_list", "a, b"),
    ("pregnancy", "unsure"),
    ("sex", UNSURE), ("weight_kg", UNSURE), ("allergies", [UNSURE]), ("allergies", UNSURE), ("meds_list", UNSURE),
    ("sex", SKIPPED), ("weight_kg", SKIPPED), ("allergies", SKIPPED), ("cp_severity", SKIPPED),
])
def test_valid_answers_accepted(nid, val):
    validate_answer(G.node(nid), val)


def test_unsure_and_skipped_are_stored_distinctly_and_both_continue_the_flow():
    s = run_bank(G, RULES, {"weight_kg": UNSURE, "kidney": SKIPPED})
    assert s.answers["weight_kg"] == UNSURE and s.answers["kidney"] == SKIPPED and s.complete
    assert answer_label(G.node("weight_kg"), UNSURE) == "Not sure"
    assert answer_label(G.node("kidney"), SKIPPED) == "Skipped"
    assert answer_label(G.node("allergies"), [UNSURE]) == "Not sure"
    assert answer_label(G.node("cp_severity"), 7) == "7/10"
    assert answer_label(G.node("sex"), "female", "hi") == "महिला"
    lbl = answer_label(G.node("allergies"), ["sulfa", "nsaids"])
    assert lbl.startswith("Sulfa medicines") and "Pain or fever tablets" in lbl


def test_bank_is_valid_and_covers_every_node():
    assert set(BANK) == set(G.ids())
    for nid, v in BANK.items():
        validate_answer(G.node(nid), v)


def test_run_bank_rejects_stale_override():
    with pytest.raises(KeyError):
        run_bank(G, RULES, {"cp_site": "left"})          # chief complaint is fever, cp_site never asked
