"""Region-driven follow-up questions (chest / abdomen / head): branches, kiosk length cap, graph validation,
and the guarantee that red flags are identical with and without them."""
import copy
import itertools
import json

import pytest

from intake import bodymap
from intake.bodymap import make_answer
from intake.conditions import SKIPPED, UNSURE, referenced_nodes
from intake.engine import validate_graph
from intake.models import END, GRAPH_PATH, LANGS, TRANSLATION_STATUS, Graph, load_graph
from intake.redflags import load_rules
from intake.session import IntakeSession
from intake.synthetic import PATIENTS, run_bank

G = load_graph()
RULES = load_rules()
NEW = ["cpx_episode_len", "cpx_arm_numb", "cpx_skin", "abx_meals", "abx_urine_stool", "hdx_eyes_nose", "hdx_neck_tight"]
SITE = {"chest_pain": "cp_site", "abdominal_pain": "ab_site", "headache": "hd_site"}


def extras(complaint, site):
    s = run_bank(G, RULES, {"chief_complaint": complaint, SITE[complaint]: site})
    return [n for n in s.path if n in NEW], s


def m(*regions):
    return make_answer(list(regions), "map")


# ------------------------------------------------------------ each region branch
CASES = [
    ("chest_pain", m("chest_left"), ["cpx_episode_len", "cpx_arm_numb"]),
    ("chest_pain", m("chest_center"), ["cpx_episode_len", "cpx_arm_numb"]),
    ("chest_pain", m("chest_right"), ["cpx_skin"]),
    ("chest_pain", m("chest_left", "chest_right"), ["cpx_episode_len", "cpx_arm_numb"]),   # first matching rule wins
    ("chest_pain", m("upper_abdomen_left"), []),
    ("chest_pain", UNSURE, []),
    ("chest_pain", SKIPPED, []),
    ("chest_pain", make_answer([], "list", "tell_doctor"), []),
    ("abdominal_pain", m("upper_abdomen_right"), ["abx_meals"]),
    ("abdominal_pain", m("upper_abdomen_left"), ["abx_meals"]),
    ("abdominal_pain", m("upper_abdomen_center"), ["abx_meals"]),
    ("abdominal_pain", m("lower_abdomen_right"), ["abx_urine_stool"]),
    ("abdominal_pain", m("lower_abdomen_center"), ["abx_urine_stool"]),
    ("abdominal_pain", m("pelvic_area"), ["abx_urine_stool"]),
    ("abdominal_pain", m("upper_abdomen_right", "lower_abdomen_left"), ["abx_meals"]),
    ("abdominal_pain", m("mid_back"), []),
    ("abdominal_pain", UNSURE, []),
    ("abdominal_pain", SKIPPED, []),
    ("headache", m("head_front"), ["hdx_eyes_nose"]),
    ("headache", m("head_back"), ["hdx_neck_tight"]),
    ("headache", m("neck_back"), ["hdx_neck_tight"]),
    ("headache", m("head_front", "head_back"), ["hdx_eyes_nose"]),
    ("headache", m("jaw_front"), []),
    ("headache", UNSURE, []),
    ("headache", SKIPPED, []),
]


@pytest.mark.parametrize("complaint,site,expected", CASES)
def test_region_branch(complaint, site, expected):
    got, s = extras(complaint, site)
    assert got == expected and s.complete


def test_other_complaints_never_get_followups():
    for cc in ("fever", "cough_breath", "other"):
        assert not [n for n in run_bank(G, RULES, {"chief_complaint": cc}).path if n in NEW]


def test_followups_come_after_associated_symptoms_in_socrates_order():
    for cc, assoc, after in (("chest_pain", "cp_assoc", "cp_course"), ("abdominal_pain", "ab_assoc", "ab_pattern"),
                             ("headache", "hd_assoc", "hd_course")):
        s = run_bank(G, RULES, {"chief_complaint": cc, SITE[cc]: m({"chest_pain": "chest_center", "abdominal_pain": "pelvic_area",
                                                                    "headache": "head_front"}[cc])})
        p = s.path
        i = p.index(assoc)
        assert p[i + 1] in NEW and p.index(after) > max(p.index(n) for n in NEW if n in p)


def test_at_most_two_extra_questions_for_any_region_selection():
    ids = bodymap.region_ids()
    selections = [[r] for r in ids] + [list(c) for c in itertools.combinations(
        ["chest_left", "chest_right", "upper_abdomen_left", "lower_abdomen_left", "head_front", "head_back", "neck_back"], 2)]
    for cc, site in SITE.items():
        for sel in selections:
            got, s = extras(cc, make_answer(sel[:3], "list"))
            assert len(got) <= 2, (cc, sel, got)


