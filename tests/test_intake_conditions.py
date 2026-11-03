import pytest

from intake.conditions import SKIPPED, UNSURE, check_condition, evaluate, referenced_nodes

A = {"s": "yes", "n": 7, "m": ["a", "b"], "u": UNSURE, "mu": [UNSURE], "sk": SKIPPED}


@pytest.mark.parametrize("cond,expected", [
    ({"equals": ["s", "yes"]}, True), ({"equals": ["s", "no"]}, False),
    ({"equals": ["m", "a"]}, True), ({"equals": ["m", "z"]}, False),          # list answer: membership
    ({"in": ["s", ["yes", "no"]]}, True), ({"in": ["s", ["no"]]}, False),
    ({"in": ["m", ["z", "b"]]}, True), ({"in": ["m", ["z"]]}, False),
    ({"gte": ["n", 7]}, True), ({"gte": ["n", 8]}, False),
    ({"lte": ["n", 7]}, True), ({"lte": ["n", 6]}, False),
    ({"all": [{"equals": ["s", "yes"]}, {"gte": ["n", 1]}]}, True),
    ({"all": [{"equals": ["s", "yes"]}, {"gte": ["n", 9]}]}, False),
    ({"any": [{"equals": ["s", "no"]}, {"gte": ["n", 1]}]}, True),
    ({"any": [{"equals": ["s", "no"]}, {"gte": ["n", 9]}]}, False),
    ({"not": {"equals": ["s", "no"]}}, True), ({"not": {"equals": ["s", "yes"]}}, False),
    ({"answered": "s"}, True), ({"answered": "missing"}, False),
    ({"unanswered": "missing"}, True), ({"unanswered": "s"}, False),
])
def test_operators(cond, expected):
    assert evaluate(cond, A) is expected


def test_unsure_is_an_answer_but_never_equals_a_value_or_compares():
    assert evaluate({"answered": "u"}, A) and not evaluate({"unanswered": "u"}, A)
    assert evaluate({"answered": "mu"}, A)
    assert not evaluate({"equals": ["u", "yes"]}, A)
    assert not evaluate({"gte": ["u", 0]}, A) and not evaluate({"lte": ["u", 999]}, A)
    assert evaluate({"equals": ["u", UNSURE]}, A) and evaluate({"equals": ["mu", UNSURE]}, A)


def test_skipped_is_unanswered_and_matches_nothing():
    assert evaluate({"unanswered": "sk"}, A) and not evaluate({"answered": "sk"}, A)
    assert not evaluate({"equals": ["sk", SKIPPED]}, A)
    assert not evaluate({"in": ["sk", [SKIPPED]]}, A)
    assert evaluate({"not": {"equals": ["sk", "yes"]}}, A)


def test_unsure_and_skipped_differ():
    assert evaluate({"answered": "u"}, A) != evaluate({"answered": "sk"}, A)


def test_numeric_ops_reject_bool_and_text():
    assert not evaluate({"gte": ["s", 0]}, A)
    assert not evaluate({"gte": ["b", 0]}, {"b": True})


@pytest.mark.parametrize("bad", [
    [], {}, {"equals": ["x"]}, {"equals": "x"}, {"in": ["x", "notalist"]}, {"gte": ["x", "5"]},
    {"gte": ["x", True]}, {"all": []}, {"any": {}}, {"answered": 3}, {"nope": ["x", 1]}, {"equals": ["x", 1], "not": {}},
])
def test_malformed_conditions_rejected(bad):
    with pytest.raises(ValueError):
        check_condition(bad)


def test_referenced_nodes():
    c = {"all": [{"equals": ["a", 1]}, {"not": {"any": [{"gte": ["b", 1]}, {"answered": "a"}, {"unanswered": "c"}]}}]}
    assert referenced_nodes(c) == ["a", "b", "c"]
