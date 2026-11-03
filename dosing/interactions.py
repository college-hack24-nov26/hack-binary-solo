"""Interaction checks from the formulary: top-level interactions[] (structured severity) and each drug's own
interactions (free text, severity 'unspecified'). Targets: current medicines (free text, normalised), other drugs
prescribed in the same visit, and context flags. Duplicate therapy is by duplicate_class."""
import re

from . import meds as medsmod
from .formulary import Formulary, norm_status
from .messages import msg

BLOCK_SEVERITIES = {"block", "contraindicated"}      # engine policy: these severities are hard stops (overridable)
_ALLERGY_CLASSES = ("penicillins", "sulfa", "nsaids")


def _split(b: str) -> list[str]:
    parts, depth, cur = [], 0, ""
    for ch in b:
        depth += (ch == "(") - (ch == ")")
        if ch in ",;" and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    out = []
    for p in parts:
        for q in re.split(r"\s+or\s+", p.strip()):
            q = q.strip()
            if q:
                out.append("qt-prolonging" if "qt" in medsmod.canon(q).split() else q)
    return out


def _head(text: str) -> list[str]:
    h = text.split(":")[0] if ":" in text else text
    return _split(h)


def drug_labels(f: Formulary, drug: dict) -> list:
    labs = medsmod.labels_for_drug(drug["id"]) + [drug["id"].replace("_", " "), drug["duplicate_class"]]
    labs += [w for w in re.split(r"[^a-z]+", drug["generic"].lower()) if len(w) > 3 and w not in ("acid", "and")]
    if drug.get("qt_risk"):
        labs.append("qt-prolonging")
    return labs


def targets(f: Formulary, ctx, visit_ids: list) -> list:
    t = []
    for m in ctx.all_meds():
        origins = [{"source": m.source, "scan_ref": m.scan_ref, "scan_date": m.scan_date}] + list(m.also)
        t.append({"name": m.raw or m.matched_name, "labels": m.labels + [m.matched_name, m.generic], "src": "current_medicine",
                  "herbal": m.kind == "herbal", "drug_id": m.drug_id, "origins": origins})
    for did in visit_ids:
        d = f.drugs[did]
        t.append({"name": d["id"], "labels": drug_labels(f, d), "src": "same_visit", "herbal": False, "drug_id": did})
    if ctx.tri("alcohol") == "yes":
        t.append({"name": "alcohol use (quiz)", "labels": ["alcohol"], "src": "patient_context", "herbal": False, "drug_id": None})
    if ctx.tri("qt_history") == "yes":
        t.append({"name": "QT history (doctor)", "labels": ["qt-prolonging"], "src": "patient_context", "herbal": False, "drug_id": None})
    return t


def _with(tg: dict) -> dict:
    """'with' text and origins for an interaction entry. Medicines read from a confirmed scan carry a 'from scanned prescription (date)' tag."""
    origins = tg.get("origins") or []
    scans = [o for o in origins if o["source"] == "ocr_doctor_confirmed"]
    if not scans:
        return {"with": f"{tg['name']} ({tg['src'].replace('_', ' ')})", "origins": origins}
    tag = "; ".join(f"from scanned prescription ({o['scan_date'] or 'date not read'})" for o in scans)
    others = [o for o in origins if o["source"] != "ocr_doctor_confirmed"]
    return {"with": f"{tg['name']} ({'patient-reported, ' if others else ''}{tag})", "origins": origins}


def _hit(terms: list, tgts: list):
    out = []
    for tg in tgts:
        for term in terms:
            if medsmod.term_matches(term, tg["labels"]) or any(medsmod.term_matches(l, [term]) for l in tg["labels"]):
                out.append((tg, term))
                break
    return out


