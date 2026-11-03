"""Rule selection: indication, population (age/weight windows), route. Conventions are documented in docs/DOSING_LOGIC.md.

* age min is inclusive; age max is inclusive through the completed unit (max_age_years 17 = up to 17 y 11 m).
* weight min is inclusive, weight max is exclusive (amoxicillin-clavulanate: <40 kg child rule, >=40 kg adult).
* population {} means a paediatric rule (age < adult threshold) when the dose is weight-based; otherwise the rule
  applies with a 'population unspecified' warning.
* adult rules (min_age_years >= adult threshold) supersede open-ended weight-based rules for adult patients."""
import json
import re
from dataclasses import dataclass, field

from .config import Config
from .formulary import Formulary, norm_status
from .messages import msg

UNIT_DAYS = {"years": 365.25, "months": 30.4375, "weeks": 7.0, "days": 1.0}
WEIGHT_TYPES = {"mg_per_kg_per_dose", "mg_per_kg_per_day", "weight_band"}
WILDCARD_KEYS = {"any", "all indications"}
_POP_RE = re.compile(r"^(min|max)_age_(years|months|weeks|days)$")


def indication_key(label: str) -> str:
    return re.split(r"\s*[,(]", (label or "").lower().strip(), maxsplit=1)[0].strip()


def indications(drug: dict) -> list[dict]:
    """Doctor-facing indication list: [{key, rules:[idx], labels:[...]}] in first-seen order."""
    out: dict = {}
    for i, r in enumerate(drug["dose_rules"]):
        k = indication_key(r["indication"])
        e = out.setdefault(k, {"key": k, "rules": [], "labels": []})
        e["rules"].append(i)
        e["labels"].append(r["indication"])
    return list(out.values())


def is_weight_dependent(rule: dict) -> bool:
    return rule["dose_type"] in WEIGHT_TYPES


@dataclass
class Pop:
    status: str = "match"      # match | age_below | age_above | weight_below | weight_above | age_ambiguous | needs
    reasons: list = field(default_factory=list)
    needs: list = field(default_factory=list)       # [(field, message)]
    warnings: list = field(default_factory=list)
    window: str = ""


def _age_ok(bound_kind: str, n: float, unit: str, lo: float, hi: float):
    """(ok_at_lo, ok_at_hi) for one bound; hi is exclusive so test just below it."""
    days = UNIT_DAYS[unit]
    if bound_kind == "min":
        f = lambda a: a >= n * days
    else:
        f = lambda a: a < (n + 1) * days
    return f(lo), f(hi - 1e-6)


def population_check(rule: dict, ctx, cfg: Config, adult_switch: dict | None = None) -> Pop:
    pop = dict(rule.get("population") or {})
    p = Pop()
    w0 = ctx.get("weight_kg")
    if adult_switch and w0 is not None and w0 >= adult_switch["min_weight_kg"] and pop.get("min_age_years", 0) >= cfg.adult_min_age_years:
        pop.pop("min_age_years")                         # drug-level adult_switch: at this weight the adult dose applies
        p.warnings.append(msg("warn_adult_switch", w=w0, src=adult_switch.get("source", "")))
    implicit = False
    if not pop:
        if is_weight_dependent(rule):
            pop = {"max_age_years": cfg.adult_min_age_years - 1}      # convention: {} + weight-based = paediatric
            implicit = True
        else:
            p.warnings.append(msg("warn_population_unspecified"))
    lo, hi = ctx.age_days()
    desc = ["{}{}".format("" if not implicit else "implicit ", f"{k} {v}") for k, v in pop.items()]
    p.window = ", ".join(desc) or "no population stated"
    age_keys = [k for k in pop if _POP_RE.match(k)]
    if age_keys:
        if lo is None:
            p.status = "needs"
            p.needs.append(("age_months", msg("need_age")))
            return p
        ambiguous = False
        for k in age_keys:
            kind, unit = _POP_RE.match(k).groups()
            a, b = _age_ok(kind, pop[k], unit, lo, hi)
            if a and b:
                continue
            if not a and not b:
                p.status = "age_below" if kind == "min" else "age_above"
                p.reasons.append(msg("block_age", age=_age_text(ctx), why=f"{k} {pop[k]}"))
                return p
            ambiguous = True
            p.reasons.append(f"{k} {pop[k]}")
        if ambiguous:
            p.status = "age_ambiguous"
            p.needs.append(("age_exact", msg("need_age_exact", lo=round(lo / UNIT_DAYS["months"], 1),
                                             hi=round(hi / UNIT_DAYS["months"], 1), why=", ".join(p.reasons))))
            return p
    wmin, wmax = pop.get("min_weight_kg"), pop.get("max_weight_kg")
    if wmin is not None or wmax is not None:
        w = ctx.get("weight_kg")
        if w is None:
            p.status = "needs"
            p.needs.append(("weight_kg", msg("need_weight", why=p.window)))
            return p
        if wmin is not None and w < wmin:
            p.status = "weight_below"
            p.reasons.append(msg("block_weight", w=w, why=f"min_weight_kg {wmin}"))
        elif wmax is not None and w >= wmax:
            p.status = "weight_above"
            p.reasons.append(msg("block_weight", w=w, why=f"max_weight_kg {wmax}"))
    return p


