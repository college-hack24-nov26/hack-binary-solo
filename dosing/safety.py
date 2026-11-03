"""Contraindications, renal / hepatic / pregnancy / lactation rules and label warnings, evaluated against the
PatientContext. The formulary holds these as free text; data/safety_map.json maps each text to a predicate (numbers are
captured from the text itself). Text without a mapping is surfaced as 'doctor to confirm', never dropped."""
import hashlib
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from . import derived, meds as medsmod
from .formulary import Formulary, norm_status, RENAL_MEASURE_RE
from .messages import msg
from .rules import UNIT_DAYS

MAP = Path(__file__).resolve().parent / "data" / "safety_map.json"


@lru_cache(maxsize=1)
def smap() -> dict:
    return json.loads(MAP.read_text(encoding="utf-8"))


def qfield(text: str) -> str:
    """Context field that holds the doctor's yes/no/unsure answer to a contraindication text."""
    return "q_" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


@dataclass
class Out:
    blocks: list = field(default_factory=list)      # overridable hard stops
    warnings: list = field(default_factory=list)
    label_warnings: list = field(default_factory=list)
    needs: list = field(default_factory=list)       # [(field, message)]
    steps: list = field(default_factory=list)
    renal_dose: dict | None = None
    renal_unapplied: list = field(default_factory=list)
    adjust: dict = field(default_factory=dict)
    renal_values: dict = field(default_factory=dict)
    needs_scr: bool = False


def item(f: Formulary, code: str, text: str, entry: dict | None = None, **extra) -> dict:
    d = {"code": code, "text": text}
    if entry is not None:
        st = norm_status(entry.get("status"))
        d["data_status"] = st
        d["sources"] = f.source_refs(entry.get("source"), st)
        if entry.get("conflict"):
            d["conflict"] = entry["conflict"]
    d.update(extra)
    return d


# ---------------------------------------------------------------------------------------------------------- predicates
def _meds_labels(ctx, visit_labels) -> list:
    return [m.labels + [m.matched_name, m.generic] for m in ctx.all_meds()] + list(visit_labels)


