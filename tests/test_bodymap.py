import json
import re
from pathlib import Path

import pytest

from intake import bodymap as bm
from intake.bodymap import centroid, hit_test, make_answer, point_in_polygon, render_svg
from intake.conditions import SKIPPED, UNSURE, check_condition, evaluate, referenced_nodes
from intake.engine import validate_answer, validate_graph
from intake.models import TRANSLATION_STATUS, load_graph
from intake.redflags import load_rules
from intake.summary import apply_doctor_edits, body_diagram_svgs, build_summary, render_text
from intake.synthetic import BANK, run_bank

G, RULES = load_graph(), load_rules()
CAT = bm.catalog()
ALL = [r.id for r in CAT.regions]
SITE_NODES = ["fev_site", "cb_site", "ab_site", "hd_site", "cp_site"]


# ------------------------------------------------------------ catalog
def test_region_ids_unique_and_translated():
    assert len(ALL) == len(set(ALL))
    for r in CAT.regions:
        assert re.fullmatch(r"[a-z_]+", r.id)
        assert r.en.strip() and r.hi.strip() and r.mr.strip(), r.id
        assert r.hi != r.en and r.mr != r.en, r.id                       # not copy-pasted English
        assert r.translationStatus == TRANSLATION_STATUS, r.id
    assert CAT.translationStatus == TRANSLATION_STATUS
    for side in ("right", "left"):
        assert all(CAT.sideLabels[side][l].strip() for l in ("en", "hi", "mr"))
    assert CAT.sideLabels["right"]["en"] == "Patient's right" and CAT.sideLabels["left"]["en"] == "Patient's left"


def test_spec_example_regions_exist():
    need = ["head_front", "neck_front", "chest_right", "chest_left", "chest_center", "upper_abdomen_right",
            "upper_abdomen_center", "upper_abdomen_left", "lower_abdomen_right", "lower_abdomen_center",
            "lower_abdomen_left", "pelvic_area", "shoulder_right", "shoulder_left", "upper_arm_right", "upper_arm_left",
            "forearm_right", "forearm_left", "hand_right", "hand_left", "thigh_right", "thigh_left", "knee_right",
            "knee_left", "shin_right", "shin_left", "foot_right", "foot_left", "head_back", "neck_back",
            "upper_back_right", "upper_back_left", "mid_back", "lower_back_right", "lower_back_left",
            "buttock_right", "buttock_left", "calf_right", "calf_left"]
    assert set(need) <= set(ALL)


def test_every_side_pair_exists_and_names_match_side_field():
    for r in CAT.regions:
        if r.id.endswith("_right"):
            assert r.side == "right" and r.id[:-6] + "_left" in ALL
        elif r.id.endswith("_left"):
            assert r.side == "left"
        else:
            assert r.side == "center"


def test_polygons_are_valid_convex_inside_the_box():
    w, h = CAT.viewBox
    for r in CAT.regions:
        pts = r.polygon
        assert len(pts) >= 3 and all(0 <= x <= w and 0 <= y <= h for x, y in pts), r.id
        cross = [(pts[(i + 1) % len(pts)][0] - pts[i][0]) * (pts[(i + 2) % len(pts)][1] - pts[(i + 1) % len(pts)][1])
                 - (pts[(i + 1) % len(pts)][1] - pts[i][1]) * (pts[(i + 2) % len(pts)][0] - pts[(i + 1) % len(pts)][0])
                 for i in range(len(pts))]
        assert all(c >= 0 for c in cross) or all(c <= 0 for c in cross), f"{r.id} not convex"


# ------------------------------------------------------------ hit-testing
@pytest.mark.parametrize("rid", ALL)
def test_each_region_is_hit_at_its_centroid(rid):
    r = bm.region(rid)
    x, y = centroid(r.polygon)
    assert hit_test(r.view, x, y) == rid
    other = "back" if r.view == "front" else "front"
    assert hit_test(other, x, y) != rid                                   # a region exists on one view only


def test_regions_do_not_overlap():
    for view in ("front", "back"):
        rs = bm.regions_in_view(view)
        for x in range(0, 200):
            for y in range(0, 424):
                assert sum(point_in_polygon(x + .5, y + .5, r.polygon) for r in rs) <= 1, (view, x, y)


