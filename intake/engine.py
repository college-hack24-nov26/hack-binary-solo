"""Pure functions over (graph, answers). No I/O, no clock, no network."""
from dataclasses import dataclass
from typing import Any, Optional

from . import bodymap
from .conditions import SKIPPED, UNSURE, evaluate, is_answered, is_unsure, referenced_nodes
from .models import END, LANGS, Graph, Node

CHOICE = ("single_choice", "multi_choice", "yes_no_unsure")


# ---------------------------------------------------------------- answers
def validate_answer(node: Node, value: Any) -> None:
    """Raise ValueError unless value is acceptable for node. "unsure" and SKIPPED are accepted for
    every node except consent (which must be an explicit agree/decline)."""
    if node.section == "consent":
        if value not in [o.id for o in node.options]:
            raise ValueError("consent needs an explicit choice")
        return
    if value == SKIPPED or value == UNSURE:
        return
    t = node.type
    if t == "body_map":
        specials = {o.id for o in node.options} - {"unsure"}
        bodymap.check_answer(value, node.maxSelections, specials)
        return
    if t in ("single_choice", "yes_no_unsure"):
        if not isinstance(value, str) or node.option(value) is None:
            raise ValueError(f"{node.id}: {value!r} is not an option")
    elif t == "multi_choice":
        if value == [UNSURE]:
            return
        if not isinstance(value, list) or not value or len(set(value)) != len(value):
            raise ValueError(f"{node.id}: need a non-empty list of distinct options")
        bad = [v for v in value if node.option(v) is None]
        if bad:
            raise ValueError(f"{node.id}: not options: {bad}")
        if "none" in value and len(value) > 1:
            raise ValueError(f"{node.id}: 'none' cannot be combined with other options")
    elif t == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{node.id}: need a number")
        if not (node.min <= value <= node.max):
            raise ValueError(f"{node.id}: {value} outside {node.min}..{node.max}")
    elif t == "scale_0_10":
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10:
            raise ValueError(f"{node.id}: need an integer 0-10")
    elif t == "free_text":
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{node.id}: need non-empty text (use skip instead)")


def answer_label(node: Node, value: Any, lang: str = "en") -> str:
    """Human-readable answer; distinguishes Not sure from Skipped."""
    lang = lang if lang in LANGS else "en"
    ui = {"en": ("Not sure", "Skipped"), "hi": ("पक्का नहीं", "छोड़ा गया"), "mr": ("खात्री नाही", "वगळले")}[lang]
    if value == SKIPPED:
        return ui[1]
    if value == UNSURE or value == [UNSURE]:
        return ui[0]
    if node.type == "body_map":
        if value.get("special"):
            return node.option(value["special"]).get(lang)
        return bodymap.regions_text(value["regions"], lang)
    if node.type in ("single_choice", "yes_no_unsure"):
        o = node.option(value)
        return o.get(lang) if o else str(value)
    if node.type == "multi_choice":
        return ", ".join(node.option(v).get(lang) if node.option(v) else str(v) for v in value)
    if node.type == "scale_0_10":
        return f"{value}/10"
    return str(value)


# ---------------------------------------------------------------- flow
def next_node(graph: Graph, answers: dict, current: str) -> str:
    """First matching rule's goto, else the node's default. Returns a node id or END."""
    nxt = graph.node(current).next
    for r in nxt.rules:
        if evaluate(r.if_, answers):
            return r.goto
    return nxt.default


@dataclass(frozen=True)
class PathResult:
    path: list[str]               # nodes on the current path, in order (answered ones + pending)
    pending: Optional[str]        # first node still needing an answer, None when the path reached END
    answers: dict                 # answers restricted to nodes on the path

    @property
    def complete(self) -> bool:
        return self.pending is None


def recompute_path(graph: Graph, answers: dict) -> PathResult:
    """Walk from start following current answers. Stops at the first unanswered node (the pending
    question). Answers for nodes no longer on the path are dropped."""
    path: list[str] = []
    node = graph.start
    pending = None
    limit = len(graph.nodes) + 1
    while node != END:
        if node in path or len(path) > limit:
            raise RuntimeError(f"cycle at {node}")
        path.append(node)
        if node not in answers:
            pending = node
            break
        node = next_node(graph, answers, node)
    return PathResult(path, pending, {n: answers[n] for n in path if n in answers})


def longest_path(graph: Graph, start: str) -> int:
    """Most nodes any route from start (inclusive) to END can contain, ignoring conditions.
    Upper bound on questions; graph must be acyclic (see validate_graph)."""
    memo: dict[str, int] = {}

    def go(n: str) -> int:
        if n == END:
            return 0
        if n not in memo:
            nxt = graph.node(n).next
            memo[n] = 1 + max(go(t) for t in [r.goto for r in nxt.rules] + [nxt.default])
        return memo[n]

    return go(start)


