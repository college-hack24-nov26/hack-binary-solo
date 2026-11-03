"""Doctor-only 'Dosage check' panel. Calls dosing.service; the patient never sees this output."""
import streamlit as st

from dosing import formulary as fmod, history as hist, service
from dosing.config import BANNER, DEMO_BANNER, Config
from dosing.engine import apply_inputs
from dosing.mapper import map_record
from dosing.rules import indications
from intake.ui import result_card

ss = st.session_state
CHIP = {"patient_reported": "🟡 patient-reported", "doctor_entered": "🟢 doctor-entered", "doctor_confirmed": "🟢 doctor-confirmed",
        "derived": "⚪ derived", "unknown": "⚫ unknown"}
SHOW = [("weight_kg", "Weight (kg)"), ("age_months", "Age (months)"), ("sex", "Sex"), ("pregnant", "Pregnant"),
        ("allergy_penicillins", "Penicillin allergy"), ("allergy_nsaids", "NSAID allergy"), ("kidney_disease", "Kidney disease"),
        ("liver_disease", "Liver disease"), ("diabetes", "Diabetes"), ("hypertension", "Hypertension"), ("asthma", "Asthma"),
        ("ulcer", "Ulcer"), ("alcohol", "Alcohol"), ("heart_disease", "Heart disease")]
TRI = ["", "yes", "no"]


def _num(label, key, **kw):
    v = st.text_input(label, key=key, **kw).strip()
    return float(v) if v else None


def render(rec, user: dict, editable: bool) -> None:
    cfg = Config.from_env()
    f = fmod.load(cfg.formulary_path)
    st.header("Dosage check")
    st.error(BANNER) if not cfg.allow_unverified else st.error(BANNER + ". UNVERIFIED rules are computed.")
    if cfg.demo_mode:
        st.markdown(f"<div style='background:#c00;color:#fff;padding:8px;font-weight:bold;text-align:center'>{DEMO_BANNER}</div>", unsafe_allow_html=True)
    st.caption("Decision support only. The doctor makes the final decision. Nothing here is shown to the patient.")
    if not editable:
        st.info("Read-only: only a doctor can run and confirm a dosage check.")
        return
    k = rec.token
    ctx = map_record(rec)
    drug_id = st.selectbox("Drug", list(f.drugs), key=f"dc_drug_{k}", format_func=lambda i: f.drugs[i]["generic"])
    inds = indications(f.drugs[drug_id])
    ind = st.selectbox("Indication", [i["key"] for i in inds], key=f"dc_ind_{k}_{drug_id}")
    show_all = st.checkbox("Show every rule for this drug that fits the patient", key=f"dc_all_{k}")
    visit = st.multiselect("Other drugs prescribed this visit", [d for d in f.drugs if d != drug_id], key=f"dc_visit_{k}")
    _history(rec, user, f, drug_id, ctx, k)
    st.subheader("Patient context (provenance)")
    cols = st.columns(4)
    for i, (name, label) in enumerate(SHOW):
        v = ctx.f.get(name)
        cols[i % 4].caption(f"**{label}**: {v.value if v and v.value is not None else '—'}  \n{CHIP[ctx.prov(name)]}")
    _medicines(ctx)
    st.subheader("Doctor-entered inputs (never defaulted)")
    a, b, c = st.columns(3)
    with a:
        weight = _num("Confirm / correct weight (kg)", f"dc_w_{k}", help="Doses stay provisional until the doctor confirms weight")
        confirm_w = st.checkbox("Weight reported by patient is correct", key=f"dc_cw_{k}")
        height = _num("Height (cm)", f"dc_h_{k}")
        scr = _num("Serum creatinine (mg/dL)", f"dc_scr_{k}")
    with b:
        preg = st.selectbox("Pregnant (override quiz)", ["", "yes", "no", "possible"], key=f"dc_preg_{k}")
        weeks = _num("Weeks of pregnancy", f"dc_pw_{k}")
        trim = st.selectbox("Trimester", ["", "1", "2", "3"], key=f"dc_tri_{k}")
    with c:
        cp = st.selectbox("Child-Pugh class", ["", "A", "B", "C"], key=f"dc_cp_{k}")
        cps = _num("Child-Pugh score", f"dc_cps_{k}")
        g6 = st.selectbox("G6PD", ["", "normal", "deficient", "unknown"], key=f"dc_g6_{k}")
        meds = st.text_input("Current medicines (replaces quiz list)", key=f"dc_meds_{k}")
    form = st.text_input("Pharmacy form (e.g. 'oral liquid 120 mg/5 mL'; blank = suggest)", key=f"dc_form_{k}").strip() or None
    dpd = _num("Doses per day (only if the rule asks)", f"dc_dpd_{k}")
    mgkg = _num("Intended mg/kg/day (only if the rule asks)", f"dc_mgkg_{k}")
    di = {"weight_kg": weight, "height_cm": height, "scr_mg_dl": scr, "pregnant": preg,
          "pregnancy_weeks": weeks, "pregnancy_trimester": trim, "child_pugh_class": cp, "child_pugh_score": cps, "g6pd": g6,
          "meds_text": meds, "doses_per_day": dpd, "mg_per_kg_per_day": mgkg}
    di = {n: v for n, v in di.items() if v not in (None, "")}
    sel = st.session_state.get(f"dc_sel_{k}")
    extras = dict(ss.get(f"dc_extra_{k}", {}))             # values filled in on the result card (needs_input checklist)
    form = extras.pop("form", None) or form
    di = {**di, **extras}
    ovr = ss.get(f"dc_ovr_{k}")                            # override recorded on the result card; only for the drug it was given for
    ovr = ovr if ovr and ovr["drug"] == drug_id and ovr["ind"] == ind else None
    run = st.button("Run dosage check", type="primary", key=f"dc_run_{k}")
    recalc = ss.pop(f"dc_recalc_{k}", False)
    if run or recalc or f"dc_res_{k}" in ss:
        if run or recalc:
            if run:
                ss.pop(f"dc_ovr_{k}", None)               # a fresh run starts without an override
                ovr = None
            ss[f"dc_res_{k}"] = service.evaluate_for_record(
                rec, drug_id, ind, doctor_id=user["username"], doctor_inputs=di, confirmed=["weight_kg"] if confirm_w else [],
                visit_drugs=visit, selected_rule_id=sel, form=form, show_all_rules=show_all,
                override_reason=ovr["reason"] if ovr else None, override_category=ovr["category"] if ovr else None)
            ss[f"dc_di_{k}"] = di
        res = ss[f"dc_res_{k}"]
        _result(rec, user, res, k, ss.get(f"dc_di_{k}", di), drug_id, ind)


