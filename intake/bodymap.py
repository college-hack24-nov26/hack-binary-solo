"""Body map: region catalog, canonical answer, point-in-polygon hit-testing and SVG drawing.

'right' / 'left' always mean the PATIENT's own side. On the front view the patient's right is on the
viewer's left; on the back view it is on the viewer's right. Pure functions, no I/O after load."""
import json
from functools import lru_cache
from html import escape
from math import hypot
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict

from .models import LANGS, ROOT, TRANSLATION_STATUS

REGIONS_PATH = ROOT / "data" / "body_regions.json"
View = Literal["front", "back"]
SPECIALS = ("tell_doctor", "none")        # besides "I'm not sure", which is the ordinary UNSURE answer


class Region(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    view: View
    side: Literal["right", "left", "center"]
    en: str
    hi: str
    mr: str
    translationStatus: str = TRANSLATION_STATUS
    polygon: list[list[float]]

    def label(self, lang: str) -> str:
        return getattr(self, lang if lang in LANGS else "en") or self.en


class Catalog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: Optional[str] = None
    viewBox: list[int]
    sideLabels: dict[str, dict[str, str]]
    viewLabels: dict[str, dict[str, str]]
    translationStatus: str
    regions: list[Region]

    def __init__(self, **kw):
        kw["note"] = kw.pop("_note", None)
        super().__init__(**kw)


@lru_cache(maxsize=1)
def catalog(path: str = str(REGIONS_PATH)) -> Catalog:
    return Catalog(**json.loads(Path(path).read_text(encoding="utf-8")))


def region_ids() -> list[str]:
    return [r.id for r in catalog().regions]


def region(rid: str) -> Region:
    return next(r for r in catalog().regions if r.id == rid)


def regions_in_view(view: str) -> list[Region]:
    return [r for r in catalog().regions if r.view == view]


# ------------------------------------------------------------------ answers
def make_answer(regions: list[str], input_mode: str, special: Optional[str] = None) -> dict:
    """The ONE place a body-map answer is built, for both the map and the list. Regions are put in
    catalog order and `view` is the view of the first region (front when there are none), so the same
    selection gives the same regions and view whichever input produced it."""
    order = {r: i for i, r in enumerate(region_ids())}
    bad = [r for r in regions if r not in order]
    if bad:
        raise ValueError(f"unknown regions: {bad}")
    regs = sorted(set(regions), key=order.__getitem__)
    ans: dict[str, Any] = {"regions": regs, "view": region(regs[0]).view if regs else "front", "inputMode": input_mode}
    if special:
        ans["special"] = special
    return ans


def check_answer(ans: Any, max_selections: int, allowed_specials: set[str]) -> None:
    """Raise ValueError unless ans is a canonical body-map answer."""
    if not isinstance(ans, dict) or not {"regions", "view", "inputMode"} <= set(ans) <= {"regions", "view", "inputMode", "special"}:
        raise ValueError("body map answer needs regions, view, inputMode")
    if ans["inputMode"] not in ("map", "list"):
        raise ValueError("inputMode must be map or list")
    if not isinstance(ans["regions"], list):
        raise ValueError("regions must be a list")
    special = ans.get("special")
    if special is not None and (special not in allowed_specials or ans["regions"]):
        raise ValueError(f"special {special!r} not allowed here, or combined with regions")
    if special is None and not ans["regions"]:
        raise ValueError("select at least one region, or choose another option")
    if len(ans["regions"]) > max_selections:
        raise ValueError(f"at most {max_selections} regions")
    if ans != make_answer(ans["regions"], ans["inputMode"], special):
        raise ValueError("answer is not in canonical form (use make_answer)")


def regions_text(regions: list[str], lang: str = "en") -> str:
    return "; ".join(region(r).label(lang) for r in regions)


# ------------------------------------------------------------------ geometry
def point_in_polygon(x: float, y: float, poly: list[list[float]]) -> bool:
    inside = False
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _dist_to_polygon(x: float, y: float, poly: list[list[float]]) -> float:
    best = float("inf")
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        dx, dy = x2 - x1, y2 - y1
        t = 0 if dx == dy == 0 else max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
        best = min(best, hypot(x - (x1 + t * dx), y - (y1 + t * dy)))
    return best


def hit_test(view: str, x: float, y: float, slop: float = 0.0) -> Optional[str]:
    """Region id under (x, y) in viewBox units. With slop > 0, a tap that lands in a gap resolves to the
    nearest region within `slop` units (forgiving for fingers)."""
    rs = regions_in_view(view)
    for r in rs:
        if point_in_polygon(x, y, r.polygon):
            return r.id
    if slop > 0:
        d, rid = min((_dist_to_polygon(x, y, r.polygon), r.id) for r in rs)
        if d <= slop:
            return rid
    return None


def centroid(poly: list[list[float]]) -> tuple[float, float]:
    return sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly)


# ------------------------------------------------------------------ drawing
COLORS = {"sel": "#d62828", "site": "#d62828", "radiation": "#f77f00"}


def render_svg(view: str, groups: Optional[dict[str, list[str]]] = None, lang: str = "en", width: int = 300) -> str:
    """Self-contained SVG (no external files). groups maps a colour key (sel/site/radiation) to region ids.
    Each region is a <polygon data-region=ID> so the same markup serves the tap component and the doctor diagram."""
    c = catalog()
    w, h = c.viewBox
    color_of = {rid: COLORS[k] for k, ids in (groups or {}).items() for rid in ids}
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h + 16}" width="{width}" role="img" '
             f'aria-label="{escape(c.viewLabels[view][lang])}" style="max-width:100%;height:auto;touch-action:manipulation">']
    for r in regions_in_view(view):
        fill = color_of.get(r.id, "#f1f3f5")
        pts = " ".join(f"{x:g},{y:g}" for x, y in r.polygon)
        parts.append(f'<polygon data-region="{r.id}" points="{pts}" fill="{fill}" fill-opacity="{0.85 if r.id in color_of else 1}" '
                     f'stroke="#495057" stroke-width="1.2" stroke-linejoin="round"><title>{escape(r.label(lang))}</title></polygon>')
    viewer_left = "right" if view == "front" else "left"        # whose side is on the viewer's left
    viewer_right = "left" if view == "front" else "right"
    sl = c.sideLabels
    parts.append(f'<text x="2" y="{h + 12}" font-size="10" fill="#212529">{escape(sl[viewer_left][lang])}</text>')
    parts.append(f'<text x="{w - 2}" y="{h + 12}" font-size="10" text-anchor="end" fill="#212529">{escape(sl[viewer_right][lang])}</text>')
    parts.append("</svg>")
    return "".join(parts)