# ------------------------------------------------------------ node metadata
def test_new_nodes_are_unsourced_machine_drafted_and_translated():
    for nid in NEW:
        n = G.node(nid)
        assert n.source is None and n.sourceChecked is False and n.redFlagRefs == [], nid
        assert n.translationStatus == TRANSLATION_STATUS and n.section == "module" and n.socrates == "associated"
        assert n.shortLabel
        for lang in LANGS:
            assert getattr(n.text, lang).strip() and all(getattr(o, lang).strip() for o in n.options)
        assert n.text.hi != n.text.en and n.text.mr != n.text.en


def test_existing_node_ids_still_present():
    ids = set(G.ids())
    for old in ("cp_site", "cp_onset", "cp_char", "body_map_radiation", "cp_assoc", "cp_course", "cp_exac", "cp_relieve", "cp_severity",
                "ab_site", "ab_assoc", "ab_pattern", "hd_site", "hd_assoc", "hd_course", "danger_signs", "hx_similar"):
        assert old in ids


# ------------------------------------------------------------ validate_graph covers the new nodes
@pytest.fixture()
def raw():
    return json.loads(GRAPH_PATH.read_text(encoding="utf-8"))


def mutated(raw, fn):
    r = copy.deepcopy(raw)
    fn({n["id"]: n for n in r["nodes"]})
    return Graph.model_validate(r)


def test_shipped_graph_with_new_nodes_is_valid():
    assert validate_graph(G, {r.id for r in RULES}) == []


def test_validate_catches_cycle_through_a_new_node(raw):
    g = mutated(raw, lambda N: N["cpx_arm_numb"]["next"].update(default="cp_assoc"))
    assert any("cycle" in e for e in validate_graph(g))


def test_validate_catches_unreachable_new_node(raw):
    g = mutated(raw, lambda N: N["cp_assoc"]["next"].update(rules=[]))
    errs = validate_graph(g)
    assert any("unreachable node 'cpx_episode_len'" in e for e in errs) and any("'cpx_skin'" in e for e in errs)


def test_validate_catches_missing_translation_on_a_new_node(raw):
    def f(N):
        N["abx_meals"]["text"]["mr"] = ""
        N["abx_meals"]["options"][0]["hi"] = " "
    errs = validate_graph(mutated(raw, f))
    assert "abx_meals: missing mr text" in errs and "abx_meals.before: missing hi option text" in errs


def test_validate_catches_unknown_region_and_bad_target(raw):
    g = mutated(raw, lambda N: N["hd_assoc"]["next"]["rules"][0].update(goto="nope"))
    assert any("missing target 'nope'" in e for e in validate_graph(g))
    g = mutated(raw, lambda N: N["hd_assoc"]["next"]["rules"][0]["if"]["regionsAny"].__setitem__(1, ["head_nowhere"]))
    assert any("unknown region 'head_nowhere'" in e for e in validate_graph(g))


def test_validate_rejects_checked_without_source(raw):
    g = mutated(raw, lambda N: N["cpx_skin"].update(sourceChecked=True))
    assert any("cpx_skin: sourceChecked is true but there is no source" in e for e in validate_graph(g))


# ------------------------------------------------------------ red flags do not depend on the new nodes
def baseline_graph() -> Graph:
    """The same graph with the 7 region follow-ups removed and their edges bypassed."""
    r = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    by = {n["id"]: n for n in r["nodes"]}

    def skip(t):
        while t in NEW:
            t = by[t]["next"]["default"]
        return t
    r["nodes"] = [n for n in r["nodes"] if n["id"] not in NEW]
    for n in r["nodes"]:
        n["next"]["rules"] = [x for x in n["next"]["rules"] if x["goto"] not in NEW]
        n["next"]["default"] = skip(n["next"]["default"])
    return Graph.model_validate(r)


def fired(s):
    return [(t.ruleId, t.severity, json.dumps(t.triggeredBy, sort_keys=True)) for t in s.red_flags]


def replay_without_new(full: IntakeSession, base: Graph) -> IntakeSession:
    b = IntakeSession(base, RULES, language=full.language)
    while b.pending:
        b.answer(b.pending, full.answers[b.pending])        # KeyError here = the new nodes changed the old path
    return b