def _medicines(ctx) -> None:
    """Current medicines used by the interaction check: self-reported plus doctor-confirmed scans, de-duplicated, each with its source."""
    merged = ctx.all_meds()
    if not merged and not ctx.unparsed_meds and not ctx.ocr_unparsed:
        return
    st.subheader("Current medicines (used for interactions)")

    def tag(o):
        return "from scanned prescription" + (f" ({o['scan_date']})" if o.get("scan_date") else "") if o["source"] == "ocr_doctor_confirmed" else "patient-reported"
    for m in merged:
        origins = [{"source": m.source, "scan_date": m.scan_date}] + list(m.also)
        st.caption(f"• **{m.generic}** (as written: {m.raw}) · " + " + ".join(dict.fromkeys(tag(o) for o in origins)))
    for t in ctx.unparsed_meds:
        st.caption(f"• unparsed: doctor to review: '{t}'")
    for u in ctx.ocr_unparsed:
        st.caption(f"• unparsed from prescription: doctor to review: '{u['token']}' (scan dated {u['scan_date'] or 'not read'})")


def _result(rec, user, res, k, di, drug_id, ind):
    from records import store
    st.subheader("Result")
    if res.get("demo"):
        st.markdown(f"<div style='background:#c00;color:#fff;padding:8px;font-weight:bold;text-align:center'>{res['demo_banner']}</div>", unsafe_allow_html=True)
    st.warning(res["banner"] + f" · data status {res['data_status']}")
    result_card.render(res, k, drug_id, ind)
    hide = res["status"] in ("blocked", "refused")          # no dose figure of any kind until an override is recorded
    for b in res["blocks"]:
        st.error("⛔ " + b["text"])
    for n in res["needs_input"]:
        st.info(f"Needs input · {n['field']}: {n['why']}")
    if res["dose_mg"] is not None:
        st.metric("Dose", f"{res['dose_mg']:g} mg", f"{res['product']}: " + (f"{res['volume_ml']:g} mL" if res["volume_ml"] else f"{res['units']:g} unit(s)"))
        st.write(f"Interval/frequency: {res['interval_h'] or res['doses_per_day']} · daily total {res['daily_total_mg']} mg · "
                 f"daily max {res['daily_max_mg']} mg · binding cap: {res['binding_cap'] or 'none'}")
    if res["plan"] and not hide:
        st.write("Titration plan:", res["plan"])
    if res["text_regimen"] and not hide:
        st.write("Regimen (free text from the formulary, not computed):", res["text_regimen"])
    if res["duration"] and not hide:
        st.write("Duration:", res["duration"])
    if not res["final"] and res["pending_confirmations"]:
        st.warning("Provisional: confirm " + ", ".join(res["pending_confirmations"]))
    if res["alternatives"]:
        st.markdown("**Alternatives (side by side)**")
        for a in res["alternatives"]:
            tag = " ⭐ suggested" if a["suggested"] else ""
            with st.expander(f"{a['rule_id']} · {a['indication']} · {a['data_status']}{tag}", expanded=a["selected"]):
                st.write({x: a[x] for x in a if x in (("note", "conflict") if hide else
                                                      ("dose_range_mg", "interval_h", "doses_per_day", "duration", "text_regimen", "note", "conflict"))})
                st.write("Sources:", ", ".join(f"{s['name']} ({s['url']})" if s.get("url") else s["name"] for s in a["sources"]))
                if st.button("Use this rule", key=f"dc_use_{k}_{a['rule_id']}"):
                    ss[f"dc_sel_{k}"] = a["rule_id"]
                    ss.pop(f"dc_res_{k}", None)
                    st.rerun()
    with st.expander("Calculation steps", expanded=not hide):
        if hide:
            st.write("Hidden until an override is recorded: no dose figure is shown for a blocked or refused case.")
        else:
            for s in res["calculation_steps"]:
                st.write("• " + s)
    for w in res["warnings"]:
        st.warning(w["text"])
    for i in res["interactions"]:
        st.warning("↔ " + i["text"])
    with st.expander("Label warnings"):
        for w in res["label_warnings"]:
            st.write(w["text"])
    with st.expander("Sources"):
        for s in res["sources"]:
            st.write(f"{s['id'] or '-'} · {s['name']} · [{s['status']}] · {s.get('url') or ''}  \n{s['section']}")
    ack = False
    if res.get("acknowledge_items"):
        st.warning("These contraindications could not be checked by the engine and are still unanswered:\n" + "\n".join("- " + t for t in res["acknowledge_items"]))
        ack = st.checkbox("I have checked these", key=f"dc_ack_{k}")
    if st.button("Confirm and save to record", disabled=not service.can_confirm(res, ack), key=f"dc_conf_{k}"):
        store.save(service.confirm(rec, res, doctor_id=user["username"], doctor_inputs=di, acknowledged=ack))
        ss.pop(f"dc_res_{k}", None)
        ss[f"saved_{k}"] = "Dosage check confirmed and saved."
        st.rerun()


