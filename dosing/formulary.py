"""Load, validate and index the formulary JSON (read-only; never modified)."""
import hashlib
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

STATUSES = ("VERIFIED", "SECONDARY", "UNVERIFIED")

SUPPORTED_DOSE_TYPES = {"fixed", "fixed_daily", "mg_per_kg_per_dose", "mg_per_kg_per_day", "weight_band", "titration",
                        "duration_only"}
# every key a dose rule may carry; each is either used by calc.py or shown as information
RULE_FIELDS = {
    "indication", "population", "dose_type", "source", "status", "note", "conflict", "route",
    "dose_mg", "start_mg", "range_mg", "mg_per_kg", "mg_per_kg_per_day", "mg_per_day", "weight_bands", "options",
    "doses_per_day", "interval_h", "min_interval_h", "single_dose", "doses",
    "max_per_dose_mg", "max_per_day_mg", "max_per_kg_per_day", "max_per_course_mg", "max_doses_per_day",
    "max_tablets_per_day", "duration_days", "duration_weeks", "max_duration_days", "duration_days_otitis",
    "start", "step", "schedule", "product"}
POPULATION_FIELDS = {"min_age_years", "max_age_years", "min_age_months", "max_age_months", "min_age_weeks",
                     "max_age_weeks", "max_age_days", "min_weight_kg", "max_weight_kg"}
DRUG_FIELDS = {"id", "generic", "class", "atc", "rxcui", "forms_india", "dose_rules", "renal_rules", "hepatic_rules",
               "contraindications", "warnings", "pregnancy", "lactation", "food", "interactions", "duplicate_class",
               "gaps", "verified", "reviewed_by", "review_date", "pregnancy_additional", "lactation_additional",
               "jan_aushadhi", "nppa_ceiling_price", "nppa_ceiling_price_note", "block_rules", "qt_risk", "dose_basis",
               "adult_switch", "duration_limits", "forms_note", "food_additional", "override_rules"}
RENAL_FIELDS = {"measure", "min", "max", "action", "source", "status", "conflict", "note"}
HEPATIC_FIELDS = {"text", "source", "status", "conflict", "measure", "class", "action", "note", "min"}
TEXT_FIELDS = {"text", "source", "status", "conflict", "note"}
FORM_FIELDS = {"form", "strength", "level", "source", "scored", "note"}
TOP_FIELDS = {"meta", "sources", "formulas", "defaults", "drugs", "interactions"}
INTERACTION_FIELDS = {"a", "b", "severity", "action", "source", "status", "note", "conflict"}
KNOWN_FORMS = {"tablet", "capsule", "modified-release tablet", "oral liquid", "dry syrup", "injection",
               "powder for injection", "suppository"}
_STRENGTH_RE = re.compile(r"^\s*\d+(\.\d+)?\s*(mg|g)(\s*\+\s*\d+(\.\d+)?\s*(mg|g))?(\s*/\s*(\d+(\.\d+)?\s*)?mL)?\s*$")
RENAL_MEASURE_RE = re.compile(r"^\s*(CrCl|eGFR|GFR)\b", re.I)


def norm_status(s) -> str:
    """VERIFIED / SECONDARY / UNVERIFIED. Anything else (e.g. a mixed note) counts as the weakest it mentions."""
    s = str(s or "")
    if s in STATUSES:
        return s
    if "UNVERIFIED" in s or not s:
        return "UNVERIFIED"
    return "SECONDARY" if "SECONDARY" in s else "UNVERIFIED"