def test_outside_the_body_is_no_region_and_slop_snaps_to_nearest():
    assert hit_test("front", 5, 5) is None and hit_test("front", 100, 421) is None
    gap = (63, 130)                                                       # between chest_right and the upper arm
    assert hit_test("front", *gap) is None
    assert hit_test("front", *gap, slop=4) in ("chest_right", "upper_arm_right")
    assert hit_test("front", 5, 5, slop=4) is None                        # far away stays a miss


def test_point_in_polygon_basics():
    sq = [[0, 0], [10, 0], [10, 10], [0, 10]]
    assert point_in_polygon(5, 5, sq) and not point_in_polygon(11, 5, sq) and not point_in_polygon(5, -1, sq)


# ------------------------------------------------------------ orientation: right/left are the PATIENT's
@pytest.mark.parametrize("r", CAT.regions, ids=lambda r: r.id)
def test_side_matches_screen_position(r):
    cx, _ = centroid(r.polygon)
    if r.side == "center":
        assert abs(cx - 100) < 1
    elif r.view == "front":      # patient's right is on the VIEWER's left
        assert (cx < 100) == (r.side == "right")
    else:                        # back view: patient's right is on the viewer's right
        assert (cx > 100) == (r.side == "right")


def test_concrete_orientation_points():
    assert hit_test("front", 76, 125) == "chest_right" and hit_test("front", 124, 125) == "chest_left"
    assert hit_test("back", 124, 120) == "upper_back_right" and hit_test("back", 76, 120) == "upper_back_left"
    assert hit_test("front", 48, 130) == "upper_arm_right" and hit_test("back", 152, 130) == "upper_arm_back_right"


def test_diagram_labels_patients_right_and_left_on_correct_edges():
    def labels(svg):
        import html
        return [(x, html.unescape(t)) for x, t in re.findall(r'<text x="([\d.]+)"[^>]*>([^<]+)</text>', svg)]
    (lx, lt), (rx, rt) = labels(render_svg("front"))
    assert float(lx) < float(rx) and (lt, rt) == ("Patient's right", "Patient's left")
    (lx, lt), (rx, rt) = labels(render_svg("back"))
    assert (lt, rt) == ("Patient's left", "Patient's right")
    assert labels(render_svg("front", lang="hi"))[0][1] == "मरीज़ का दायाँ"
    assert labels(render_svg("front", lang="mr"))[0][1] == "रुग्णाचा उजवा"


def test_svg_is_self_contained_plain_shapes():
    svg = render_svg("front", {"sel": ["chest_left"]})
    assert svg.count("<polygon") == len(bm.regions_in_view("front")) and "<image" not in svg
    assert not re.search(r"(href|src)=|url\(|https?://(?!www\.w3\.org)", svg)
    assert '#d62828' in svg                                                # selected region highlighted




# ------------------------------------------------------------ answers: map and list are interchangeable
def test_map_and_list_store_identical_values():
    picks = ["upper_abdomen_left", "chest_center", "neck_back"]            # includes both views
    a_map = make_answer(picks, "map")
    a_list = make_answer(list(reversed(picks)), "list")                    # different tap order, other input
    assert {k: v for k, v in a_map.items() if k != "inputMode"} == {k: v for k, v in a_list.items() if k != "inputMode"}
    assert a_map["regions"] == ["chest_center", "upper_abdomen_left", "neck_back"] and a_map["view"] == "front"
    assert {a_map["inputMode"], a_list["inputMode"]} == {"map", "list"}
    assert make_answer(["neck_back", "chest_center"], "map")["view"] == "front"   # view of the first region in catalog order
    assert make_answer(["calf_left"], "map")["view"] == "back"
    node = G.node("ab_site")
    validate_answer(node, a_map); validate_answer(node, a_list)


def test_map_and_list_give_identical_records():
    recs = {}
    for mode in ("map", "list"):
        ans = make_answer(["chest_left", "chest_center"], mode)
        recs[mode] = run_bank(G, RULES, {"chief_complaint": "chest_pain", "cp_site": ans}).finish()
    sm, sl = (recs[m].socrates["site"].model_dump() for m in ("map", "list"))
    assert {k: v for k, v in sm.items() if k != "inputMode"} == {k: v for k, v in sl.items() if k != "inputMode"}
    assert sm["inputMode"] == "map" and sl["inputMode"] == "list"
    assert [t.ruleId for t in recs["map"].redFlags] == [t.ruleId for t in recs["list"].redFlags]