def test_rules_never_read_new_nodes():
    for r in RULES:
        assert not set(referenced_nodes(r.condition)) & set(NEW), r.id


def test_baseline_graph_is_valid_and_smaller():
    b = baseline_graph()
    assert validate_graph(b) == [] and len(b.nodes) == len(G.nodes) - len(NEW)


def scenarios():
    sites = {"chest_pain": [m("chest_left"), m("chest_center"), m("chest_right"), UNSURE, SKIPPED, m("chest_left", "chest_right")],
             "abdominal_pain": [m("upper_abdomen_left"), m("pelvic_area"), m("upper_abdomen_right", "lower_abdomen_left"), UNSURE],
             "headache": [m("head_front"), m("head_back"), m("neck_back"), UNSURE, SKIPPED]}
    rad = [make_answer([], "list", "none"), m("jaw_front"), m("upper_arm_left"), UNSURE]
    assoc = {"chest_pain": [["none"], ["sweating"], ["sweating", "nausea"]], "abdominal_pain": [["none"], ["vomiting"]],
             "headache": [["none"], ["neck_stiffness", "fever"], ["light"]]}
    for cc, site_vals in sites.items():
        for site, rd, a in itertools.product(site_vals, rad, assoc[cc]):
            ov = {"chief_complaint": cc, SITE[cc]: site, "body_map_radiation": rd, {"chest_pain": "cp_assoc", "abdominal_pain": "ab_assoc",
                  "headache": "hd_assoc"}[cc]: a}
            for extra in ({}, {"danger_signs": ["vomit_blood"]}, {"hd_onset": "sudden", "hd_severity": 9, "hd_worst": "yes"} if cc == "headache" else {}):
                yield {**ov, **extra}


@pytest.mark.parametrize("new_answer", ["plain", UNSURE, SKIPPED])
def test_red_flags_identical_with_and_without_new_nodes(new_answer):
    base = baseline_graph()
    seen_flags = set()
    n = 0
    for ov in scenarios():
        ov = {**ov, **{k: ("no" if new_answer == "plain" else new_answer) for k in NEW if G.node(k).type == "yes_no_unsure"},
              "cpx_episode_len": "over_30" if new_answer == "plain" else new_answer,
              "abx_meals": "after" if new_answer == "plain" else new_answer}
        full = run_bank(G, RULES, ov, allow_unused=True)
        b = replay_without_new(full, base)
        assert fired(full) == fired(b), ov
        assert [x for x in full.path if x not in NEW] == b.path
        seen_flags |= {f[0] for f in fired(full)}
        n += 1
    assert n > 100 and {"RF_CHEST_PAIN_RADIATION_SWEATING", "RF_VOMITING_BLOOD_OR_BLACK_STOOL", "RF_FEVER_NECK_STIFFNESS"} <= seen_flags


def test_red_flags_identical_for_the_three_demo_patients():
    base = baseline_graph()
    for name, ov in PATIENTS.items():
        full = run_bank(G, RULES, ov, allow_unused=True)
        assert fired(full) == fired(replay_without_new(full, base)), name


def test_red_flag_fires_the_moment_the_triggering_answer_is_given():
    """Red flags are re-evaluated after every answer, before any follow-up is asked."""
    s = run_bank(G, RULES, {"chief_complaint": "chest_pain", "cp_site": m("chest_center")}, stop_at="cp_assoc")
    assert s.red_flags == []
    s.answer("body_map_radiation", m("jaw_front"))
    assert [t.ruleId for t in s.red_flags] == ["RF_CHEST_PAIN_RADIATION_SWEATING"] and s.pending == "cp_assoc"
    assert s.red_flags[0].triggeredBy["cp_site"]["regions"] == ["chest_center"]


def test_followup_is_shown_on_the_kiosk_in_hindi(tmp_path, monkeypatch):
    from pathlib import Path as P
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("INTAKE_DATA_DIR", str(tmp_path))
    s = run_bank(G, RULES, {"chief_complaint": "chest_pain", "cp_site": m("chest_center")}, stop_at="cpx_episode_len")
    at = AppTest.from_file(str(P(__file__).resolve().parent.parent / "intake" / "ui" / "patient.py"), default_timeout=20)
    at.session_state["sess"], at.session_state["stage"], at.session_state["view"] = s, "flow", None
    at.run()
    assert at.header[0].value == "When the pain comes, how long does it last?"
    at.radio[0].set_value("hi").run()
    assert at.header[0].value == G.node("cpx_episode_len").text.hi and not at.exception
