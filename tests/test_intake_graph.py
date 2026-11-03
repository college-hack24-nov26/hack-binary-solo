import copy
import json

import pytest

from intake.conditions import referenced_nodes
from intake.engine import longest_path, validate_graph
from intake.models import END, GRAPH_PATH, LANGS, TRANSLATION_STATUS, Graph, load_graph
from intake.redflags import load_rules


@pytest.fixture(scope="module")
def graph():
    return load_graph()


@pytest.fixture()
def raw():
    return json.loads(GRAPH_PATH.read_text(encoding="utf-8"))


def mk(raw, mutate):
    r = copy.deepcopy(raw)
    mutate(r)
    return Graph.model_validate(r)


def node(r, nid):
    return next(n for n in r["nodes"] if n["id"] == nid)


def test_shipped_graph_is_valid(graph):
    assert validate_graph(graph, {r.id for r in load_rules()}) == []


def test_every_node_and_option_has_en_hi_mr(graph):
    for n in graph.nodes:
        for lang in LANGS:
            assert getattr(n.text, lang).strip(), (n.id, lang)
            for o in n.options:
                assert getattr(o, lang).strip(), (n.id, o.id, lang)
        assert n.translationStatus == TRANSLATION_STATUS, n.id


def test_hindi_marathi_are_actually_translated(graph):
    """Catches copy-pasted English. Allowed to match only for identical-script words like 'Fever' units."""
    same = [(n.id, o.id) for n in graph.nodes for o in n.options if o.hi == o.en or o.mr == o.en]
    assert same == []
    assert [n.id for n in graph.nodes if n.text.hi == n.text.en or n.text.mr == n.text.en] == []


def test_patient_text_has_no_diagnosis_or_advice(graph):
    banned = ["you may have", "you probably have", "you might have", "you are suffering", "diagnos", "heart attack", "meningitis", "you should take",
              "take this", "treatment", "you need to", "emergency"]
    for n in graph.nodes:
        for t in [n.text.en, *[o.en for o in n.options]]:
            assert not any(b in t.lower() for b in banned), (n.id, t)
    for r in load_rules():
        assert not any(b in r.patientMessage.en.lower() for b in banned)


def test_question_cap_after_basics(graph):
    assert longest_path(graph, "chief_complaint") <= 15


def test_question_cap_on_real_paths():
    from intake.synthetic import PATIENTS, run_bank
    g, rules = load_graph(), load_rules()
    for cc in ["fever", "cough_breath", "abdominal_pain", "headache", "chest_pain", "other"]:
        s = run_bank(g, rules, {"chief_complaint": cc})
        assert 0 < s.questions_after_basics() <= 15, cc
    for p in PATIENTS.values():
        assert run_bank(g, rules, p).questions_after_basics() <= 15


def test_red_flag_refs_match_rules(graph):
    rules = load_rules()
    expected: dict[str, set] = {}
    for r in rules:
        for n in referenced_nodes(r.condition):
            expected.setdefault(n, set()).add(r.id)
    actual = {n.id: set(n.redFlagRefs) for n in graph.nodes if n.redFlagRefs}
    assert actual == expected


def test_yes_no_unsure_nodes_use_standard_options(graph):
    for n in graph.nodes:
        if n.type == "yes_no_unsure":
            assert [o.id for o in n.options] == ["yes", "no", "unsure"]


# ------------------------------------------------ validate_graph negative cases
def test_detects_missing_target(raw):
    g = mk(raw, lambda r: node(r, "sex")["next"].update(default="nowhere"))
    assert any("missing target 'nowhere'" in e for e in validate_graph(g))


def test_detects_cycle(raw):
    g = mk(raw, lambda r: node(r, "weight_kg")["next"].update(default="sex"))
    assert any("cycle" in e for e in validate_graph(g))


def test_detects_unreachable(raw):
    def m(r):
        n = copy.deepcopy(node(r, "hx_similar")); n["id"] = "orphan"; r["nodes"].append(n)
    assert any("unreachable node 'orphan'" in e for e in validate_graph(mk(raw, m)))


def test_detects_path_that_never_ends(raw):
    def m(r):  # two nodes that only point at each other (no END reachable)
        a = copy.deepcopy(node(r, "hx_similar")); a["id"] = "loop_a"; a["next"] = {"rules": [], "default": "loop_b"}
        b = copy.deepcopy(a); b["id"] = "loop_b"; b["next"] = {"rules": [], "default": "loop_a"}
        r["nodes"] += [a, b]
        node(r, "hx_similar")["next"]["rules"] = [{"if": {"equals": ["hx_similar", "yes"]}, "goto": "loop_a"}]
    errs = validate_graph(mk(raw, m))
    assert any("no path to END" in e for e in errs) and any("cycle" in e for e in errs)


@pytest.mark.parametrize("lang", LANGS)
def test_detects_missing_text_translation(raw, lang):
    g = mk(raw, lambda r: node(r, "sex")["text"].update({lang: "  "}))
    assert any(f"sex: missing {lang} text" in e for e in validate_graph(g))


@pytest.mark.parametrize("lang", LANGS)
def test_detects_missing_option_translation(raw, lang):
    g = mk(raw, lambda r: node(r, "sex")["options"][0].update({lang: ""}))
    assert any(f"sex.female: missing {lang} option text" in e for e in validate_graph(g))


def test_absent_translation_key_fails_schema(raw):
    def m(r): del node(r, "sex")["text"]["mr"]
    with pytest.raises(Exception):
        mk(raw, m)


def test_detects_unknown_option_in_condition(raw):
    g = mk(raw, lambda r: node(r, "sex")["next"].update(rules=[{"if": {"equals": ["sex", "martian"]}, "goto": "weight_kg"}]))
    assert any("no option 'martian'" in e for e in validate_graph(g))


def test_detects_condition_on_unknown_node(raw):
    g = mk(raw, lambda r: node(r, "sex")["next"].update(rules=[{"if": {"answered": "ghost"}, "goto": "weight_kg"}]))
    assert any("unknown node 'ghost'" in e for e in validate_graph(g))


def test_detects_unknown_red_flag_ref(raw):
    g = mk(raw, lambda r: node(r, "sex").update(redFlagRefs=["RF_NOPE"]))
    assert any("RF_NOPE" in e for e in validate_graph(g, {"RF_X"}))


def test_missing_start(raw):
    g = mk(raw, lambda r: r.update(start="zzz"))
    assert validate_graph(g)


@pytest.mark.parametrize("mutation", [
    lambda r: node(r, "sex").update(options=[]),                                   # choice without options
    lambda r: node(r, "weight_kg").update(options=node(r, "sex")["options"]),    # number with options
    lambda r: node(r, "weight_kg").pop("min"),                                     # number without range
    lambda r: node(r, "pregnancy").update(options=node(r, "pregnancy")["options"][:2]),
    lambda r: node(r, "sex").update(type="dropdown"),
    lambda r: node(r, "sex")["next"].update(rules=[{"if": {"bogus": 1}, "goto": END}]),
])
def test_schema_rejects_bad_nodes(raw, mutation):
    with pytest.raises(Exception):
        mk(raw, mutation)