@pytest.mark.parametrize("bad", [
    {"regions": ["chest_left"], "view": "back", "inputMode": "map"},                    # wrong view for the regions
    {"regions": ["upper_abdomen_left", "chest_center"], "view": "front", "inputMode": "map"},   # not canonical order
    {"regions": ["chest_left"], "view": "front"},                                       # missing inputMode
    {"regions": ["chest_left"], "view": "front", "inputMode": "tap"},
    {"regions": [], "view": "front", "inputMode": "map"},                               # nothing chosen
    {"regions": ["chest_left", "chest_center", "chest_right", "pelvic_area"], "view": "front", "inputMode": "map"},  # > max (3)
    {"regions": ["nose"], "view": "front", "inputMode": "map"},
    {"regions": ["chest_left"], "view": "front", "inputMode": "map", "special": "tell_doctor"},
    {"regions": [], "view": "front", "inputMode": "map", "special": "none"},            # cp_site has no 'none' option
    {"regions": ["chest_left", "chest_left"], "view": "front", "inputMode": "map"},
    "chest_left", ["chest_left"], 3,
])
def test_invalid_body_map_answers_rejected(bad):
    with pytest.raises(ValueError):
        validate_answer(G.node("cp_site"), bad)


def test_specials_and_unsure_accepted():
    validate_answer(G.node("cp_site"), make_answer([], "list", "tell_doctor"))
    validate_answer(G.node("cp_site"), UNSURE)
    validate_answer(G.node("cp_site"), SKIPPED)
    validate_answer(G.node("fev_site"), make_answer([], "list", "none"))
    validate_answer(G.node("body_map_radiation"), make_answer([], "map", "none"))
    assert make_answer([], "list", "tell_doctor") == {"regions": [], "view": "front", "inputMode": "list", "special": "tell_doctor"}
    with pytest.raises(ValueError):
        make_answer(["nope"], "map")


# ------------------------------------------------------------ graph integration
def test_every_module_has_a_body_map_site_and_radiation_node():
    for nid in SITE_NODES:
        n = G.node(nid)
        assert n.type == "body_map" and n.socrates == "site" and n.maxSelections >= 1
        assert {"unsure", "tell_doctor"} <= {o.id for o in n.options}
        assert n.id in G.ids()
    r = G.node("body_map_radiation")
    assert r.type == "body_map" and r.socrates == "radiation" and {o.id for o in r.options} == {"unsure", "tell_doctor", "none"}
    assert not {"cp_radiation", "ab_radiation"} & set(G.ids())
    for cc, site in [("fever", "fev_site"), ("cough_breath", "cb_site"), ("abdominal_pain", "ab_site"),
                     ("headache", "hd_site"), ("chest_pain", "cp_site")]:
        assert site in run_bank(G, RULES, {"chief_complaint": cc}).path
    assert "body_map_radiation" in run_bank(G, RULES, {"chief_complaint": "chest_pain"}).path
    assert "body_map_radiation" in run_bank(G, RULES, {"chief_complaint": "abdominal_pain"}).path
    assert "body_map_radiation" not in run_bank(G, RULES, {"chief_complaint": "headache"}).path


def test_node_text_and_special_options_translated():
    for nid in SITE_NODES + ["body_map_radiation"]:
        n = G.node(nid)
        assert n.text.hi != n.text.en and n.text.mr != n.text.en
        assert all(o.hi != o.en and o.mr != o.en for o in n.options)
        assert n.translationStatus == TRANSLATION_STATUS


def test_validate_graph_checks_regions_in_conditions():
    import copy
    raw = json.loads((Path(bm.__file__).parent.parent / "data" / "intake_graph.json").read_text())
    def mk(cond):
        r = copy.deepcopy(raw)
        next(n for n in r["nodes"] if n["id"] == "weight_kg")["next"] = {"rules": [{"if": cond, "goto": "allergies"}], "default": "allergies"}
        from intake.models import Graph
        return Graph.model_validate(r)
    assert validate_graph(mk({"regionsAny": ["cp_site", ["chest_left"]]})) == []
    assert any("unknown region 'nose'" in e for e in validate_graph(mk({"regionsAny": ["cp_site", ["nose"]]})))
    assert any("non-body_map" in e for e in validate_graph(mk({"regionsAny": ["sex", ["chest_left"]]})))