def eval_pred(pred: dict, groups: tuple, ctx, drug: dict, visit_labels: list, egfr_fn, form: str | None, text: str = ""):
    """-> (state, needs, note). state: true | false | unknown | warn | manual."""
    k = pred["kind"]
    needs: list = []
    if k == "manual":
        return "manual", needs, ""
    if k == "question":
        v = ctx.get(qfield(text))
        if v == "yes":
            return "true", needs, ""
        if v == "no":
            return "false", needs, ""
        if pred.get("required"):                       # unanswered or 'unsure': never treated as no
            return "unknown", [(qfield(text), msg("need_question", text=text))], ""
        return "manual", needs, ""
    if k == "any":
        states = [eval_pred(p, groups, ctx, drug, visit_labels, egfr_fn, form, text) for p in pred["of"]]
        for s, n, _ in states:
            needs += n
        if any(s == "true" for s, _, _ in states):
            return "true", [], ""
        if any(s == "warn" for s, _, _ in states):
            return "warn", [], ""
        return ("unknown", needs, "") if any(s == "unknown" for s, _, _ in states) else ("false", [], "")
    if k == "allergy":
        t = ctx.tri(f"allergy_{pred['class']}")
        if t == "unknown":
            return "unknown", [(f"allergy_{pred['class']}", msg("need_allergy", what=pred["class"]))], ""
        return ("true" if t == "yes" else "false"), needs, ""
    if k in ("age_lt", "form_age_lt"):
        if k == "form_age_lt" and form is not None and form != pred["form"]:
            return "false", needs, ""
        n = float(groups[pred["n"] - 1])
        bound = n * UNIT_DAYS[pred["unit"]]
        lo, hi = ctx.age_days()
        if lo is None:
            return "unknown", [("age_months", msg("need_age"))], ""
        if hi - 1e-6 < bound:
            young = True
        elif lo >= bound:
            young = False
        else:
            return "unknown", [("age_exact", msg("need_age_exact", lo=round(lo / UNIT_DAYS["months"], 1),
                                                  hi=round(hi / UNIT_DAYS["months"], 1), why=f"age < {n:g} {pred['unit']}"))], ""
        if k == "form_age_lt":
            return ("true" if young else "false") if form == pred["form"] else ("warn" if young else "false"), needs, ""
        return ("true" if young else "false"), needs, ""
    if k == "pregnant":
        p = ctx.get("pregnant")
        if p in ("yes", "possible"):
            return "true", needs, "possible" if p == "possible" else ""
        if p == "no":
            return "false", needs, ""
        return "unknown", [("pregnant", msg("need_pregnant", why="contraindication in pregnancy"))], ""
    if k in ("trimester", "weeks_ge"):
        p = ctx.get("pregnant")
        if p == "no":
            return "false", needs, ""
        if p is None:
            return "unknown", [("pregnant", msg("need_pregnant", why="trimester / weeks rule"))], ""
        if p == "possible":
            return "warn", needs, "possible"
        if k == "trimester":
            tri = ctx.get("pregnancy_trimester")
            if tri is None:
                return "unknown", [("pregnancy_trimester", msg("need_trimester", why="trimester rule"))], ""
            return ("true" if int(tri) == pred["n"] else "false"), needs, ""
        wk = ctx.get("pregnancy_weeks")
        if wk is None:
            return "unknown", [("pregnancy_weeks", msg("need_weeks", why="weeks-of-pregnancy rule"))], ""
        return ("true" if wk >= float(groups[pred["n"] - 1]) else "false"), needs, ""
    if k == "ctx_yes":
        ts = {fld: ctx.tri(fld) for fld in pred["fields"]}
        if "yes" in ts.values():
            return ("warn" if pred.get("on_true") == "warn" else "true"), needs, ""
        unk = [fld for fld, v in ts.items() if v == "unknown"]
        if unk:
            return "unknown", [(fld, msg("need_state", what=pred["what"], why="a contraindication depends on it")) for fld in unk], ""
        return "false", needs, ""
    if k == "hint":
        yes = [fld for fld in pred["fields"] if ctx.tri(fld) == "yes"]
        return ("warn" if yes else "false"), needs, pred["what"]
    if k == "med":
        if ctx.get("meds_known") != "yes":
            return "unknown", [("meds_text", msg("need_meds"))], ""
        hit = any(medsmod.term_matches(pred["label"], labs) or pred["label"] in labs for labs in _meds_labels(ctx, visit_labels))
        return ("true" if hit else "false"), needs, ""
    if k == "egfr_lt":
        if ctx.get("scr_mg_dl") is None and ctx.tri("kidney_disease") == "no":
            return "false", needs, "renal function not measured"      # creatinine is required only when kidney disease is yes/unsure/unknown
        d = egfr_fn()
        if d.value is None:
            return "unknown", list(d.needs) or [("scr_mg_dl", msg("need_scr", why="eGFR contraindication"))], ""
        return ("true" if d.value < float(groups[pred["n"] - 1]) else "false"), needs, ""
    return "manual", needs, ""


def _match_ci(text: str):
    for e in smap()["ci_map"]:
        m = re.search(e["match"], text, re.I)
        if m:
            return e["pred"], m.groups()
    return {"kind": "question"}, ()


# ---------------------------------------------------------------------------------------------------------- renal
def _classify(action: str) -> str:
    for e in smap()["renal_actions"]:
        if re.search(e["regex"], action, re.I):
            return e["effect"]
    return "warn"


def parse_renal_dose(action: str):
    nums = [float(x) for tup in re.findall(r"(\d+(?:\.\d+)?)(?:\s*-\s*(\d+(?:\.\d+)?))?\s*mg", action.split(" plus ")[0])
            for x in tup if x]
    if not nums:
        return None
    m = re.search(r"every\s+(\d+(?:\.\d+)?)\s*h", action)
    if m:
        ih = float(m.group(1))
    elif re.search(r"once every (\d+) days?", action):
        ih = 24.0 * float(re.search(r"once every (\d+) days?", action).group(1))
    elif "once daily" in action:
        ih = 24.0
    else:
        return None
    return {"lo": min(nums), "hi": max(nums), "interval_h": ih}


