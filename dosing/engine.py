"""evaluate(): the one entry point. Pure and deterministic: same Request in, same Result out (no clock, no randomness).
Order of status: blocked > refused > needs_input > ok."""
import re
from dataclasses import dataclass, field

from . import ENGINE_VERSION, calc as calcmod, formulary as fmod, interactions as imod, products as pmod, rules as rmod, safety
from .config import BANNER, DEMO_BANNER, OVERRIDE_CATEGORIES, Config
from .context import CONFIRMED, DERIVED, DOCTOR, PatientContext, TRUSTED, UNKNOWN
from .formulary import norm_status
from .mapper import DAYS_PER_MONTH, set_age
from .messages import msg
from . import meds as medsmod

STATUS_ORDER = {"VERIFIED": 0, "SECONDARY": 1, "UNVERIFIED": 2}
TRI_FIELDS_BASE = {"lactating", "qt_history", "on_dialysis", "alcohol", "ulcer", "gi_bleed", "heart_disease", "kidney_disease",
              "liver_disease", "diabetes", "hypertension", "asthma", "allergy_penicillins", "allergy_sulfa", "allergy_nsaids"}
TRI_FIELDS = TRI_FIELDS_BASE


def is_tri_field(name: str) -> bool:
    return name in TRI_FIELDS or name.startswith("q_")


NUM_FIELDS = {"weight_kg", "height_cm", "scr_mg_dl", "pregnancy_weeks", "pregnancy_trimester", "child_pugh_score"}
STR_FIELDS = {"sex_for_formula": {"female", "male"}, "pregnant": {"yes", "no", "possible"},
              "child_pugh_class": {"A", "B", "C"}, "g6pd": {"normal", "deficient", "unknown"}}
CALC_INPUTS = {"doses_per_day", "mg_per_kg_per_day", "cg_weight_basis"}


@dataclass
class Request:
    drug: str
    context: PatientContext
    indication: str | None = None
    doctor_inputs: dict = field(default_factory=dict)      # fields typed by the doctor on the dosage screen
    confirmed: list = field(default_factory=list)          # names whose current (quiz) value the doctor confirms as-is
    visit_drugs: list = field(default_factory=list)        # other drugs (ids or names) prescribed in the same visit
    selected_rule_id: str | None = None
    form: str | None = None                                # a forms_india label such as "oral liquid 120 mg/5 mL"
    route: str | None = None                               # oral | parenteral | rectal
    show_all_rules: bool = False
    override_reason: str | None = None
    override_category: str | None = None                   # key of config.OVERRIDE_CATEGORIES
    doctor_id: str | None = None
    history: dict = field(default_factory=dict)            # History-check answers (yes/no/unsure), stored as doctor_confirmed


def _set_choice(c: PatientContext, name: str, val, prov: str, note: str = "") -> None:
    if val not in ("yes", "no", "unsure"):
        raise ValueError(f"{name} must be yes, no or unsure")
    if name == "pregnant":
        val = "possible" if val == "unsure" else val
    c.set(name, val, prov, note)