# ---------------------------------------------------------------- validation
def _edges(node: Node) -> list[str]:
    return [r.goto for r in node.next.rules] + [node.next.default]


def validate_graph(graph: Graph, red_flag_ids: Optional[set[str]] = None) -> list[str]:
    """Return a list of problems (empty = valid)."""
    errs: list[str] = []
    ids = graph.ids()
    idset = set(ids)
    if len(ids) != len(idset):
        errs.append("duplicate node ids")
    if graph.start not in idset:
        errs.append(f"start node {graph.start!r} does not exist")
        return errs

    for n in graph.nodes:
        for t in _edges(n):
            if t != END and t not in idset:
                errs.append(f"{n.id}: missing target {t!r}")
        for r in n.next.rules:
            for ref in referenced_nodes(r.if_):
                if ref not in idset:
                    errs.append(f"{n.id}: condition reads unknown node {ref!r}")
        # translations
        for lang in LANGS:
            if not getattr(n.text, lang).strip():
                errs.append(f"{n.id}: missing {lang} text")
            for o in n.options:
                if not getattr(o, lang).strip():
                    errs.append(f"{n.id}.{o.id}: missing {lang} option text")
        if red_flag_ids is not None:
            for ref in n.redFlagRefs:
                if ref not in red_flag_ids:
                    errs.append(f"{n.id}: unknown redFlagRef {ref!r}")
    if errs and any("missing target" in e for e in errs):
        return errs  # structural checks below assume targets exist

    for r in bodymap.catalog().regions:
        for lang in LANGS:
            if not getattr(r, lang).strip():
                errs.append(f"region {r.id}: missing {lang} label")
    # option values used in conditions must exist
    by_id = {n.id: n for n in graph.nodes}
    for n in graph.nodes:
        for r in n.next.rules:
            errs += _check_values(r.if_, by_id, f"{n.id}")

    # cycles (iterative colouring DFS)
    colour: dict[str, int] = {}
    for root in ids:
        if colour.get(root):
            continue
        stack = [(root, iter(_edges(by_id[root])))]
        colour[root] = 1
        while stack:
            n, it = stack[-1]
            for t in it:
                if t == END:
                    continue
                if colour.get(t) == 1:
                    errs.append(f"cycle through {n} -> {t}")
                elif not colour.get(t):
                    colour[t] = 1
                    stack.append((t, iter(_edges(by_id[t]))))
                    break
            else:
                colour[n] = 2
                stack.pop()

    # unreachable
    seen, todo = set(), [graph.start]
    while todo:
        n = todo.pop()
        if n in seen or n == END:
            continue
        seen.add(n)
        todo += _edges(by_id[n])
    for n in ids:
        if n not in seen:
            errs.append(f"unreachable node {n!r}")

    # every node can reach END
    rev: dict[str, list[str]] = {n: [] for n in ids}
    ends = []
    for n in graph.nodes:
        for t in _edges(n):
            if t == END:
                ends.append(n.id)
            else:
                rev[t].append(n.id)
    ok, todo = set(), list(ends)
    while todo:
        n = todo.pop()
        if n in ok:
            continue
        ok.add(n)
        todo += rev[n]
    for n in ids:
        if n not in ok:
            errs.append(f"node {n!r} has no path to END")
    return errs


def _check_values(cond: dict, by_id: dict, where: str) -> list[str]:
    (op, arg), = cond.items()
    if op in ("all", "any"):
        return [e for c in arg for e in _check_values(c, by_id, where)]
    if op == "not":
        return _check_values(arg, by_id, where)
    if op in ("answered", "unanswered"):
        return []
    node = by_id.get(arg[0])
    if node is None:
        return []
    if op in ("regionsAny", "regionsAll"):
        if node.type != "body_map":
            return [f"{where}: {op} on non-body_map node {node.id}"]
        known = set(bodymap.region_ids())
        return [f"{where}: unknown region {v!r}" for v in arg[1] if v not in known]
    if op in ("gte", "lte"):
        return [] if node.type in ("number", "scale_0_10") else [f"{where}: {op} on non-numeric node {node.id}"]
    vals = arg[1] if op == "in" else [arg[1]]
    if node.type not in CHOICE:
        return [f"{where}: {op} on non-choice node {node.id}"]
    legal = {o.id for o in node.options} | {UNSURE}
    return [f"{where}: {node.id} has no option {v!r}" for v in vals if v not in legal]
