"""Dose arithmetic for one rule, by dose_type. Every number comes from the rule (or formulary defaults); every cap is
reported; nothing is rounded up past a cap. Product rounding happens in engine.py via products.py."""
from dataclasses import dataclass, field
from typing import Any

from .config import Config
from .formulary import Formulary
from .messages import msg
from .rules import WEIGHT_TYPES

NUMERIC = ("dose_mg", "start_mg", "mg_per_kg", "mg_per_kg_per_day", "mg_per_day")


def rng(x):
    """number or [lo, hi] -> (lo, hi)."""
    if isinstance(x, (list, tuple)):
        return float(min(x)), float(max(x))
    return float(x), float(x)


def r3(x):
    return None if x is None else round(float(x), 3)


def fmt(x):
    return f"{x:g}" if isinstance(x, (int, float)) else str(x)


@dataclass
class Calc:
    kind: str = "none"                 # numeric | text | plan | duration | none
    lo: float | None = None            # per-dose mg range after caps and adjustments
    hi: float | None = None
    target: float | None = None
    n_lo: float | None = None          # doses per day
    n_hi: float | None = None
    interval_h: Any = None
    doses_per_day: Any = None
    daily_lo: float | None = None
    daily_hi: float | None = None
    daily_max_mg: float | None = None
    binding_cap: str | None = None
    ceiling: float | None = None       # a bound cap: no delivered dose may exceed it
    duration: str | None = None
    text: str | None = None
    plan: dict | None = None
    product_keys: list = field(default_factory=list)
    max_tablets_per_day: float | None = None
    steps: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    needs: list = field(default_factory=list)
    refused: list = field(default_factory=list)
    off_label: bool = False


def _duration(rule) -> str | None:
    parts = []
    if "duration_days" in rule:
        lo, hi = rng(rule["duration_days"])
        parts.append(f"{fmt(lo)} days" if lo == hi else f"{fmt(lo)} to {fmt(hi)} days")
    if "duration_weeks" in rule:
        parts.append(f"{fmt(rule['duration_weeks'])} weeks")
    if "duration_days_otitis" in rule:
        parts.append(f"{fmt(rule['duration_days_otitis'])} days for otitis media")
    if "max_duration_days" in rule:
        parts.append(f"maximum {fmt(rule['max_duration_days'])} days")
    return "; ".join(parts) or None


def _frequency(rule: dict, di: dict, c: Calc, need_n: bool):
    n_lo = n_hi = None
    if rule.get("single_dose"):
        n_lo = n_hi = 1.0
        c.doses_per_day = 1
    elif "interval_h" in rule:
        ilo, ihi = rng(rule["interval_h"])
        c.interval_h = rule["interval_h"]
        if ilo <= 24:
            n_lo, n_hi = 24.0 / ihi, 24.0 / ilo
    elif "doses_per_day" in rule:
        n_lo, n_hi = rng(rule["doses_per_day"])
        c.doses_per_day = rule["doses_per_day"]
    elif di.get("doses_per_day"):
        n_lo = n_hi = float(di["doses_per_day"])
        c.doses_per_day = di["doses_per_day"]
    elif need_n:
        c.needs.append(("doses_per_day", msg("need_doses_per_day")))
    if n_hi is not None and "max_doses_per_day" in rule:
        n_hi = min(n_hi, float(rule["max_doses_per_day"]))
        n_lo = min(n_lo, n_hi)
    if "min_interval_h" in rule and "interval_h" in rule:
        if rng(rule["interval_h"])[0] < rule["min_interval_h"]:
            c.warnings.append(msg("warn_interval_short", h=fmt(rng(rule["interval_h"])[0]), min_h=fmt(rule["min_interval_h"])))
    c.n_lo, c.n_hi = n_lo, n_hi


def _child_defaults(f: Formulary, drug_id: str, rule: dict, ctx, cfg) -> dict:
    """Caps the formulary's `defaults` give for paediatric patients, only where the rule did not state its own."""
    d = f.defaults.get(f"{drug_id}_child")
    lo, _ = ctx.age_days()
    if not isinstance(d, dict) or lo is None or lo >= cfg.adult_min_age_years * 365.25 or rule["dose_type"] not in WEIGHT_TYPES:
        return {}
    ren = {"max_mg_per_kg_per_day": "max_per_kg_per_day"}
    out = {}
    for k, v in d.items():
        k2 = ren.get(k, k)
        if k2 in ("max_per_kg_per_day", "max_per_dose_mg", "max_per_day_mg", "max_doses_per_day") and k2 not in rule \
                and not isinstance(v, str):
            out[k2] = v
    return out