def rule_hash(rule: dict) -> str:
    return hashlib.sha256(json.dumps(rule, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:10]


@dataclass
class Formulary:
    raw: dict
    path: str = ""
    drugs: dict = field(default_factory=dict)          # id -> drug dict

    @property
    def version(self) -> str:
        return self.raw["meta"]["version"]

    @property
    def sources(self) -> dict:
        return self.raw["sources"]

    @property
    def formulas(self) -> dict:
        return self.raw["formulas"]

    @property
    def defaults(self) -> dict:
        return self.raw["defaults"]

    @property
    def interactions(self) -> list:
        return self.raw["interactions"]

    def find_drug(self, name: str):
        n = re.sub(r"[\s_\-]+", " ", (name or "").lower()).strip()
        for d in self.drugs.values():
            gen = d["generic"].lower()
            names = {d["id"].replace("_", " "), gen, re.sub(r"\s*\(.*?\)", "", gen).strip()}
            names |= {x.strip() for x in re.findall(r"\(([^)]*)\)", gen)}
            names.add(gen.replace(" + ", " ").replace("clavulanic acid", "clavulanate"))
            if n in {re.sub(r"[\s_\-]+", " ", x) for x in names}:
                return d
        return None

    def rule_id(self, drug_id: str, i: int) -> str:
        return f"{drug_id}#{i}"

    def rule(self, rid: str):
        did, i = rid.split("#")
        return self.drugs[did], self.drugs[did]["dose_rules"][int(i)]

    def source_refs(self, source_text: str, status: str) -> list[dict]:
        """Parse 'S2 Table 4.4', 'S6; S8 6693/4590 sec 4.2', '... [S19]' into [{id,name,url,section,status}]."""
        text = str(source_text or "")
        ids = []
        for m in re.finditer(r"\b(S\d+|AAPD|HPRA)\b", text):
            if m.group(1) in self.sources and m.group(1) not in ids:
                ids.append(m.group(1))
        url = (re.findall(r"https?://[^\s\]\)]+", text) or [None])[0]
        if not ids:
            return [{"id": None, "name": re.sub(r"https?://\S+", "", text).strip(" ;[]") or "no source text", "url": url,
                     "section": text, "status": status}]
        return [{"id": i, "name": self.sources[i]["name"], "url": self.sources[i].get("url") or url,
                 "section": text, "status": status} for i in ids]


def validate(raw: dict) -> list[str]:
    """Every dose_type, key, measure or form shape the engine does not handle. Empty list = fully supported."""
    out: list[str] = []
    if set(raw) - TOP_FIELDS:
        out.append(f"unknown top-level keys {sorted(set(raw) - TOP_FIELDS)}")
    for k in ("meta", "sources", "formulas", "defaults", "drugs", "interactions"):
        if k not in raw:
            out.append(f"missing top-level '{k}'")
    for e in raw.get("interactions", []):
        if set(e) - INTERACTION_FIELDS:
            out.append(f"interaction {e.get('a')}/{e.get('b')}: unknown keys {sorted(set(e) - INTERACTION_FIELDS)}")
    for d in raw.get("drugs", []):
        did = d.get("id", "?")
        if set(d) - DRUG_FIELDS:
            out.append(f"{did}: unknown drug keys {sorted(set(d) - DRUG_FIELDS)}")
        for f in d.get("forms_india", []):
            if set(f) - FORM_FIELDS:
                out.append(f"{did}: unknown form keys {sorted(set(f) - FORM_FIELDS)}")
            if f.get("form") not in KNOWN_FORMS:
                out.append(f"{did}: unsupported form '{f.get('form')}'")
            if not _STRENGTH_RE.match(f.get("strength", "")):
                out.append(f"{did}: unparseable strength '{f.get('strength')}'")
        for i, r in enumerate(d.get("dose_rules", [])):
            w = f"{did}#{i}"
            if r.get("dose_type") not in SUPPORTED_DOSE_TYPES:
                out.append(f"{w}: unsupported dose_type '{r.get('dose_type')}'")
            if set(r) - RULE_FIELDS:
                out.append(f"{w}: unknown rule fields {sorted(set(r) - RULE_FIELDS)}")
            if set(r.get("population") or {}) - POPULATION_FIELDS:
                out.append(f"{w}: unknown population keys {sorted(set(r['population']) - POPULATION_FIELDS)}")
            for b in r.get("weight_bands") or []:
                if set(b) - {"min_kg", "max_kg", "dose_mg"}:
                    out.append(f"{w}: unknown weight_band keys {sorted(set(b) - {'min_kg', 'max_kg', 'dose_mg'})}")
            for o in r.get("options") or []:
                if isinstance(o, dict) and set(o) - {"mg_per_kg_per_day", "doses_per_day", "products"}:
                    out.append(f"{w}: unknown option keys {sorted(set(o) - {'mg_per_kg_per_day', 'doses_per_day', 'products'})}")
                elif not isinstance(o, (dict, str)):
                    out.append(f"{w}: unsupported option shape {type(o).__name__}")
        for sec, allowed in (("renal_rules", RENAL_FIELDS), ("hepatic_rules", HEPATIC_FIELDS),
                             ("contraindications", TEXT_FIELDS), ("warnings", TEXT_FIELDS),
                             ("interactions", TEXT_FIELDS), ("block_rules", TEXT_FIELDS),
                             ("pregnancy_additional", TEXT_FIELDS), ("lactation_additional", TEXT_FIELDS)):
            for e in d.get(sec) or []:
                if set(e) - allowed:
                    out.append(f"{did}.{sec}: unknown keys {sorted(set(e) - allowed)}")
        for e in d.get("renal_rules", []):
            m = e.get("measure", "")
            if (e.get("min") is not None or e.get("max") is not None) and not RENAL_MEASURE_RE.match(m):
                out.append(f"{did}.renal_rules: numeric band with unsupported measure '{m}'")
    return sorted(set(out))


@lru_cache(maxsize=4)
def _load(path: str) -> Formulary:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    f = Formulary(raw=raw, path=path, drugs={d["id"]: d for d in raw["drugs"]})
    return f


def load(path) -> Formulary:
    return _load(str(path))


def check_at_startup(f: Formulary, strict: bool = False) -> list[str]:
    """Dev: raise on unsupported shapes (strict). Prod: log and continue; unsupported rules then refuse at use."""
    issues = validate(f.raw)
    if issues and strict:
        raise ValueError("formulary has shapes the engine does not support:\n" + "\n".join(issues))
    return issues
