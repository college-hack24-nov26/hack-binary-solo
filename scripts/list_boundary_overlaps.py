"""List every pair of rules (same drug, same indication key) whose age windows overlap under the completed-age convention.
Run: .venv/bin/python scripts/list_boundary_overlaps.py"""
import itertools
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dosing import config, formulary  # noqa: E402
from dosing.rules import UNIT_DAYS, indication_key, is_weight_dependent  # noqa: E402

POP = re.compile(r"^(min|max)_age_(years|months|weeks|days)$")


def window(rule, adult=18):
    pop = rule.get("population") or {}
    if not pop and is_weight_dependent(rule):
        pop = {"max_age_years": adult - 1}
    lo, hi = 0.0, float("inf")
    for k, n in pop.items():
        m = POP.match(k)
        if m:
            d = UNIT_DAYS[m.group(2)]
            if m.group(1) == "min":
                lo = max(lo, n * d)
            else:
                hi = min(hi, (n + 1) * d)
    return lo, hi


def desc(r):
    p = r.get("population") or {}
    return ", ".join(f"{k} {v}" for k, v in p.items() if k.startswith(("min_age", "max_age"))) or "no age stated"


f = formulary.load(config.Config().formulary_path)
for did, d in f.drugs.items():
    rs = list(enumerate(d["dose_rules"]))
    for (i, a), (j, b) in itertools.combinations(rs, 2):
        if indication_key(a["indication"]) != indication_key(b["indication"]):
            continue
        la, ha = window(a)
        lb, hb = window(b)
        lo, hi = max(la, lb), min(ha, hb)
        if hi > lo and not (la == lb and ha == hb):
            same_dose = {k: v for k, v in a.items() if k not in ("indication", "source", "status", "note", "conflict")} == \
                        {k: v for k, v in b.items() if k not in ("indication", "source", "status", "note", "conflict")}
            span = "inf" if hi == float("inf") else f"{(hi - lo) / 365.25:.2f} y"
            kind = "single completed-unit overlap at a boundary" if hi != float("inf") and (hi - lo) <= 366 else "wide overlap"
            print(f"- {did}#{i} ({desc(a)}) vs {did}#{j} ({desc(b)}), indication '{indication_key(a['indication'])}': {kind}, overlap {span}"
                  + (" [identical dose content, merged]" if same_dose else ""))