def test_body_map_schema_rules():
    import copy
    from intake.models import Graph
    raw = json.loads((Path(bm.__file__).parent.parent / "data" / "intake_graph.json").read_text())
    for mutate in (lambda n: n.pop("maxSelections"), lambda n: n.update(options=[]),
                   lambda n: n.update(options=[o for o in n["options"] if o["id"] != "tell_doctor"]),
                   lambda n: n.update(options=n["options"] + [{"id": "x", "en": "x", "hi": "x", "mr": "x"}])):
        r = copy.deepcopy(raw)
        mutate(next(n for n in r["nodes"] if n["id"] == "cp_site"))
        with pytest.raises(Exception):
            Graph.model_validate(r)
    r = copy.deepcopy(raw)
    next(n for n in r["nodes"] if n["id"] == "sex")["maxSelections"] = 2
    with pytest.raises(Exception):
        Graph.model_validate(r)


# ------------------------------------------------------------ condition language
A = {"m": make_answer(["chest_left", "chest_center"], "map"), "t": make_answer([], "list", "tell_doctor"), "u": UNSURE, "s": SKIPPED}


@pytest.mark.parametrize("cond,expected", [
    ({"regionsAny": ["m", ["chest_left"]]}, True), ({"regionsAny": ["m", ["chest_right", "chest_center"]]}, True),
    ({"regionsAny": ["m", ["chest_right"]]}, False),
    ({"regionsAll": ["m", ["chest_left", "chest_center"]]}, True), ({"regionsAll": ["m", ["chest_left", "chest_right"]]}, False),
    ({"regionsAny": ["t", ["chest_left"]]}, False), ({"regionsAll": ["t", ["chest_left"]]}, False),
    ({"regionsAny": ["u", ["chest_left"]]}, False), ({"regionsAny": ["s", ["chest_left"]]}, False),
    ({"regionsAny": ["missing", ["chest_left"]]}, False),
    ({"not": {"regionsAny": ["m", ["chest_right"]]}}, True), ({"answered": "t"}, True), ({"answered": "u"}, True),
])
def test_region_operators(cond, expected):
    assert evaluate(cond, A) is expected


@pytest.mark.parametrize("bad", [{"regionsAny": ["m", []]}, {"regionsAll": ["m", "chest_left"]}, {"regionsAny": ["m"]},
                                 {"regionsAny": [3, ["a"]]}])
def test_malformed_region_conditions(bad):
    with pytest.raises(ValueError):
        check_condition(bad)
    assert referenced_nodes({"all": [{"regionsAny": ["a", ["x"]]}, {"regionsAll": ["b", ["y"]]}]}) == ["a", "b"]


# ------------------------------------------------------------ red flag with regions + recompute on change/removal
CHEST = {"chief_complaint": "chest_pain"}


def test_region_rule_positive_and_negative_end_to_end():
    pos = run_bank(G, RULES, {**CHEST, "cp_site": make_answer(["chest_left"], "map"),
                              "body_map_radiation": make_answer(["upper_arm_left"], "map")})
    assert [t.ruleId for t in pos.red_flags] == ["RF_CHEST_PAIN_RADIATION_SWEATING"] and pos.red_flags[0].draft
    neg = run_bank(G, RULES, {**CHEST, "cp_site": make_answer(["chest_left"], "map"),
                              "body_map_radiation": make_answer([], "map", "none")})
    assert neg.red_flags == []


def test_removing_a_selection_recomputes_flags_and_keeps_path_valid():
    s = run_bank(G, RULES, {**CHEST, "cp_site": make_answer(["chest_left", "chest_right"], "map"),
                            "body_map_radiation": make_answer(["jaw_front"], "map")})
    assert s.red_flags and s.complete
    path = list(s.path)
    s.answer("cp_site", make_answer(["chest_right"], "map"))                   # untap chest_left
    assert s.red_flags == [] and s.pending == "cpx_skin"                       # right chest asks the skin follow-up instead
    s.answer("cpx_skin", "no")
    assert s.pending == "cp_course"       # a changed branch re-asks what came after it (recompute_path drops answers off the old path)
    while s.pending:                      # re-answer the rest: the intake still completes, flags stay clear, and apart from the
        s.answer(s.pending, BANK[s.pending])   # region follow-ups the path is exactly what it was before the untap
    assert s.complete and s.red_flags == []
    assert [n for n in s.path if not n.startswith("cpx_")] == [n for n in path if not n.startswith("cpx_")]
    s.answer("cp_site", make_answer(["chest_left"], "list"))                   # tap it again, from the list
    assert [t.ruleId for t in s.red_flags] == ["RF_CHEST_PAIN_RADIATION_SWEATING"]
    s.answer("body_map_radiation", make_answer([], "map", "none"))
    assert s.red_flags == []