def apply_inputs(ctx: PatientContext, inputs: dict, confirmed: list, history: dict | None = None) -> PatientContext:
    c = ctx.copy()
    for name, val in sorted((history or {}).items()):
        if val in (None, ""):
            continue
        _set_choice(c, name, val, CONFIRMED, "History check")
    for name in confirmed:
        v = c.f.get(name)
        if v is not None and v.value is not None and v.prov not in TRUSTED:
            v.note = (v.note + "; " if v.note else "") + f"quiz value {v.value!r} confirmed"
            v.prov = CONFIRMED
    for name, val in sorted(inputs.items()):
        if val is None or val == "":
            continue
        old = c.f.get(name)
        note = f"quiz said {old.value!r}" if old is not None and old.value not in (None, val) and old.prov != UNKNOWN else ""
        if is_tri_field(name) or name == "pregnant":
            _set_choice(c, name, val, DOCTOR, note)
        elif name in NUM_FIELDS:
            c.set(name, float(val), DOCTOR, note)
        elif name in STR_FIELDS and name != "pregnant":
            if val not in STR_FIELDS[name]:
                raise ValueError(f"{name} must be one of {sorted(STR_FIELDS[name])}")
            c.set(name, val, DOCTOR, note)
        elif name == "age_exact_days":
            d = float(val)
            c.set("age_months", int(d // DAYS_PER_MONTH), DOCTOR, "exact age entered")
            c.set("age_window_months", 0, DOCTOR)
            c.set("age_days_lo", d, DOCTOR)
            c.set("age_days_hi", d + 1, DOCTOR)
        elif name == "age_months":
            set_age(c, int(val), 0, DOCTOR)
        elif name == "meds_text":
            c.set("meds_text", str(val), DOCTOR, note)
            c.set("meds_known", "yes", DOCTOR)
            c.meds, c.unparsed_meds = medsmod.parse_names(str(val))
        elif name in CALC_INPUTS:
            pass
        else:
            raise ValueError(f"unknown doctor input {name!r}")
    return c


def _worst(*s) -> str:
    return max((norm_status(x) for x in s), key=STATUS_ORDER.get)


def _fmt_dose(x):
    return calcmod.r3(x)


def _ratio_key(s: str):
    m = re.search(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", s or "")
    return (float(m.group(1)), float(m.group(2))) if m else None


def _product_key(p: pmod.Product):
    k = p.key.split("/")
    return (float(k[0]), float(k[1])) if len(k) == 2 else None


def _round_to_products(f, drug, c: calcmod.Calc, req: Request, rule: dict, cfg: Config):
    """-> (best Option | None, options list, warnings, needs, steps)"""
    warns, needs, steps = [], [], []
    rc = req.route or (sorted(rmod.route_classes(rule.get("route")))[0] if rule.get("route") else "oral")
    prods = pmod.products_for(drug, rc)
    if req.form:
        prods = [p for p in prods if p.label == req.form]
        if not prods:
            needs.append(("form", msg("need_form", why=f"'{req.form}' is not a {rc} form of this drug")))
            return None, [], warns, needs, steps
    mismatch = False
    if c.product_keys:
        wanted = [_ratio_key(k) for k in c.product_keys]
        match = [p for p in prods if _product_key(p) in wanted]
        if match:
            prods = match
        else:
            mismatch = True
            warns.append(msg("warn_ratio", want=", ".join(c.product_keys)))
    elif drug.get("dose_basis"):
        warns.append(msg("warn_ratio_unspecified"))
    if not req.form:
        warns.append(msg("warn_no_form"))
    opts = []
    for p in prods:
        opts += pmod.deliver(p, c.lo, c.hi, c.target, c.ceiling, cfg.ml_step, ratio_mismatch=mismatch)
    best, ranked = pmod.choose([o for o in opts if not o.ratio_mismatch] or opts, c.target)
    if best is not None and best.ratio_mismatch:
        best = None
    if any(not p.liquid and not p.scored for p in prods):
        pass
    if best is None:
        needs.append(("form", msg("need_product")))
    return best, ranked, warns, needs, steps


@dataclass
class _Solved:
    cand: rmod.Candidate
    calc: calcmod.Calc
    out: safety.Out
    best: pmod.Option | None = None
    options: list = field(default_factory=list)
    warns: list = field(default_factory=list)
    needs: list = field(default_factory=list)
    refused: list = field(default_factory=list)
    status: str = "VERIFIED"


def _solve(f, drug, cand, ctx, req, cfg, visit_labels) -> _Solved:
    rule = cand.rule
    st = norm_status(rule.get("status"))
    s = _Solved(cand=cand, calc=calcmod.Calc(), out=safety.Out(), status=st)
    if st == "UNVERIFIED" and not cfg.allow_unverified:
        s.refused.append(msg("refused_unverified"))
        return s
    form_class = None
    if req.form:
        form_class = req.form.split(" ")[0] if False else None
    out = safety.assess(f, drug, ctx, rule, visit_labels, cfg, _form_name(req.form))
    s.out = out
    s.calc = calcmod.compute(f, drug, rule, ctx, req.doctor_inputs, cfg, adjust={**out.adjust, **({"renal_dose": out.renal_dose} if out.renal_dose else {})})
    s.refused += s.calc.refused
    if s.calc.kind == "numeric" and not s.calc.needs and not s.refused:
        s.best, s.options, s.warns, n, _ = _round_to_products(f, drug, s.calc, req, rule, cfg)
        s.needs += n
    return s


def _form_name(label: str | None):
    if not label:
        return None
    for fm in sorted(pmod.ORAL | pmod.PARENTERAL | pmod.RECTAL, key=len, reverse=True):
        if label.startswith(fm):
            return fm
    return None


def _summary(sv: _Solved, suggested_id, selected_id, f) -> dict:
    c, cand = sv.calc, sv.cand
    rule = cand.rule
    st = norm_status(rule.get("status"))
    a = {"rule_id": cand.rid, "indication": rule["indication"], "population": rule.get("population") or {},
         "dose_type": rule["dose_type"], "data_status": st, "suggested": cand.rid == suggested_id,
         "selected": cand.rid == selected_id, "computed": c.kind in ("numeric",) and not sv.refused,
         "kind": c.kind, "sources": f.source_refs(rule.get("source"), st),
         "rule_hash": fmod.rule_hash(rule)}
    if rule.get("conflict"):
        a["conflict"] = rule["conflict"]
    if rule.get("note"):
        a["note"] = rule["note"]
    if cand.also:
        a["corroborated_by"] = cand.also
    if c.kind == "numeric":
        a["dose_range_mg"] = [_fmt_dose(c.lo), _fmt_dose(c.hi)]
        a["interval_h"] = c.interval_h
        a["doses_per_day"] = c.doses_per_day
        a["binding_cap"] = c.binding_cap
    if c.kind == "text":
        a["text_regimen"] = c.text
    if c.duration:
        a["duration"] = c.duration
    a["needs_input"] = [{"field": n[0], "why": n[1]} for n in (c.needs + cand.pop.needs + sv.needs)]
    if sv.refused:
        a["refused"] = sv.refused
    if cand.pop.status == "age_ambiguous":
        a["age_boundary"] = True
    return a


def evaluate(req: Request, cfg: Config | None = None, formulary: fmod.Formulary | None = None) -> dict:
    cfg = cfg or Config.from_env()
    f = formulary or fmod.load(cfg.formulary_path)
    res = {"status": "needs_input", "drug": None, "indication": req.indication, "selected_rule_id": None,
           "suggested_rule_id": None, "alternatives": [], "dose_mg": None, "dose_range_mg": None, "product": None,
           "product_options": [], "volume_ml": None, "units": None, "interval_h": None, "doses_per_day": None,
           "daily_total_mg": None, "daily_max_mg": None, "binding_cap": None, "duration": None, "plan": None,
           "text_regimen": None, "computed": False, "calculation_steps": [], "warnings": [], "label_warnings": [],
           "blocks": [], "needs_input": [], "refused_reasons": [], "interactions": [], "overrides": [],
           "provenance": {}, "sources": [], "data_status": "VERIFIED", "final": False, "pending_confirmations": [],
           "indications": [], "engine_version": ENGINE_VERSION, "formulary_version": f.version, "banner": BANNER,
           "disclaimer": msg("doctor_decides"), "allow_unverified": cfg.allow_unverified,
           "demo": cfg.demo_mode, "acknowledge_items": [], "demo_banner": DEMO_BANNER if cfg.demo_mode else None, "boundary_overlap": []}

    drug = f.find_drug(req.drug)
    if drug is None:
        res.update(status="refused", refused_reasons=[msg("refused_unknown_drug", drug=req.drug)])
        return res
    res["drug"] = drug["id"]
    res["indications"] = [{"key": i["key"], "labels": i["labels"], "rules": len(i["rules"])} for i in rmod.indications(drug)]
    ctx = apply_inputs(req.context, req.doctor_inputs, req.confirmed, req.history)
    res["provenance"] = ctx.provenance_dict()
    needs: list = []
    warnings: list = []
    steps: list = []

    # -- visit drugs
    visit_ids, visit_labels = [], []
    for name in req.visit_drugs:
        d = f.find_drug(name)
        if d is not None and d["id"] != drug["id"] and d["id"] not in visit_ids:
            visit_ids.append(d["id"])
    visit_ids.sort()
    for did in visit_ids:
        visit_labels.append(imod.drug_labels(f, f.drugs[did]))

    # -- age and the basics every rule needs
    if ctx.get("age_months") is None:
        needs.append(("age_months", msg("need_age")))
    else:
        steps.append(msg("step_age", months=ctx.get("age_months"), lo=round(ctx.get("age_days_lo") / DAYS_PER_MONTH, 1),
                         hi=round(ctx.get("age_days_hi") / DAYS_PER_MONTH, 1), prov=ctx.prov("age_months")))
    if ctx.get("weight_kg") is not None:
        steps.append(msg("step_weight", w=calcmod.fmt(ctx.get("weight_kg")), prov=ctx.prov("weight_kg")))
    wi = ctx.get("weight_implausible")
    if wi and not ctx.trusted("weight_kg"):
        warnings.append({"code": "warn_weight_implausible", "text": msg("warn_weight_implausible", **wi)})
    if ctx.red_flags:
        warnings.append({"code": "warn_red_flags", "text": msg("warn_red_flags", ids=", ".join(r["ruleId"] for r in ctx.red_flags))})
    if ctx.get("g6pd"):
        warnings.append({"code": "warn_g6pd", "text": msg("warn_g6pd", v=ctx.get("g6pd"))})

    # -- indication and candidate rules
    ind_key = rmod.indication_key(req.indication) if req.indication else None
    if ind_key is None and not req.show_all_rules:
        needs.append(("indication", msg("need_indication")))
        return _finish(res, f, drug, cfg, ctx, req, needs, warnings, steps, [], [], None, None, None)
    cands, gated = rmod.select(f, drug, ind_key, ctx, req.route, cfg, show_all=req.show_all_rules)
    blocks: list = []
    overridable_gate = False
    if not cands:
        if gated:
            seen = []
            for g in gated:
                for r in g.pop.reasons:
                    if r not in seen:
                        seen.append(r)
            for r in seen[:4]:
                blocks.append({"code": "block_age" if "Age" in r else "block_weight", "text": r, "overridable": True})
            if drug.get("override_rules") and ctx.get("age_days_lo") is not None and ctx.get("age_days_lo") < cfg.adult_min_age_years * 365.25:
                for o in drug["override_rules"]:
                    st = norm_status(o.get("status"))
                    blocks.append({"code": "block_offlabel_child", "text": msg("block_offlabel_child", text=o["text"]),
                                   "overridable": True, "data_status": st, "sources": f.source_refs(o.get("source"), st)})
                overridable_gate = True
        else:
            res["refused_reasons"].append(msg("refused_no_rule", drug=drug["id"], ind=req.indication or "all"))

    # a valid written override lets the engine show the rules the patient falls outside of
    override = _valid_override(req, cfg)
    overridden_path = False
    if not cands and gated and override and overridable_gate:
        overridden_path = True
        cands, _ = rmod.select(f, drug, None, ctx, req.route, cfg, show_all=True)
        cands = [c for c in cands]
        for c in cands:
            c.pop.warnings.append(msg("warn_offlabel"))

    solved = [_solve(f, drug, c, ctx, req, cfg, visit_labels) for c in cands]
    no_rule_out = None
    if not cands:               # contraindications and unknowns are still reported when no rule fits the patient
        no_rule_out = safety.assess(f, drug, ctx, {"dose_type": "fixed", "population": {}}, visit_labels, cfg, _form_name(req.form))
    live = [s for s in solved if not any(msg("refused_unverified") == r for r in s.refused)]
    sug, why = rmod.suggested(f, drug, [s.cand for s in live]) if live else (None, "")
    suggested_id = sug.rid if sug else None
    force_pick = bool(cands) and bool(overridden_path)
    sel_id = None
    edge = [s for s in live if rmod.at_age_edge(s.cand.rule, ctx)]
    boundary_only = len(live) > 1 and len(edge) == len(live)
    if boundary_only:            # same patient age sits on a shared boundary: default to the lower-dose rule, doctor may pick either
        res["boundary_overlap"] = [s.cand.rid for s in live]
        numeric = [s for s in live if s.calc.kind == "numeric" and s.calc.lo is not None]
        if len(numeric) == len(live):
            low = min(numeric, key=lambda s: ((s.calc.daily_hi if s.calc.daily_hi is not None else s.calc.hi), s.cand.index))
            suggested_id = low.cand.rid
    if req.selected_rule_id and any(s.cand.rid == req.selected_rule_id for s in live):
        sel_id = req.selected_rule_id
    elif len(live) == 1 and not force_pick:
        sel_id = live[0].cand.rid
    elif boundary_only and suggested_id:
        sel_id = suggested_id
    view = next((s for s in solved if s.cand.rid == (sel_id or suggested_id)), None)       # drives the safety checks
    if len(live) > 1 or force_pick:
        steps.append(msg("step_selected", n=len(live), rid=suggested_id, why=why))
        if sel_id is None:
            needs.append(("selected_rule_id", msg("need_rule_choice")))
    if cands and not live:
        res["refused_reasons"].append(msg("refused_unverified"))
    if no_rule_out is not None:
        blocks += no_rule_out.blocks
        warnings += no_rule_out.warnings
        needs += no_rule_out.needs
        res["label_warnings"] = no_rule_out.label_warnings
    return _finish(res, f, drug, cfg, ctx, req, needs, warnings, steps, blocks, solved, suggested_id, sel_id, chosen=view,
                   visit_ids=visit_ids, override=override, show_calc=sel_id is not None)


def _multi_ambiguous(live) -> bool:
    return any(s.cand.pop.status == "age_ambiguous" for s in live)


def _valid_override(req: Request, cfg: Config) -> bool:
    return bool(req.override_reason and len(req.override_reason.strip()) >= cfg.override_min_chars and req.doctor_id
                and req.override_category in OVERRIDE_CATEGORIES)


def _finish(res, f, drug, cfg, ctx, req, needs, warnings, steps, blocks, solved, suggested_id, sel_id, chosen=None,
            visit_ids=(), override=False, show_calc=True):
    res["suggested_rule_id"], res["selected_rule_id"] = suggested_id, sel_id
    res["alternatives"] = [_summary(s, suggested_id, sel_id, f) for s in (solved or [])]
    sources: list = []
    status_parts = ["VERIFIED"]
    refused = list(res["refused_reasons"])

    if chosen is not None:
        c, rule, out = chosen.calc, chosen.cand.rule, chosen.out
        res["indication"] = rule["indication"]
        status_parts.append(norm_status(rule.get("status")))
        steps.append(msg("step_rule", rid=chosen.cand.rid, ind=rule["indication"], src=str(rule.get("source"))[:80],
                         status=norm_status(rule.get("status"))))
        steps.append(msg("step_age_window", w=chosen.cand.pop.window))
        if show_calc:
            steps += c.steps + out.steps
            needs += c.needs + chosen.cand.pop.needs + chosen.needs
        needs += out.needs
        warnings += [{"code": "pop", "text": w} for w in chosen.cand.pop.warnings]
        warnings += [{"code": "calc", "text": w} for w in c.warnings + chosen.warns]
        blocks += out.blocks
        warnings += out.warnings
        res["label_warnings"] = out.label_warnings
        refused += chosen.refused
        if rule.get("conflict"):
            warnings.append({"code": "warn_alt_conflict", "text": msg("warn_alt_conflict", text=rule["conflict"])})
        if chosen.cand.pop.status == "age_ambiguous" or chosen.cand.rid in res["boundary_overlap"]:
            warnings.append({"code": "warn_overlap", "text": msg("warn_overlap")})
        if norm_status(rule.get("status")) == "UNVERIFIED":
            warnings.append({"code": "warn_unverified_rule", "text": msg("warn_unverified_rule")})
        sources += f.source_refs(rule.get("source"), norm_status(rule.get("status")))
        for al in chosen.cand.also:
            sources += f.source_refs(al["source"], al["status"])
        for d in out.renal_values.values():
            status_parts.append(d.status)
        for it in out.blocks + out.warnings:
            if it.get("data_status") and it["code"] in ("block_renal", "warn_renal"):
                status_parts.append(it["data_status"])
        # product / dose fields
        res["duration"] = c.duration
        res["binding_cap"] = c.binding_cap
        res["daily_max_mg"] = c.daily_max_mg
        res["interval_h"] = c.interval_h
        res["doses_per_day"] = c.doses_per_day if c.doses_per_day is not None else (_nfmt(c.n_hi) if c.n_hi else None)
        res["text_regimen"] = c.text
        res["plan"] = c.plan
        res["computed"] = show_calc and c.kind == "numeric" and not refused and not c.needs
        if not show_calc:
            res["duration"] = res["binding_cap"] = res["daily_max_mg"] = res["interval_h"] = res["doses_per_day"] = res["text_regimen"] = res["plan"] = None
        if show_calc and c.kind == "numeric" and not c.needs and not chosen.refused:
            res["dose_range_mg"] = [_fmt_dose(c.lo), _fmt_dose(c.hi)]
            res["product_options"] = [o.as_dict() for o in chosen.options[:6]]
            b = chosen.best
            if b is not None:
                steps.append(msg("step_product", p=b.product, n=(f"{b.units:g} unit(s)" if b.units else f"{b.volume_ml:g} mL"), mg=_fmt_dose(b.delivered_mg)))
                if b.volume_ml:
                    pr = next((p for p in pmod.products_for(drug, None) if p.label == b.product), None)
                    if pr:
                        steps.append(msg("step_liquid", mgml=calcmod.fmt(round(pr.comps[0], 4)), mg=_fmt_dose(c.target), ml=round(c.target / pr.comps[0], 3),
                                         step=calcmod.fmt(cfg.ml_step), vol=b.volume_ml, dmg=_fmt_dose(b.delivered_mg)))
                else:
                    steps.append(msg("step_solid", strength=b.product, u=calcmod.fmt(b.units), mg=_fmt_dose(b.delivered_mg)))
                res["product"], res["units"], res["volume_ml"] = b.product, b.units, b.volume_ml
                res["dose_mg"] = _fmt_dose(b.delivered_mg)
                if c.n_hi:
                    lo_t, hi_t = b.delivered_mg * (c.n_lo or c.n_hi), b.delivered_mg * c.n_hi
                    res["daily_total_mg"] = _fmt_dose(hi_t) if abs(hi_t - lo_t) < 1e-9 else [_fmt_dose(lo_t), _fmt_dose(hi_t)]
                    if c.daily_max_mg is not None and hi_t > c.daily_max_mg + 1e-6:
                        warnings.append({"code": "warn_cap_exceeded", "text": f"Daily total {_fmt_dose(hi_t)} mg exceeds the cap {c.daily_max_mg} mg: reduce the number of doses."})
                if c.max_tablets_per_day and b.units and c.n_hi and b.units * c.n_hi > c.max_tablets_per_day:
                    warnings.append({"code": "warn_max_tablets", "text": msg("warn_max_tablets", cap=calcmod.fmt(c.max_tablets_per_day),
                                                                              units=calcmod.fmt(b.units), n=calcmod.fmt(c.n_hi), tot=calcmod.fmt(b.units * c.n_hi))})
            else:
                res["dose_mg"] = _fmt_dose(c.target)
        elif c.kind in ("text", "plan", "duration") or not show_calc:
            res["computed"] = False

    # -- interactions (only once a drug is known; independent of the rule)
    inter = imod.check(f, drug, ctx, list(visit_ids))
    for it in inter["items"]:
        sev = it["severity"]
        entry = {k: it[k] for k in ("kind", "severity", "with", "action", "data_status", "sources", "details", "blocking", "origins") if k in it}
        entry["text"] = (msg("warn_duplicate", cls=it.get("class", ""), with_=it["with"], action=it["action"]) if it["kind"] == "duplicate"
                         else msg("warn_interaction", sev=sev, with_=it["with"], action=it["action"]))
        res["interactions"].append(entry)
        if it["blocking"]:
            blocks.append({"code": "block_interaction", "overridable": True, "data_status": it["data_status"], "sources": it["sources"],
                           "text": msg("block_interaction", sev=sev, with_=it["with"], action=it["action"])})
        else:
            warnings.append({"code": "warn_interaction", "text": entry["text"], "data_status": it["data_status"], "sources": it["sources"]})
    warnings += inter["warnings"]
    if inter["incomplete"]:
        needs.append(("meds_text", msg("need_meds")))

    # -- finality: weight (and creatinine where a renal measure was used) must be doctor-confirmed
    pending = []
    if chosen is not None and show_calc:
        weight_used = chosen.cand.rule["dose_type"] in rmod.WEIGHT_TYPES or "max_per_kg_per_day" in chosen.cand.rule \
            or any(v.note == "cockcroft_gault" for v in chosen.out.renal_values.values())
        if weight_used and not ctx.trusted("weight_kg"):
            pending.append("weight_kg")
            warnings.append({"code": "warn_weight_unconfirmed", "text": msg("warn_weight_unconfirmed")})
        if chosen.out.renal_values and not ctx.trusted("scr_mg_dl"):
            pending.append("scr_mg_dl")
            warnings.append({"code": "warn_scr_unconfirmed", "text": msg("warn_scr_unconfirmed")})
    res["pending_confirmations"] = pending

    # -- override: a valid written reason turns each overridable block into a logged, visible warning
    if override and blocks:
        for b in blocks:
            if b.get("overridable"):
                res["overrides"].append({"block": b["text"], "code": b["code"], "reason": req.override_reason.strip(), "doctor_id": req.doctor_id,
                                         "category": req.override_category, "category_label": OVERRIDE_CATEGORIES[req.override_category]})
                warnings.append({"code": "overridden", "text": msg("overridden", doctor=req.doctor_id, reason=f"{OVERRIDE_CATEGORIES[req.override_category]}: {req.override_reason.strip()}", block=b["text"]),
                                 "data_status": b.get("data_status", "VERIFIED"), "sources": b.get("sources", [])})
        blocks = [b for b in blocks if not b.get("overridable")]

    # -- de-duplicate and finish
    res["blocks"] = _uniq(blocks)
    res["warnings"] = _uniq(warnings)
    # unanswered free-text contraindications stay warnings, but the doctor must tick "I have checked these" before confirming
    res["acknowledge_items"] = [w["text"] for w in res["warnings"] if w["code"] == "warn_unchecked_ci"]
    res["needs_input"] = [{"field": a, "why": b} for a, b in _uniq_pairs(needs)]
    res["refused_reasons"] = list(dict.fromkeys(refused))
    for it in res["blocks"] + res["warnings"]:
        for s in it.get("sources", []):
            sources.append(s)
        if it.get("data_status"):
            status_parts.append(it["data_status"])
    for a in res["alternatives"]:
        if a["selected"]:
            continue
    res["sources"] = _uniq_sources(sources)
    res["data_status"] = _worst(*status_parts)
    if res["data_status"] == "UNVERIFIED":
        res["calculation_steps"] = ["[UNVERIFIED] " + s for s in steps]
    else:
        res["calculation_steps"] = steps

    if res["blocks"]:
        res["status"] = "blocked"
    elif res["refused_reasons"]:
        res["status"] = "refused"
    elif res["needs_input"]:
        res["status"] = "needs_input"
    else:
        res["status"] = "ok"
    if res["status"] in ("blocked", "refused", "needs_input"):
        for k in ("dose_mg", "product", "volume_ml", "units", "daily_total_mg"):
            res[k] = None                      # never show a number the doctor must not act on
        res["computed"] = False
        if res["status"] != "needs_input":
            res["dose_range_mg"] = None
            res["product_options"] = res["product_options"] if res["status"] == "needs_input" else []
    res["final"] = res["status"] == "ok" and not pending and res["computed"]
    return res


def _nfmt(x):
    return int(x) if abs(x - round(x)) < 1e-9 else round(x, 2)


def _uniq(items):
    seen, out = set(), []
    for it in items:
        k = (it.get("code"), it.get("text"))
        if k not in seen:
            seen.add(k)
            out.append(it)
    return out


def _uniq_pairs(pairs):
    seen, out = set(), []
    for a, b in pairs:
        if (a, b) not in seen:
            seen.add((a, b))
            out.append((a, b))
    return out


def _uniq_sources(srcs):
    seen, out = set(), []
    for s in srcs:
        k = (s.get("id"), s.get("section"))
        if k not in seen:
            seen.add(k)
            out.append(s)
    return out