def check(f: Formulary, drug: dict, ctx, visit_ids: list) -> dict:
    labels = drug_labels(f, drug)
    tgts = [t for t in targets(f, ctx, visit_ids) if t["drug_id"] != drug["id"] or t["src"] == "current_medicine"]
    items: dict = {}
    warnings: list = []
    cls_row = {}

    def put(key, it):
        if key in items:
            items[key]["details"] += it["details"]
            return
        items[key] = it

    for row in f.interactions:
        a, b = row["a"], row["b"]
        sev = row["severity"]
        st = norm_status(row.get("status"))
        base = {"severity": sev, "action": row["action"], "data_status": st,
                "sources": f.source_refs(row.get("source"), st), "details": [],
                "blocking": sev in BLOCK_SEVERITIES}
        if a.startswith("class:") and b == a:
            cls_row[medsmod.canon(a)] = row
            continue
        if a.startswith("allergy:"):
            cls = next((c for c in _ALLERGY_CLASSES if medsmod.canon(c) == medsmod.canon(a)), None)
            if cls and ctx.tri(f"allergy_{cls}") == "yes" and medsmod.term_matches(b, labels):
                put(("allergy", cls), {**base, "kind": "allergy", "with": f"allergy to {cls} (quiz)", "label": row["action"]})
            continue
        a_terms, b_terms = _split(a), _split(b)
        a_hits_drug = medsmod.term_matches(a, labels) or a == drug["id"] or (a.startswith("flag:qt_risk") and drug.get("qt_risk"))
        if a_hits_drug:
            for tg, term in _hit(b_terms, tgts):
                put((tg["name"], term), {**base, "kind": "drug_drug", **_with(tg),
                                          "label": row["action"], "matched": term})
        if any(medsmod.term_matches(t, labels) or (t == "qt-prolonging" and drug.get("qt_risk")) for t in b_terms) \
                and not a.startswith("flag:"):
            for tg, term in _hit([a], tgts):
                put((tg["name"], a), {**base, "kind": "drug_drug", **_with(tg),
                                       "label": row["action"], "matched": a})

    # drug-level free-text interactions: severity not given by the formulary
    for e in drug.get("interactions") or []:
        st = norm_status(e.get("status"))
        for tg, term in _hit(_head(e["text"]), tgts):
            it = {"severity": "unspecified", "action": e["text"], "data_status": st, "sources": f.source_refs(e.get("source"), st),
                  "details": [e["text"]], "blocking": False, "kind": "drug_drug", **_with(tg),
                  "label": e["text"], "matched": term}
            put((tg["name"], term), it)

    # duplicate therapy by duplicate_class (and the same drug twice)
    dup = medsmod.canon(drug["duplicate_class"])
    for tg in tgts:
        if tg["src"] == "patient_context":
            continue
        same_drug = tg["drug_id"] == drug["id"]
        same_class = any(medsmod.canon(l) == dup for l in tg["labels"])
        if same_drug or same_class:
            row = cls_row.get(f"{dup}") or cls_row.get(medsmod.canon("class:" + drug["duplicate_class"]))
            sev = row["severity"] if row else "unspecified"
            st = norm_status(row.get("status")) if row else "UNVERIFIED"
            put(("dup", tg["name"]), {"severity": sev, "action": row["action"] if row else "Duplicate therapy (no severity in the formulary)",
                                      "data_status": st, "sources": f.source_refs(row.get("source") if row else "", st), "details": [],
                                      "blocking": sev in BLOCK_SEVERITIES, "kind": "duplicate",
                                      **_with(tg), "label": "Duplicate therapy", "class": drug["duplicate_class"]})

    for tg in tgts:
        if tg.get("herbal"):
            warnings.append({"code": "warn_herbal", "text": msg("warn_herbal", tok=tg["name"])})
    for tok in ctx.unparsed_meds:
        warnings.append({"code": "warn_unparsed_med", "text": msg("warn_unparsed_med", tok=tok)})
    for u in ctx.ocr_unparsed:
        warnings.append({"code": "warn_unparsed_ocr_med", "text": msg("warn_unparsed_ocr_med", tok=u["token"], date=u["scan_date"] or "not read"),
                         "scan_ref": u["scan_ref"]})
    if ctx.get("meds_known") != "yes":
        warnings.append({"code": "warn_meds_incomplete", "text": msg("warn_meds_incomplete")})
    return {"items": [items[k] for k in sorted(items, key=lambda k: str(k))], "warnings": warnings,
            "incomplete": ctx.get("meds_known") != "yes"}
