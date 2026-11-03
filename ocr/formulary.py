"""Fuzzy match of drug names against the local formulary. Suggest only; never rewrite the written name."""
import json
import re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

from .config import ROOT

MATCH_THRESHOLD = 0.85   # below this: no suggestion, needsReview
AMBIGUITY_GAP = 0.08     # runner-up closer than this: needsReview

_PREFIX = re.compile(r"^(rx\s*[:.]?\s*)?(tab(let)?s?|cap(sule)?s?|syp|syrup|inj(ection)?|oint(ment)?|drops?)\b\.?\s*", re.I)
_STRENGTH = re.compile(r"\b\d+(\.\d+)?\s*(mg|mcg|µg|g|ml|iu|%)\b.*$", re.I)


def normalize(name: str) -> str:
    n = name.strip().lower()
    n = _PREFIX.sub("", n)
    n = _STRENGTH.sub("", n)
    n = re.sub(r"[^a-z\s\-]", " ", n)
    return re.sub(r"\s+", " ", n).strip()


@lru_cache(maxsize=1)
def load_formulary(path: str | None = None) -> list[tuple[str, str]]:
    """Returns list of (searchable_term, generic)."""
    p = Path(path) if path else ROOT / "data" / "formulary.json"
    terms = []
    for d in json.loads(p.read_text())["drugs"]:
        for t in [d["generic"], *d.get("aliases", [])]:
            terms.append((normalize(t), d["generic"]))
    return terms


def match_drug(name_as_written: str, terms: list[tuple[str, str]] | None = None) -> dict:
    terms = terms if terms is not None else load_formulary()
    q = normalize(name_as_written)
    res = {"suggestedGeneric": None, "matchScore": 0.0, "ambiguous": False}
    if not q:
        return res
    best: dict[str, float] = {}
    for term, generic in terms:
        s = 1.0 if q == term else SequenceMatcher(None, q, term).ratio()
        best[generic] = max(best.get(generic, 0.0), s)
    ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
    top_g, top_s = ranked[0]
    res["matchScore"] = round(top_s, 3)
    if top_s >= MATCH_THRESHOLD:
        res["suggestedGeneric"] = top_g
        if len(ranked) > 1 and top_s - ranked[1][1] < AMBIGUITY_GAP:
            res["ambiguous"] = True
    return res
