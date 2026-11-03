"""Condition expression language shared by the question graph and the red-flag rules.

A condition is a one-key dict:
  {"equals": [node, value]}      list answers (multi_choice): value is one of the selected options
  {"in": [node, [values]]}       list answers: at least one selected option is in values
  {"gte": [node, n]} / {"lte": [node, n]}   numeric answers only; "unsure"/skipped never compare true
  {"all": [cond, ...]} / {"any": [cond, ...]} / {"not": cond}
  {"regionsAny": [node, [regions]]}   body_map answers: at least one listed region is selected
  {"regionsAll": [node, [regions]]}   body_map answers: every listed region is selected
  {"answered": node}             a real answer, including "unsure"
  {"unanswered": node}           never asked, or skipped
"Not sure" is a real answer (answered=True) and never equals a concrete value. Skipped is not an answer.
"""
from typing import Any, Iterator

UNSURE = "unsure"
SKIPPED = "__skipped__"

_LEAF_ARGS = {"equals", "in", "gte", "lte", "regionsAny", "regionsAll"}
_NODE_ONLY = {"answered", "unanswered"}
_LISTS = {"all", "any"}


def check_condition(cond: Any) -> None:
    """Raise ValueError if cond is not well-formed."""
    if not isinstance(cond, dict) or len(cond) != 1:
        raise ValueError(f"condition must be a one-key object, got {cond!r}")
    (op, arg), = cond.items()
    if op in _LEAF_ARGS:
        if not (isinstance(arg, list) and len(arg) == 2 and isinstance(arg[0], str)):
            raise ValueError(f"{op} needs [node, value], got {arg!r}")
        if op in ("in", "regionsAny", "regionsAll") and not (isinstance(arg[1], list) and arg[1]):
            raise ValueError(f"{op} needs a non-empty list of values")
        if op in ("gte", "lte") and (isinstance(arg[1], bool) or not isinstance(arg[1], (int, float))):
            raise ValueError(f"{op} needs a number")
    elif op in _NODE_ONLY:
        if not isinstance(arg, str):
            raise ValueError(f"{op} needs a node id")
    elif op in _LISTS:
        if not isinstance(arg, list) or not arg:
            raise ValueError(f"{op} needs a non-empty list")
        for c in arg:
            check_condition(c)
    elif op == "not":
        check_condition(arg)
    else:
        raise ValueError(f"unknown operator {op!r}")


def referenced_nodes(cond: dict) -> list[str]:
    """Node ids a condition reads, in first-seen order."""
    out: list[str] = []

    def walk(c: dict) -> Iterator[str]:
        (op, arg), = c.items()
        if op in _LEAF_ARGS:
            yield arg[0]
        elif op in _NODE_ONLY:
            yield arg
        elif op in _LISTS:
            for x in arg:
                yield from walk(x)
        else:
            yield from walk(arg)

    for n in walk(cond):
        if n not in out:
            out.append(n)
    return out


def is_answered(answers: dict, node: str) -> bool:
    return node in answers and answers[node] != SKIPPED


def is_unsure(value: Any) -> bool:
    return value == UNSURE or (isinstance(value, list) and UNSURE in value)


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def evaluate(cond: dict, answers: dict) -> bool:
    (op, arg), = cond.items()
    if op == "all":
        return all(evaluate(c, answers) for c in arg)
    if op == "any":
        return any(evaluate(c, answers) for c in arg)
    if op == "not":
        return not evaluate(arg, answers)
    if op == "answered":
        return is_answered(answers, arg)
    if op == "unanswered":
        return not is_answered(answers, arg)
    node, want = arg
    if not is_answered(answers, node):
        return False
    have = answers[node]
    if op == "equals":
        return want in have if isinstance(have, list) else have == want
    if op in ("regionsAny", "regionsAll"):
        sel = have.get("regions", []) if isinstance(have, dict) else []
        return any(r in sel for r in want) if op == "regionsAny" else all(r in sel for r in want)
    if op == "in":
        return any(h in want for h in have) if isinstance(have, list) else have in want
    if not _num(have):
        return False
    return have >= want if op == "gte" else have <= want