def test_changing_complaint_drops_the_body_map_answers():
    s = run_bank(G, RULES, {**CHEST, "cp_site": make_answer(["chest_left"], "map"),
                            "body_map_radiation": make_answer(["upper_arm_left"], "map")})
    s.answer("chief_complaint", "headache")
    assert "cp_site" not in s.answers and "body_map_radiation" not in s.answers and s.red_flags == []
    assert s.pending == "hd_site"
    rec = s.to_record()
    assert "radiation" not in rec.socrates and "site" not in rec.socrates


def test_abdominal_pain_keeps_radiation_answer_but_chest_rule_stays_quiet():
    s = run_bank(G, RULES, {"chief_complaint": "abdominal_pain", "body_map_radiation": make_answer(["upper_arm_left"], "map")})
    assert s.red_flags == [] and s.answers["body_map_radiation"]["regions"] == ["upper_arm_left"]


# ------------------------------------------------------------ record + doctor summary
def test_none_special_in_record():
    r = run_bank(G, RULES, {"chief_complaint": "fever", "fev_site": make_answer([], "list", "none")}).finish()
    assert r.socrates["site"].special == "none" and r.socrates["site"].regions == []
    assert "Site: No particular place" in render_text(build_summary(r))
    r = run_bank(G, RULES, {"chief_complaint": "chest_pain", "body_map_radiation": make_answer([], "list", "none")}).finish()
    assert "Radiation: Does not spread" in render_text(build_summary(r))



def test_record_site_and_radiation_shape():
    r = run_bank(G, RULES, {**CHEST, "cp_site": make_answer(["chest_center"], "map"),
                            "body_map_radiation": make_answer(["jaw_front", "upper_arm_left"], "list")}).finish()
    d = json.loads(r.model_dump_json())["socrates"]
    assert d["site"] == {"nodeId": "cp_site", "regions": ["chest_center"], "view": "front", "inputMode": "map", "special": None}
    assert d["radiation"] == {"nodeId": "body_map_radiation", "regions": ["jaw_front", "upper_arm_left"], "special": None}
    assert r.answers["cp_site"] == make_answer(["chest_center"], "map")                     # raw answer kept


@pytest.mark.parametrize("val,special", [(UNSURE, "unsure"), (SKIPPED, "skipped"),
                                          (make_answer([], "list", "tell_doctor"), "tell_doctor")])
def test_special_answers_in_record_and_summary(val, special):
    r = run_bank(G, RULES, {"chief_complaint": "headache", "hd_site": val}).finish()
    site = r.socrates["site"]
    assert site.special == special and site.regions == []
    assert "Site:" in render_text(build_summary(r))


def test_doctor_summary_names_regions_in_the_doctors_language():
    r = run_bank(G, RULES, {**CHEST, "cp_site": make_answer(["chest_left"], "map"),
                            "body_map_radiation": make_answer(["upper_arm_left"], "map")}).finish()
    f = lambda lang: {x.key: x.value for s in build_summary(r, lang).sections for x in s.fields}
    assert f("en")["socrates.site"].startswith("Chest, patient's left") and f("en")["socrates.radiation"] == "Upper arm, patient's left"
    assert "छाती" in f("hi")["socrates.site"] and "बाईं" in f("hi")["socrates.site"]
    assert "छाती" in f("mr")["socrates.site"] and "डावी" in f("mr")["socrates.site"]


def test_doctor_can_edit_site_text_with_tracking():
    r = run_bank(G, RULES, {**CHEST, "cp_site": make_answer(["chest_left"], "map")}).finish()
    from datetime import datetime
    r2 = apply_doctor_edits(r, {"socrates.site": "Left chest and left axilla"}, datetime(2026, 1, 1))
    assert r2.editedFields == ["socrates.site"] and r2.socrates["site"].regions == ["chest_left"]     # raw untouched


def test_optional_highlight_diagram():
    r = run_bank(G, RULES, {**CHEST, "cp_site": make_answer(["chest_left"], "map"),
                            "body_map_radiation": make_answer(["upper_back_right"], "map")}).finish()
    svgs = body_diagram_svgs(r)
    assert len(svgs) == 2 and bm.COLORS["site"] in svgs[0] and bm.COLORS["radiation"] in svgs[1]
    none = run_bank(G, RULES, {"chief_complaint": "headache", "hd_site": make_answer([], "list", "tell_doctor")}).finish()
    assert body_diagram_svgs(none) == []
