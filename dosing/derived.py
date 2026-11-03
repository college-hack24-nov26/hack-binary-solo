"""Derived values, evaluated from the formula strings in the formulary JSON itself.
The strings are Python-like expressions; a small AST whitelist evaluates them (no eval, no names beyond the inputs)."""
import ast
import math
import operator
import re
from dataclasses import dataclass, field

from .formulary import Formulary, norm_status
from .messages import msg

_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow}
_FUNCS = {"min": min, "max": max, "sqrt": math.sqrt}


def safe_eval(expr: str, names: dict) -> float:
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return n.value
        if isinstance(n, ast.Name) and n.id in names:
            return names[n.id]
        if isinstance(n, ast.BinOp) and type(n.op) in _BIN:
            return _BIN[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            return -ev(n.operand) if isinstance(n.op, ast.USub) else ev(n.operand)
        if isinstance(n, ast.IfExp):
            return ev(n.body) if ev(n.test) else ev(n.orelse)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS and not n.keywords:
            return _FUNCS[n.func.id](*[ev(a) for a in n.args])
        raise ValueError(f"unsupported expression element {ast.dump(n)[:60]}")
    return float(ev(ast.parse(expr, mode="eval")))


@dataclass
class Derived:
    name: str
    value: float | None
    steps: list[str] = field(default_factory=list)
    status: str = "VERIFIED"           # formula status from the formulary
    needs: list[tuple[str, str]] = field(default_factory=list)      # (field, why)
    note: str = ""


def _round(x, n=2):
    return None if x is None else round(x, n)


def formula_population(formulary: Formulary, name: str, adult_min: int) -> tuple[float, float]:
    """(min_years, max_years) parsed from the formula's population text: 'adults' or 'children 1-16 years'."""
    p = formulary.formulas[name].get("population", "")
    m = re.search(r"children\s+(\d+)\s*-\s*(\d+)\s*years", p)
    if m:
        return float(m.group(1)), float(m.group(2)) + 1 - 1e-9      # '1-16 years' = through completed year 16
    if "adults" in p:
        return float(adult_min), 200.0
    return 0.0, 200.0


def cockcroft_gault(f: Formulary, age_y, weight, scr, female):
    fm = f.formulas["cockcroft_gault"]
    v = safe_eval(fm["formula"], {"age": age_y, "weight_kg": weight, "scr_mg_dl": scr, "female": female})
    return v


def ckd_epi(f: Formulary, age_y, scr, female):
    fm = f.formulas["ckd_epi_2021"]
    sex = "female" if female else "male"
    return safe_eval(fm["formula"], {"scr": scr, "k": fm["k"][sex], "a": fm["a"][sex], "age": age_y, "female": female})


def schwartz(f: Formulary, height_cm, scr):
    return safe_eval(f.formulas["bedside_schwartz"]["formula"], {"height_cm": height_cm, "scr_mg_dl": scr})


def bsa(f: Formulary, height_cm, weight):
    return safe_eval(f.formulas["mosteller_bsa"]["formula"], {"height_cm": height_cm, "weight_kg": weight})


def body_weights(f: Formulary, height_cm, weight, male: bool, factor):
    """(IBW, ABW). Formulary marks IBW UNVERIFIED and ABW SECONDARY; callers mark the result."""
    ibw = safe_eval(f.formulas["ideal_body_weight"]["formula"],
                    {"male": male, "height_in": height_cm / 2.54})
    fac = f.formulas["adjusted_body_weight"]["factor_default"] if factor is None else factor
    abw = safe_eval(f.formulas["adjusted_body_weight"]["formula"], {"IBW": ibw, "factor": fac, "TBW": weight})
    return ibw, abw, fac


# measure family named by a renal rule -> formula(s), by the formulary's own unit_rule
MEASURE_FORMULA = {"CRCL": ["cockcroft_gault"], "GFR": ["cockcroft_gault"], "EGFR": ["ckd_epi_2021", "bedside_schwartz"]}


def measure_family(measure: str) -> str | None:
    m = re.match(r"\s*(CrCl|eGFR|GFR)\b", measure or "", re.I)
    return m.group(1).upper() if m else None


def renal_measure(f: Formulary, family: str, ctx, cfg) -> Derived:
    """Compute the measure a renal rule names. Never substitutes silently: steps say what was used."""
    d = Derived(name=family, value=None)
    age_m = ctx.get("age_months")
    if age_m is None:
        d.needs.append(("age", msg("need_age")))
        return d
    age_y = age_m / 12.0
    scr = ctx.get("scr_mg_dl")
    wt = ctx.get("weight_kg")
    sex = ctx.get("sex_for_formula") or ctx.get("sex")
    female = {"female": True, "male": False}.get(sex)
    for fname in MEASURE_FORMULA.get(family, []):
        lo, hi = formula_population(f, fname, cfg.adult_min_age_years)
        if not (lo <= age_y <= hi):
            continue
        d.status = norm_status(f.formulas[fname].get("status"))
        if scr is None:
            d.needs.append(("scr_mg_dl", msg("need_scr", why=f"{family} via {fname}")))
        if fname == "bedside_schwartz":
            ht = ctx.get("height_cm")
            if ht is None:
                d.needs.append(("height_cm", msg("need_height", why="bedside Schwartz eGFR for a child")))
            if scr is not None and ht is not None:
                d.value = _round(schwartz(f, ht, scr))
                d.steps.append(msg("step_schwartz", v=d.value, h=ht, scr=scr))
        else:
            if fname == "cockcroft_gault" and wt is None:
                d.needs.append(("weight_kg", msg("need_weight", why="Cockcroft-Gault")))
            if female is None:
                d.needs.append(("sex_for_formula", msg("need_sex_formula")))
            if not d.needs and scr is not None:
                if fname == "cockcroft_gault":
                    d.value = _round(cockcroft_gault(f, age_y, wt, scr, female))
                    d.steps.append(msg("step_cg", v=d.value, age=_round(age_y, 1), w=wt, scr=scr,
                                       sex="female" if female else "male"))
                else:
                    d.value = _round(ckd_epi(f, age_y, scr, female))
                    d.steps.append(msg("step_ckdepi", v=d.value, age=_round(age_y, 1), scr=scr,
                                       sex="female" if female else "male"))
        if d.value is not None and family in ("GFR",):
            d.steps.append(msg("step_measure_used", named="GFR", used="Cockcroft-Gault CrCl"))
        d.note = fname
        return d
    d.note = "no_formula"
    return d