def renal(f: Formulary, drug: dict, ctx, cfg, rule: dict, out: Out) -> None:
    rows = drug.get("renal_rules") or []
    numeric = [r for r in rows if (r.get("min") is not None or r.get("max") is not None) and derived.measure_family(r.get("measure"))]
    kidney = ctx.tri("kidney_disease")
    cache: dict = {}

    def measure(fam):
        if fam not in cache:
            cache[fam] = derived.renal_measure(f, fam, ctx, cfg)
        return cache[fam]

    if numeric:
        have_scr = ctx.get("scr_mg_dl") is not None
        if not have_scr and kidney != "no":
            out.needs_scr = True
            out.needs.append(("scr_mg_dl", msg("need_kidney")))
        elif have_scr:
            for fam in sorted({derived.measure_family(r["measure"]) for r in numeric}):
                d = measure(fam)
                out.needs += [n for n in d.needs if n not in out.needs]
                if d.note == "no_formula":
                    out.warnings.append(item(f, "warn_renal_noformula", msg("warn_renal_noformula", measure=fam)))
                if d.value is not None:
                    out.steps += d.steps
                    out.renal_values[fam] = d
            dialysis = ctx.tri("on_dialysis")
            seen = set()
            for r in numeric:
                fam = derived.measure_family(r["measure"])
                d = out.renal_values.get(fam)
                if d is None or d.value is None:
                    continue
                v = d.value
                if (r.get("min") is not None and v < r["min"]) or (r.get("max") is not None and v >= r["max"]):
                    continue
                ml = r["measure"].lower()
                if "dialysis" in ml:
                    want = "no" if "not on dialysis" in ml else "yes"
                    if dialysis != want:
                        if dialysis == "unknown":
                            out.warnings.append(item(f, "warn_renal", msg("warn_renal", measure=r["measure"] + " (dialysis status unknown)",
                                                                           lo=r.get("min"), hi=r.get("max"), action=r["action"]), r))
                        continue
                key = (fam, r["action"])
                if key in seen:
                    continue
                seen.add(key)
                eff = _classify(r["action"])
                args = dict(measure=r["measure"], lo=r.get("min"), hi=r.get("max"), action=r["action"])
                if eff == "block":
                    out.blocks.append(item(f, "block_renal", msg("block_renal", **args), r, overridable=True))
                elif eff == "dose":
                    rd = parse_renal_dose(r["action"])
                    if rd and rule["dose_type"] == "fixed" and (rule.get("population") or {}).get("min_age_years", 0) >= cfg.adult_min_age_years:
                        out.renal_dose = {**rd, "measure": r["measure"], "blo": r.get("min"), "bhi": r.get("max"), "action": r["action"]}
                    else:
                        out.renal_unapplied.append(r["action"])
                        out.warnings.append(item(f, "warn_renal_adjust", msg("warn_renal_adjust", action=r["action"]), r))
                elif eff == "warn":
                    out.warnings.append(item(f, "warn_renal", msg("warn_renal", **args), r))
                # 'info' (usual dose / no adjustment): nothing to do
            for fam, d in out.renal_values.items():
                fam_rows = [r for r in numeric if derived.measure_family(r["measure"]) == fam]
                top = max([r["max"] for r in fam_rows if r.get("max") is not None] or [None], default=None)
                covered = any(not ((r.get("min") is not None and d.value < r["min"]) or (r.get("max") is not None and d.value >= r["max"]))
                              for r in fam_rows)
                open_top = any(r.get("max") is None for r in fam_rows)
                if not covered and not (top is not None and d.value >= top and not open_top and all(r.get("min") is None or r["min"] <= top for r in fam_rows)):
                    out.warnings.append(item(f, "warn_renal_unmatched", msg("warn_renal_unmatched", measure=fam, v=d.value)))
    if kidney != "no":
        for r in rows:
            if r in numeric:
                continue
            out.warnings.append(item(f, "warn_renal_text", msg("warn_renal_text", measure=r.get("measure", ""), action=r["action"]), r))


