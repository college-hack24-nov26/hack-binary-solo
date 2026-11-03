"""Free-text medicine and allergy names -> labels, via data/med_synonyms.json. No fuzzy matching: a name is either in
the table or it is shown as 'unparsed: doctor to review'."""
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "med_synonyms.json"
_STOP = {"tab", "tablet", "tablets", "cap", "capsule", "capsules", "syp", "syrup", "inj", "injection", "drops", "oint",
         "ointment", "cream", "the", "a", "of", "daily", "od", "bd", "tds", "qid", "hs", "sos", "once", "twice",
         "day", "days", "morning", "night", "taking", "takes", "medicine", "medicines", "for", "with", "and", "or"}


def canon(term: str) -> str:
    """Lowercase, drop parentheses and a 'class:' prefix, singularise words (nsaids -> nsaid)."""
    t = re.sub(r"\(.*?\)", " ", (term or "").lower())
    t = re.sub(r"^\s*(class|flag|allergy):", "", t)
    words = [w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in re.split(r"\s+", t.strip())]
    return " ".join(w for w in words if w)


def term_matches(term: str, labels) -> bool:
    t = canon(term)
    for lab in labels:
        c = canon(lab)
        if c and (c == t or re.search(rf"(?<![a-z0-9]){re.escape(c)}(?![a-z0-9])", t)):
            return True
    return False


@dataclass
class MedMatch:
    raw: str
    matched_name: str
    generic: str
    labels: list
    drug_id: str | None = None
    kind: str = "generic"


@lru_cache(maxsize=1)
def _table():
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    idx = {}
    for e in raw["entries"]:
        for n in e["names"]:
            idx.setdefault(n.lower(), e)
    by_drug = {e["drug_id"]: e for e in raw["entries"] if e.get("drug_id")}
    return idx, by_drug


def labels_for_drug(drug_id: str) -> list:
    e = _table()[1].get(drug_id)
    return list(e["labels"]) if e else []


def _clean(s: str) -> str:
    s = re.sub(r"\b\d+(\.\d+)?\s*(mg|mcg|g|gm|ml|iu)\b", " ", s.lower())
    s = re.sub(r"[^a-z0-9\- ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _scan(phrase: str):
    """Left-to-right longest-match over the words of a cleaned phrase -> ([(name, entry)], [leftover words])."""
    idx = _table()[0]
    words = phrase.split()
    found, left, i = [], [], 0
    while i < len(words):
        for n in range(min(3, len(words) - i), 0, -1):
            cand = " ".join(words[i:i + n])
            if cand in idx:
                found.append((cand, idx[cand]))
                i += n
                break
        else:
            if words[i] not in _STOP and not words[i].isdigit():
                left.append(words[i])
            i += 1
    return found, left


def parse_names(text: str):
    """-> (matches, unparsed_tokens). Splits on comma, semicolon, newline, '+', ' and '. A part with no recognised
    word is returned whole as unparsed; leftover words next to a recognised one are returned individually."""
    text = re.sub(r"amoxi\w*\s+(and|\+|with)\s+clavulan\w*(\s+acid)?", "amoxicillin clavulanate", text or "", flags=re.I)
    matches, unparsed = [], []
    for seg in re.split(r"[,;\n+]+|\s+and\s+", text):
        raw = seg.strip()
        c = _clean(raw)
        if not c:
            continue
        found, left = _scan(c)
        if not found:
            unparsed.append(raw)
            continue
        for name, e in found:
            matches.append(MedMatch(raw=raw, matched_name=name, generic=e["generic"], labels=list(e["labels"]),
                                    drug_id=e.get("drug_id"), kind=e["kind"]))
        unparsed.extend(left)
    return matches, unparsed


def match_allergy_text(text: str, drug_labels):
    """Free-text allergy: every recognised item, whether it hits the prescribed drug's labels, and the unrecognised rest."""
    matches, unparsed = parse_names(text)
    hits = [m for m in matches if any(term_matches(l, drug_labels) or term_matches(m.matched_name, drug_labels)
                                      for l in m.labels)]
    return matches, hits, unparsed
