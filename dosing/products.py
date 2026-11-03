"""Rounding a dose to products on the Indian list (forms_india). Whole tablets only unless the data says scored."""
import math
import re
from dataclasses import dataclass, field

ORAL = {"tablet", "capsule", "modified-release tablet", "oral liquid", "dry syrup"}
PARENTERAL = {"injection", "powder for injection"}
RECTAL = {"suppository"}
LIQUID_FORMS = {"oral liquid", "dry syrup"}
_TOKEN = re.compile(r"(\d+(?:\.\d+)?)\s*(mg|g)\b")


def form_class(form: str) -> str:
    return "oral" if form in ORAL else "parenteral" if form in PARENTERAL else "rectal"


@dataclass
class Product:
    form: str
    strength: str
    comps: list            # amounts in mg per unit (solid) or per mL (liquid); comps[0] is the primary component
    liquid: bool
    scored: bool = False
    label: str = ""

    @property
    def key(self) -> str:
        """'200/28.5'-style ratio key for amoxicillin-clavulanate matching (per unit or per 5 mL)."""
        per = 5.0 if (self.liquid and self.strength.rstrip().endswith("5 mL")) else 1.0
        return "/".join(f"{c * per:g}" for c in self.comps)


def parse_product(entry: dict) -> Product:
    s = entry["strength"]
    comps = [float(n) * (1000.0 if u == "g" else 1.0) for n, u in _TOKEN.findall(s)]
    vol = re.search(r"/\s*(\d+(?:\.\d+)?)?\s*mL", s)
    liquid = bool(vol) or entry["form"] in LIQUID_FORMS
    if vol:
        ml = float(vol.group(1) or 1)
        comps = [c / ml for c in comps]               # mg per mL
    return Product(entry["form"], s, comps, liquid, bool(entry.get("scored")), f"{entry['form']} {s}")


def products_for(drug: dict, route_class: str | None) -> list:
    out = []
    for e in drug["forms_india"]:
        if route_class and form_class(e["form"]) != route_class:
            continue
        out.append(parse_product(e))
    return out


def _r(x, n=3):
    return round(x, n)


@dataclass
class Option:
    product: str
    form: str
    units: float | None        # whole units (solid) or None
    volume_ml: float | None
    delivered_mg: float
    in_range: bool
    note: str = ""
    ratio_mismatch: bool = False
    steps: list = field(default_factory=list)

    def as_dict(self):
        return {"product": self.product, "form": self.form, "units": self.units, "volume_ml": self.volume_ml,
                "delivered_mg": _r(self.delivered_mg), "in_range": self.in_range, "note": self.note,
                "ratio_mismatch": self.ratio_mismatch}


def deliver(p: Product, lo: float, hi: float, target: float, ceiling: float | None, ml_step: float,
            ratio_mismatch: bool = False) -> list:
    """Candidate deliveries for one product. Never exceeds `ceiling` (a bound cap). in_range is relative to [lo, hi];
    liquids allow half a rounding step of slack because the dose is rounded to a measurable volume."""
    c0 = p.comps[0]
    out = []
    if p.liquid:
        mg_ml = c0
        raw = target / mg_ml
        cands = {math.floor(raw / ml_step) * ml_step, math.ceil(raw / ml_step) * ml_step}
        slack = ml_step * mg_ml / 2
        for v in sorted(cands):
            if v <= 0:
                continue
            d = v * mg_ml
            if ceiling is not None and d > ceiling + 1e-9:
                continue
            ok = lo - slack - 1e-9 <= d <= hi + slack + 1e-9
            out.append(Option(p.label, p.form, None, _r(v), d, ok, ratio_mismatch=ratio_mismatch))
    else:
        raw = target / c0
        unit_choices = {math.floor(raw), math.ceil(raw)}
        if p.scored:
            unit_choices |= {math.floor(raw * 2) / 2, math.ceil(raw * 2) / 2}
        for u in sorted(unit_choices):
            if u <= 0:
                continue
            d = u * c0
            if ceiling is not None and d > ceiling + 1e-9:
                continue
            ok = lo - 1e-9 <= d <= hi + 1e-9
            out.append(Option(p.label, p.form, u, None, d, ok, ratio_mismatch=ratio_mismatch))
    return out


def choose(options: list, target: float):
    """Best in-range option: a solid form if any is in range (liquids when nothing solid fits), then closest to the
    target, then fewest units / least volume, then label for a stable tie-break."""
    ok = [o for o in options if o.in_range]
    key = lambda o: (o.volume_ml is not None, round(abs(o.delivered_mg - target), 6), o.volume_ml or o.units or 0, o.product)
    return (sorted(ok, key=key)[0] if ok else None), sorted(options, key=key)