def _age_text(ctx) -> str:
    m = ctx.get("age_months")
    w = ctx.get("age_window_months") or 0
    return f"{m} months" if not w else f"{m // 12} years"


def at_age_edge(rule: dict, ctx) -> bool:
    """True when the patient's completed age equals a stated age bound of the rule (e.g. 6 y against min_age_years 6 or
    max_age_years 6): the place where neighbouring rules overlap under the completed-age convention."""
    lo, hi = ctx.age_days()
    if lo is None:
        return False
    for k, n in (rule.get("population") or {}).items():
        m = _POP_RE.match(k)
        if m:
            d = UNIT_DAYS[m.group(2)]
            if int(lo // d) == n and int((hi - 1e-6) // d) == n:
                return True
    return False


def route_classes(route_text) -> set:
    if not route_text:
        return {"oral"}                 # convention: a rule without a route is an oral rule
    t = route_text.upper()
    out = set()
    if re.search(r"\bPO\b|ORAL", t):
        out.add("oral")
    if re.search(r"\bIV\b|\bIM\b|INJ", t):
        out.add("parenteral")
    return out or {"oral", "parenteral", "rectal"}


@dataclass
class Candidate:
    rid: str
    rule: dict
    index: int
    pop: Pop
    option: int | None = None          # index into rule['options'] when the rule is expanded
    also: list = field(default_factory=list)      # identical rules from other sources that corroborate this one


def _has_numeric_dose(rule: dict) -> bool:
    return any(k in rule for k in ("dose_mg", "start_mg", "mg_per_kg", "mg_per_kg_per_day", "mg_per_day", "weight_bands"))


def expand(rule: dict) -> list[tuple[int | None, dict]]:
    """Rules whose `options` are alternatives (dicts, or free text with no numeric dose) become one pseudo-rule each."""
    opts = rule.get("options")
    if not opts or (_has_numeric_dose(rule) and all(isinstance(o, str) for o in opts)):
        return [(None, rule)]
    out = []
    for j, o in enumerate(opts):
        base = {k: v for k, v in rule.items() if k != "options"}
        if isinstance(o, dict):
            base.update(o)
        else:
            base["_text_option"] = o
        out.append((j, base))
    return out


def select(f: Formulary, drug: dict, ind_key: str | None, ctx, route_class: str | None, cfg: Config,
           show_all: bool = False):
    """-> (candidates, gated) ; gated = [Pop] of in-scope rules that failed on age/weight (for the 'blocked' reason)."""
    cands, gated = [], []
    for i, r0 in enumerate(drug["dose_rules"]):
        k = indication_key(r0["indication"])
        if not (show_all or k == ind_key or k in WILDCARD_KEYS):
            continue
        if route_class and route_class not in route_classes(r0.get("route")):
            continue
        for j, r in expand(r0):
            pop = population_check(r, ctx, cfg, drug.get("adult_switch"))
            rid = f"{drug['id']}#{i}" + (f".{j}" if j is not None else "")
            c = Candidate(rid, r, i, pop, j)
            if pop.status in ("match", "needs", "age_ambiguous"):
                cands.append(c)
            else:
                gated.append(c)
    cands = _merge_identical(cands)
    # adult rules supersede open-ended weight-based rules for adult patients
    lo, _ = ctx.age_days()
    if lo is not None and lo >= cfg.adult_min_age_years * UNIT_DAYS["years"]:
        has_adult_fixed = any(not is_weight_dependent(c.rule) and c.pop.status == "match" for c in cands)
        if has_adult_fixed:
            cands = [c for c in cands if not (is_weight_dependent(c.rule) and not any(
                k.startswith("max_") for k in (c.rule.get("population") or {})) )]
    return cands, gated


_NON_DOSE = {"indication", "source", "status", "note", "conflict"}
_RANK = {"VERIFIED": 0, "SECONDARY": 1, "UNVERIFIED": 2}


def _merge_identical(cands: list) -> list:
    """Rules with the same dose content (differing only in source, status or note) are one rule with several sources:
    the best-status one is kept and the others are listed as corroborating."""
    groups: dict = {}
    for c in cands:
        fp = json.dumps({k: v for k, v in c.rule.items() if k not in _NON_DOSE}, sort_keys=True) + "|" + indication_key(c.rule["indication"])
        groups.setdefault(fp, []).append(c)
    out = []
    for g in groups.values():
        rep = sorted(g, key=lambda c: (_RANK[norm_status(c.rule.get("status"))], c.index))[0]
        rep.also = [{"rule_id": c.rid, "status": norm_status(c.rule.get("status")), "source": c.rule.get("source")} for c in g if c is not rep]
        out.append(rep)
    return sorted(out, key=lambda c: c.index)


def suggested(f: Formulary, drug: dict, cands: list):
    """First VERIFIED in formulary order (the file lists guideline-ranked sources first), else SECONDARY, else first."""
    for want in ("VERIFIED", "SECONDARY", "UNVERIFIED"):
        for c in cands:
            if norm_status(c.rule.get("status")) == want:
                return c, want
    return (cands[0], "first") if cands else (None, "")


def doctor_picks(f: Formulary, drug_id: str) -> bool:
    return any(k.startswith(drug_id) and "doctor picks" in str(v).lower() for k, v in f.defaults.items())