# ---------------------------------------------------------------------------------------------------------- main
def assess(f: Formulary, drug: dict, ctx, rule: dict, visit_labels: list, cfg, form: str | None) -> Out:
    out = Out()
    sm = smap()
    egfr_cache: dict = {}

    def egfr_fn():
        if "v" not in egfr_cache:
            egfr_cache["v"] = derived.renal_measure(f, "EGFR", ctx, cfg)
        return egfr_cache["v"]

    # -- contraindications and block_rules (deduplicated by text)
    seen: set = set()
    has_preg_block = False
    for entry in list(drug.get("contraindications") or []) + list(drug.get("block_rules") or []):
        text = entry["text"]
        if text in seen:
            continue
        seen.add(text)
        pred, groups = _match_ci(text)
        if pred["kind"] in ("pregnant", "trimester", "weeks_ge") or (pred["kind"] == "any" and any(p["kind"] == "pregnant" for p in pred["of"])):
            has_preg_block = True
        state, needs, note = eval_pred(pred, groups, ctx, drug, visit_labels, egfr_fn, form, text)
        if state == "true":
            out.blocks.append(item(f, "block_ci", msg("block_ci", text=text), entry, overridable=True))
        elif state == "warn":
            if pred["kind"] == "hint":
                out.warnings.append(item(f, "warn_ci_hint", msg("warn_ci_hint", what=pred["what"], text=text), entry))
            else:
                out.warnings.append(item(f, "warn_relevant", msg("warn_relevant", why=pred.get("what", pred["kind"]), text=text), entry))
        elif state == "manual":
            out.warnings.append(item(f, "warn_unchecked_ci", msg("warn_unchecked_ci", text=text), entry))
        elif state == "unknown":
            for n in needs:
                if n not in out.needs:
                    out.needs.append(n)

    # -- pregnancy
    p = ctx.get("pregnant")
    ptexts = [e for e in [drug.get("pregnancy")] if e] + list(drug.get("pregnancy_additional") or [])
    for e in ptexts:
        if re.search(sm["pregnancy_block_regex"], e["text"]):
            has_preg_block = True
    if p in ("yes", "possible"):
        for e in ptexts:
            if re.search(sm["pregnancy_block_regex"], e["text"]):
                if not any(b["code"] == "block_ci" and "regnan" in b["text"] for b in out.blocks):
                    out.blocks.append(item(f, "block_pregnancy", msg("block_pregnancy", text=e["text"]), e, overridable=True))
            else:
                code = "warn_pregnancy" if p == "yes" else "warn_pregnancy_possible"
                out.warnings.append(item(f, code, msg(code, text=e["text"]), e))
    elif p is None:
        if has_preg_block:
            if ("pregnant", msg("need_pregnant", why="contraindication in pregnancy")) not in out.needs:
                out.needs.append(("pregnant", msg("need_pregnant", why="this drug has a pregnancy contraindication")))
        elif ptexts:
            out.warnings.append(item(f, "warn_pregnancy_unknown", msg("warn_pregnancy_unknown", text=ptexts[0]["text"]), ptexts[0]))

    # -- lactation
    ltexts = [e for e in [drug.get("lactation")] if e and e.get("text")] + list(drug.get("lactation_additional") or [])
    lac = ctx.tri("lactating")
    if lac == "yes":
        for e in ltexts:
            out.warnings.append(item(f, "warn_lactation", msg("warn_lactation", text=e["text"]), e))
    elif lac == "unknown" and ctx.get("sex") != "male" and ctx.prov("pregnant") != "derived":
        if any(re.search(sm["lactation_against_regex"], e["text"], re.I) for e in ltexts):
            out.needs.append(("lactating", msg("need_lactating")))

    # -- hepatic
    liver = ctx.tri("liver_disease")
    alcohol = ctx.tri("alcohol")
    for e in drug.get("hepatic_rules") or []:
        text = e.get("text") or e.get("action") or ""
        structured = e.get("measure") and "child" in e["measure"].lower()
        show = liver in ("yes", "unknown") or (alcohol == "yes" and "alcohol" in text.lower())
        if not show:
            continue
        if structured:
            cp_class, cp_score = ctx.get("child_pugh_class"), ctx.get("child_pugh_score")
            applies = None
            if e.get("class") is not None:
                applies = None if cp_class is None else (cp_class == e["class"])
            elif e.get("min") is not None:
                applies = None if cp_score is None else (cp_score >= e["min"])
            if applies is None:
                out.needs.append(("child_pugh_class" if e.get("class") is not None else "child_pugh_score",
                                  msg("need_hepatic_severity", why=f"{e['measure']} {e.get('class') or ('>= ' + str(e.get('min')))}")))
            elif applies:
                act = e.get("action", text)
                for h in sm["hepatic_actions"]:
                    mm = re.search(h["regex"], act)
                    if mm:
                        if h["effect"] == "reduce_pct":
                            out.adjust["reduce_pct"], out.adjust["reduce_label"] = float(mm.group(1)), act
                        else:
                            out.adjust["max_per_day_mg"] = float(mm.group(1))
                out.warnings.append(item(f, "warn_hepatic", msg("warn_hepatic", text=f"{e['measure']}: {act}"), e))
        else:
            out.warnings.append(item(f, "warn_hepatic", msg("warn_hepatic", text=text), e))

    # -- renal
    renal(f, drug, ctx, cfg, rule, out)

    # -- label warnings (all, collapsed in the UI) and the ones relevant to this patient
    out.label_warnings = [item(f, "warn_label", msg("warn_label", text=w["text"]), w) for w in drug.get("warnings") or []]
    texts = [("warning", w) for w in drug.get("warnings") or []] + [("interaction", w) for w in drug.get("interactions") or []]
    promoted = set()
    for trig in sm["warning_triggers"]:
        if ctx.tri(trig["field"]) != "yes":
            continue
        for _, w in texts:
            if re.search(trig["regex"], w["text"], re.I) and w["text"] not in promoted:
                promoted.add(w["text"])
                out.warnings.append(item(f, "warn_relevant", msg("warn_relevant", why=trig["why"], text=w["text"]), w))
        if not any(re.search(trig["regex"], w["text"], re.I) for _, w in texts):         # same-class borrow
            for other in f.drugs.values():
                if other["id"] != drug["id"] and other["duplicate_class"] == drug["duplicate_class"]:
                    for w in other.get("warnings", []) + other.get("interactions", []):
                        if re.search(trig["regex"], w["text"], re.I) and w["text"] not in promoted:
                            promoted.add(w["text"])
                            out.warnings.append(item(f, "warn_relevant",
                                                     msg("warn_relevant", why=trig["why"] + f"; text from the {other['id']} entry (same class)", text=w["text"]), w))
                            break

    # -- QT flag
    if drug.get("qt_risk") and ctx.tri("qt_history") == "unknown":
        out.needs.append(("qt_history", msg("need_qt")))

    # -- allergies given as free text, sulfa
    drug_labels = medsmod.labels_for_drug(drug["id"]) + [drug["id"], drug["generic"].lower()]
    if ctx.allergy_other_raw:
        matches, hits, unparsed = medsmod.match_allergy_text(ctx.allergy_other_raw, drug_labels)
        for h in hits:
            out.blocks.append({"code": "block_allergy_other", "overridable": True,
                               "text": msg("block_allergy_other", raw=ctx.allergy_other_raw, drug=drug["id"], via=h.matched_name)})
        shown = [m.matched_name for m in matches if m not in hits]
        if shown:
            out.warnings.append({"code": "warn_other_allergy", "text": msg("warn_other_allergy", raw=ctx.allergy_other_raw, matched=", ".join(shown))})
        if unparsed:
            out.warnings.append({"code": "warn_other_allergy_unmatched", "text": msg("warn_other_allergy_unmatched", raw="; ".join(unparsed))})
    if ctx.tri("allergy_sulfa") == "yes":
        out.warnings.append({"code": "warn_sulfa", "text": msg("warn_sulfa")})
    return out
