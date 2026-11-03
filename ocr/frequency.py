"""Deterministic parsing of Indian frequency notation. The verbatim string is always kept."""
import re
from fractions import Fraction

_ABBR = {
    "od": (1, "once daily"), "qd": (1, "once daily"), "daily": (1, "once daily"),
    "bd": (2, "twice daily"), "bid": (2, "twice daily"),
    "tds": (3, "three times daily"), "tid": (3, "three times daily"),
    "qid": (4, "four times daily"), "qds": (4, "four times daily"),
}
_SLOTS3 = ["morning", "afternoon", "night"]
_SLOTS4 = ["morning", "afternoon", "evening", "night"]


def _num(tok: str) -> float | None:
    tok = tok.strip().replace("½", "1/2").replace("¼", "1/4")
    try:
        return float(Fraction(tok))
    except (ValueError, ZeroDivisionError):
        return None


def parse_frequency(text: str | None) -> dict:
    out = {"verbatim": text, "kind": "unknown", "timesPerDay": None,
           "perDose": None, "slots": None, "timing": None, "display": None}
    if not text or not text.strip():
        return out
    t = text.strip().lower()

    if re.search(r"\b(a\.?c\.?|before (food|meals?))\b", t):
        out["timing"] = "before food"
    elif re.search(r"\b(p\.?c\.?|after (food|meals?))\b", t):
        out["timing"] = "after food"
    elif re.search(r"\bempty stomach\b", t):
        out["timing"] = "empty stomach"

    # numeric pattern 1-0-1 / 1-1-1-1 / 1/2-0-1
    m = re.search(r"(?<![\d/])((?:\d+(?:/\d+)?|½|¼)(?:\s*[-–]\s*(?:\d+(?:/\d+)?|½|¼)){2,3})(?![\d/])", t)
    if m:
        parts = [_num(p) for p in re.split(r"\s*[-–]\s*", m.group(1))]
        if None not in parts and all(0 <= q <= 10 for q in parts):
            slots_names = _SLOTS3 if len(parts) == 3 else _SLOTS4
            slots = {n: q for n, q in zip(slots_names, parts)}
            active = [n for n, q in slots.items() if q > 0]
            out.update(kind="scheduled", slots=slots, timesPerDay=len(active),
                       perDose=max(parts) if len(set(p for p in parts if p > 0)) == 1 else None,
                       display=f"{len(active)}x/day ({', '.join(active)})" if active else "no doses")
            return out

    if re.search(r"\b(sos|prn|if needed|when required|as needed)\b", t):
        out.update(kind="prn", display="as needed (SOS/PRN)")
        return out
    if re.search(r"\b(stat|immediately)\b", t):
        out.update(kind="stat", timesPerDay=1, display="single immediate dose (STAT)")
        return out
    if re.search(r"\b(hs|h\.s\.|at bedtime|bedtime|at night|nocte)\b", t):
        out.update(kind="scheduled", timesPerDay=1, slots={"night": 1.0}, display="once daily at bedtime (HS)")
        return out
    for ab, (n, disp) in _ABBR.items():
        if re.search(rf"\b{ab}\b", t):
            out.update(kind="scheduled", timesPerDay=n, display=disp)
            return out
    m = re.search(r"\b(?:q|every)\s*(\d{1,2})\s*h(?:ours?|rs?)?\b", t)
    if m and int(m.group(1)) > 0:
        h = int(m.group(1))
        out.update(kind="scheduled", timesPerDay=round(24 / h, 2), display=f"every {h} hours")
        return out
    if re.search(r"\bweekly\b|\bonce a week\b", t):
        out.update(kind="scheduled", display="weekly")
        return out
    return out
