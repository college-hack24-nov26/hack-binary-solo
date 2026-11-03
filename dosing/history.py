"""History check: the yes / no / unsure facts the selected drug's contraindications and warnings depend on.
Questions that come from a contraindication quote the formulary's exact text. Nothing here is defaulted: an item that
is not answered stays unknown, and unknown is never treated as no."""
import re
from dataclasses import dataclass

from . import safety
from .formulary import Formulary
from .meds import canon

LABELS = {
    "allergy_penicillins": "Allergy to penicillins / beta-lactams", "allergy_nsaids": "Allergy to NSAIDs (ibuprofen, diclofenac, aspirin)",
    "allergy_sulfa": "Allergy to sulfa medicines", "ulcer": "Peptic ulcer history", "gi_bleed": "GI bleeding (vomiting blood or black stools)",
    "alcohol": "Drinks alcohol", "kidney_disease": "Kidney disease", "liver_disease": "Liver disease", "diabetes": "Diabetes",
    "hypertension": "High blood pressure", "asthma": "Asthma", "pregnant": "Pregnant", "lactating": "Breastfeeding",
    "qt_history": "QT-interval problem (long QT, QT drugs)", "heart_disease": "Heart disease"}


@dataclass
class Item:
    field: str
    label: str
    question: str          # the exact formulary text for contraindication questions, else a plain question
    value: str             # yes | no | unsure | unknown
    prov: str
    required: bool = False
    source: str = ""

    def as_dict(self):
        return self.__dict__.copy()


def _value(ctx, field: str) -> str:
    v = ctx.get(field)
    if field == "pregnant":
        return {"yes": "yes", "no": "no", "possible": "unsure"}.get(v, "unknown")
    if v in ("yes", "no", "unsure"):
        return v
    return "unknown"


def items_for(f: Formulary, drug: dict, ctx) -> list[Item]:
    sm = safety.smap()
    out: dict[str, Item] = {}

    def add(field, label=None, question=None, required=False, source=""):
        if field not in out:
            out[field] = Item(field, label or LABELS.get(field, field), question or f"{label or LABELS.get(field, field)}?",
                              _value(ctx, field), ctx.prov(field), required, source)

    seen = set()
    for e in list(drug.get("contraindications") or []) + list(drug.get("block_rules") or []):
        text = e["text"]
        if text in seen:
            continue
        seen.add(text)
        pred, _ = safety._match_ci(text)
        kinds = [pred] + (pred.get("of", []) if pred["kind"] == "any" else [])
        for p in kinds:
            k = p["kind"]
            if k == "allergy":
                add(f"allergy_{p['class']}")
            elif k == "ctx_yes":
                for fld in p["fields"]:
                    add(fld)
            elif k == "pregnant":
                add("pregnant")
            elif k == "hint":
                for fld in p["fields"]:
                    add(fld)
            elif k == "question":
                add(safety.qfield(text), "Contraindication in the formulary", f"\"{text}\" - does this apply?",
                    bool(p.get("required")), str(e.get("source", "")))
    texts = [w["text"] for w in (drug.get("warnings") or []) + (drug.get("interactions") or [])]
    for trig in sm["warning_triggers"]:
        if any(re.search(trig["regex"], t, re.I) for t in texts):
            add(trig["field"])
    if any(r.get("min") is not None or r.get("max") is not None for r in drug.get("renal_rules") or []):
        add("kidney_disease")
    if drug.get("hepatic_rules"):
        add("liver_disease")
    if drug.get("pregnancy") or drug.get("pregnancy_additional"):
        add("pregnant")
    ltxt = [x.get("text", "") for x in [drug.get("lactation")] if x] + [x.get("text", "") for x in drug.get("lactation_additional") or []]
    if any(re.search(sm["lactation_against_regex"], t, re.I) for t in ltxt):
        add("lactating")
    if drug.get("qt_risk"):
        add("qt_history")
    if ctx.get("sex") == "male" or ctx.prov("pregnant") == "derived":
        out.pop("pregnant", None)           # derived 'no' from the quiz's own age/sex gate is not asked again
        if ctx.get("sex") == "male":
            out.pop("lactating", None)
    return sorted(out.values(), key=lambda i: (not i.required, i.field))


def unknown_items(items: list[Item]) -> list[Item]:
    return [i for i in items if i.value in ("unknown", "unsure")]