def compute(f: Formulary, drug: dict, rule: dict, ctx, di: dict, cfg: Config, adjust: dict | None = None) -> Calc:
    adjust = adjust or {}
    c = Calc()
    dt = rule["dose_type"]
    W = ctx.get("weight_kg")
    c.duration = _duration(rule)
    c.product_keys = [rule["product"]] if isinstance(rule.get("product"), str) else list(rule.get("products") or [])
    if "max_tablets_per_day" in rule:
        c.max_tablets_per_day = float(rule["max_tablets_per_day"])
    c.off_label = "off-label" in rule["indication"].lower()
    if c.off_label:
        c.warnings.append(msg("warn_offlabel"))

    if dt == "duration_only":
        c.kind = "duration"
        c.steps.append(msg("step_duration", d=c.duration or "not stated"))
        return c
    if dt == "titration":
        c.kind = "plan"
        c.plan = {k: rule[k] for k in ("start", "step", "max_per_day_mg", "doses_per_day", "note") if k in rule}
        c.daily_max_mg = rule.get("max_per_day_mg")
        c.steps.append(msg("step_titration", start=rule.get("start", "not stated in this rule"),
                           step=rule.get("step", "not stated"), mx=fmt(rule.get("max_per_day_mg", "not stated"))))
        return c
    if "_text_option" in rule or (dt == "fixed" and not any(k in rule for k in NUMERIC)):
        text = rule.get("_text_option")
        if text is None:
            c.refused.append(msg("refused_rule_incomplete", what="fixed rule without dose_mg, start_mg or options"))
            return c
        c.kind, c.text = "text", text
        c.daily_max_mg = rule.get("max_per_day_mg")
        c.steps.append(msg("step_text_option", t=text))
        return c
    if "schedule" in rule and not any(k in rule for k in NUMERIC):
        c.kind, c.text = "text", rule["schedule"]
        c.steps.append(msg("step_text_option", t=rule["schedule"]))
        return c

    needs_w = dt in WEIGHT_TYPES or "max_per_kg_per_day" in rule
    if needs_w and W is None:
        c.needs.append(("weight_kg", msg("need_weight", why=f"{dt}")))
        return c

    _frequency(rule, di, c, need_n=dt in ("fixed_daily", "mg_per_kg_per_day") or (dt == "weight_band" and False))
    if c.needs:
        return c

    lo = hi = None
    if dt == "fixed":
        if "dose_mg" in rule:
            lo, hi = rng(rule["dose_mg"])
        else:
            lo = hi = float(rule["start_mg"])
        c.steps.append(msg("step_fixed", lo=fmt(lo), hi=fmt(hi)))
    elif dt == "fixed_daily":
        dlo, dhi = rng(rule["mg_per_day"])
        n = c.n_hi
        lo, hi = dlo / n, dhi / n
        c.steps.append(msg("step_fixed_daily", lo=fmt(dlo), hi=fmt(dhi), n=fmt(n), plo=r3(lo), phi=r3(hi)))
    elif dt == "mg_per_kg_per_dose":
        if "mg_per_kg" not in rule:
            c.refused.append(msg("refused_rule_incomplete", what="mg_per_kg_per_dose rule without mg_per_kg"))
            return c
        klo, khi = rng(rule["mg_per_kg"])
        lo, hi = klo * W, khi * W
        c.steps.append(msg("step_mgkg", mgkg=fmt(klo) if klo == khi else f"{fmt(klo)} to {fmt(khi)}", w=fmt(W), lo=r3(lo), hi=r3(hi)))
        band = _band(rule, W)
        if band is not None and not (lo - 1e-9 <= band["dose_mg"] <= hi + 1e-9):
            c.warnings.append(msg("warn_band_vs_formula", band=fmt(band["dose_mg"]), lo=r3(lo), hi=r3(hi)))
        elif band is not None:
            c.steps.append(msg("step_band", bmin=fmt(band["min_kg"]), bmax=fmt(band.get("max_kg")), d=fmt(band["dose_mg"])))
    elif dt == "mg_per_kg_per_day":
        if "mg_per_kg_per_day" in rule:
            klo, khi = rng(rule["mg_per_kg_per_day"])
        elif di.get("mg_per_kg_per_day") is not None and "max_per_kg_per_day" in rule:
            klo = khi = float(di["mg_per_kg_per_day"])
            if klo > rule["max_per_kg_per_day"] + 1e-9:
                c.refused.append(f"Requested {fmt(klo)} mg/kg/day exceeds the rule's ceiling {fmt(rule['max_per_kg_per_day'])} mg/kg/day.")
                return c
        elif "max_per_kg_per_day" in rule:
            c.needs.append(("mg_per_kg_per_day", msg("need_mg_per_kg_day", cap=fmt(rule["max_per_kg_per_day"]))))
            return c
        else:
            c.refused.append(msg("refused_rule_incomplete", what="mg_per_kg_per_day rule without a mg/kg/day value"))
            return c
        if c.n_hi is None:
            c.needs.append(("doses_per_day", msg("need_doses_per_day")))
            return c
        dlo, dhi = klo * W, khi * W
        lo, hi = dlo / c.n_hi, dhi / c.n_hi
        c.steps.append(msg("step_mgkg_day", mgkg=fmt(klo) if klo == khi else f"{fmt(klo)} to {fmt(khi)}", w=fmt(W),
                           lo=r3(dlo), hi=r3(dhi), n=fmt(c.n_hi), plo=r3(lo), phi=r3(hi)))
    elif dt == "weight_band":
        band = _band(rule, W)
        if band is None:
            c.refused.append(msg("refused_no_band", w=fmt(W)))
            return c
        lo = hi = float(band["dose_mg"])
        c.steps.append(msg("step_band", bmin=fmt(band["min_kg"]), bmax=fmt(band.get("max_kg")) if band.get("max_kg") else "no upper limit", d=fmt(lo)))
        if "mg_per_kg_per_day" in rule and c.n_hi:
            eff = lo * c.n_hi / W
            klo, khi = rng(rule["mg_per_kg_per_day"])
            c.steps.append(msg("step_band_eff", v=r3(eff), w=fmt(W)))
            if not (klo - 1e-9 <= eff <= khi + 1e-9):
                c.warnings.append(msg("warn_band_vs_formula", band=fmt(lo), lo=r3(klo * W / c.n_hi), hi=r3(khi * W / c.n_hi)))
    c.kind = "numeric"

    # -- renal / hepatic adjustments from the engine (parsed from the formulary text; see safety.py)
    if adjust.get("renal_dose"):
        rd = adjust["renal_dose"]
        lo, hi = rd["lo"], rd["hi"]
        if rd.get("interval_h"):
            c.interval_h, c.n_lo, c.n_hi = rd["interval_h"], 24.0 / rd["interval_h"], 24.0 / rd["interval_h"]
        c.steps.append(msg("step_renal_apply", measure=rd["measure"], lo=rd["blo"], hi=rd["bhi"], action=rd["action"]))

    # -- caps, then the percentage reduction
    caps = []        # (name, per-dose cap mg)
    day_caps = []
    src = dict(rule)
    for k, v in _child_defaults(f, drug["id"], rule, ctx, cfg).items():
        src[k] = v
        c.steps.append(msg("step_default_cap", name=f"defaults.{drug['id']}_child.{k}", v=fmt(v)))
    n = c.n_hi
    days_hi = rng(rule["duration_days"])[1] if "duration_days" in rule else None
    if "max_per_dose_mg" in src:
        caps.append((f"max_per_dose_mg {fmt(src['max_per_dose_mg'])}", float(src["max_per_dose_mg"])))
    if "range_mg" in src:
        caps.append((f"range_mg upper {fmt(max(src['range_mg']))}", float(max(src["range_mg"]))))
    if "max_per_kg_per_day" in src and W is not None:
        d = float(src["max_per_kg_per_day"]) * W
        day_caps.append((f"max_per_kg_per_day {fmt(src['max_per_kg_per_day'])} x {fmt(W)} kg = {r3(d)} mg/day", d))
    if "max_per_day_mg" in src:
        day_caps.append((f"max_per_day_mg {fmt(src['max_per_day_mg'])}", float(src["max_per_day_mg"])))
    if adjust.get("max_per_day_mg") is not None:
        day_caps.append((f"hepatic max per day {fmt(adjust['max_per_day_mg'])} mg", float(adjust["max_per_day_mg"])))
    if "max_per_course_mg" in src:
        if n and days_hi:
            caps.append((f"max_per_course_mg {fmt(src['max_per_course_mg'])} over {fmt(n)} x {fmt(days_hi)} d",
                         float(src["max_per_course_mg"]) / (n * days_hi)))
        elif n == 1 and rule.get("single_dose"):
            caps.append((f"max_per_course_mg {fmt(src['max_per_course_mg'])}", float(src["max_per_course_mg"])))
        else:
            c.warnings.append(f"Course cap {fmt(src['max_per_course_mg'])} mg is stated but the course length is not; check manually.")
    if n:
        caps += [(name + f" / {fmt(n)} doses", d / n) for name, d in day_caps]
    elif day_caps:
        c.warnings.append("A daily cap exists but the number of doses per day is unknown; check the daily total manually.")
    c.daily_max_mg = r3(min([d for _, d in day_caps])) if day_caps else None

    before_hi = hi
    if caps:
        name, cap = min(caps, key=lambda t: t[1])
        if cap < hi - 1e-9:
            hi = cap
            lo = min(lo, hi)
            c.binding_cap, c.ceiling = name, cap
            c.steps.append(msg("step_cap", cap=name, before=r3(before_hi), after=r3(hi)))
    if not c.binding_cap:
        c.steps.append(msg("step_cap_none"))
    if adjust.get("reduce_pct"):
        k = (100.0 - adjust["reduce_pct"]) / 100.0
        lo, hi = lo * k, hi * k
        c.steps.append(msg("step_hepatic_apply", action=adjust["reduce_label"]))
        c.ceiling = hi if c.ceiling is None else min(c.ceiling, hi)
        c.binding_cap = c.binding_cap or f"hepatic reduction {fmt(adjust['reduce_pct'])}%"
    c.lo, c.hi = lo, hi
    c.target = (lo + hi) / 2.0
    if n:
        c.daily_lo, c.daily_hi = lo * (c.n_lo or n), hi * n
        c.steps.append(msg("step_daily", lo=r3(c.daily_lo), hi=r3(c.daily_hi)))
    return c


def _band(rule: dict, W: float):
    for b in rule.get("weight_bands") or []:
        mx = b.get("max_kg")
        if W >= b["min_kg"] and (mx is None or W < mx):
            return b
    return None