def _history(rec, user, f, drug_id, ctx, k):
    """One checklist of every unknown fact this drug's contraindications and warnings need. Unanswered stays unknown."""
    from records import store
    ctx2 = apply_inputs(ctx, {}, [], rec.visitHistory)
    items = hist.items_for(f, f.drugs[drug_id], ctx2)
    todo = hist.unknown_items(items)
    st.subheader("History check")
    st.caption("Answers are saved as doctor-confirmed for this visit and reused for every drug checked. Unanswered items stay unknown, never 'no'.")
    known = [i for i in items if i not in todo]
    if known:
        st.caption("Already known: " + " · ".join(f"{i.label}: {i.value} ({CHIP[i.prov].split(' ', 1)[1]})" for i in known))
    if not todo:
        st.success("Nothing unknown for this drug.")
        return
    if st.button("None of these apply (sets every listed item to no)", key=f"dc_hnone_{k}_{drug_id}"):
        for i in todo:
            ss[f"dc_h_{k}_{i.field}"] = "no"
        st.rerun()
    for i in todo:
        st.markdown(f"**{i.label}**" + (" · *required*" if i.required else "") + f"  \n{i.question}")
        st.radio(i.label, ["", "yes", "no", "unsure"], key=f"dc_h_{k}_{i.field}", horizontal=True, label_visibility="collapsed",
                 format_func=lambda v: v or "unanswered")
    if st.button("Save history answers", key=f"dc_hsave_{k}_{drug_id}"):
        ans = {i.field: ss.get(f"dc_h_{k}_{i.field}") for i in todo if ss.get(f"dc_h_{k}_{i.field}")}
        if ans:
            store.save(service.save_history(rec, ans, doctor_id=user["username"]))
            ss.pop(f"dc_res_{k}", None)
            st.rerun()
        else:
            st.info("Nothing answered yet.")
