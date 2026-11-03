"""Doctor-only 'Dosage check' panel. Calls dosing.service; the patient never sees this output."""
import streamlit as st

from dosing import formulary as fmod, service
from dosing.config import BANNER, Config
from dosing.mapper import map_record
from dosing.rules import indications

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
    st.error(BANNER) if not cfg.allow_unverified else st.error(BANNER + ". DOSING_ALLOW_UNVERIFIED is ON: UNVERIFIED rules are computed.")
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
    st.subheader("Patient context (provenance)")
    cols = st.columns(4)
    for i, (name, label) in enumerate(SHOW):
        v = ctx.f.get(name)
        cols[i % 4].caption(f"**{label}**: {v.value if v and v.value is not None else '—'}  \n{CHIP[ctx.prov(name)]}")
    st.subheader("Doctor-entered inputs (never defaulted)")
    a, b, c = st.columns(3)
    with a:
        weight = _num("Confirm / correct weight (kg)", f"dc_w_{k}", help="Doses stay provisional until the doctor confirms weight")
        confirm_w = st.checkbox("Weight reported by patient is correct", key=f"dc_cw_{k}")
        height = _num("Height (cm)", f"dc_h_{k}")
        scr = _num("Serum creatinine (mg/dL)", f"dc_scr_{k}")
    with b:
        lact = st.selectbox("Breastfeeding", TRI, key=f"dc_lact_{k}")
        qt = st.selectbox("QT-risk history", TRI, key=f"dc_qt_{k}")
        preg = st.selectbox("Pregnant (override quiz)", ["", "yes", "no", "possible"], key=f"dc_preg_{k}")
        weeks = _num("Weeks of pregnancy", f"dc_pw_{k}")
        trim = st.selectbox("Trimester", ["", "1", "2", "3"], key=f"dc_tri_{k}")
    with c:
        cp = st.selectbox("Child-Pugh class", ["", "A", "B", "C"], key=f"dc_cp_{k}")
        cps = _num("Child-Pugh score", f"dc_cps_{k}")
        g6 = st.selectbox("G6PD", ["", "normal", "deficient", "unknown"], key=f"dc_g6_{k}")
        ulcer = st.selectbox("Peptic ulcer / GI bleed history", TRI, key=f"dc_ul_{k}")
        heart = st.selectbox("Heart disease", TRI, key=f"dc_hd_{k}")
        meds = st.text_input("Current medicines (replaces quiz list)", key=f"dc_meds_{k}")
    form = st.text_input("Pharmacy form (e.g. 'oral liquid 120 mg/5 mL'; blank = suggest)", key=f"dc_form_{k}").strip() or None
    dpd = _num("Doses per day (only if the rule asks)", f"dc_dpd_{k}")
    mgkg = _num("Intended mg/kg/day (only if the rule asks)", f"dc_mgkg_{k}")
    di = {"weight_kg": weight, "height_cm": height, "scr_mg_dl": scr, "lactating": lact, "qt_history": qt, "pregnant": preg,
          "pregnancy_weeks": weeks, "pregnancy_trimester": trim, "child_pugh_class": cp, "child_pugh_score": cps, "g6pd": g6,
          "ulcer": ulcer, "heart_disease": heart, "meds_text": meds, "doses_per_day": dpd, "mg_per_kg_per_day": mgkg}
    di = {n: v for n, v in di.items() if v not in (None, "")}
    sel = st.session_state.get(f"dc_sel_{k}")
    override = st.text_area("Override reason (only to override a block; logged)", key=f"dc_ov_{k}", height=70).strip() or None
    run = st.button("Run dosage check", type="primary", key=f"dc_run_{k}")
    if run or f"dc_res_{k}" in ss:
        if run:
            ss[f"dc_res_{k}"] = service.evaluate_for_record(
                rec, drug_id, ind, doctor_id=user["username"], doctor_inputs=di, confirmed=["weight_kg"] if confirm_w else [],
                visit_drugs=visit, selected_rule_id=sel, form=form, show_all_rules=show_all, override_reason=override)
            ss[f"dc_di_{k}"] = di
        res = ss[f"dc_res_{k}"]
        _result(rec, user, res, k, ss.get(f"dc_di_{k}", di))


def _result(rec, user, res, k, di):
    from records import store
    st.subheader("Result")
    st.warning(res["banner"] + f" · data status {res['data_status']}")
    {"ok": st.success, "needs_input": st.info, "blocked": st.error, "refused": st.error}[res["status"]](res["status"].upper().replace("_", " "))
    for b in res["blocks"]:
        st.error("⛔ " + b["text"])
    for r in res["refused_reasons"]:
        st.error(r)
    for n in res["needs_input"]:
        st.info(f"Needs input · {n['field']}: {n['why']}")
    if res["dose_mg"] is not None:
        st.metric("Dose", f"{res['dose_mg']:g} mg", f"{res['product']}: " + (f"{res['volume_ml']:g} mL" if res["volume_ml"] else f"{res['units']:g} unit(s)"))
        st.write(f"Interval/frequency: {res['interval_h'] or res['doses_per_day']} · daily total {res['daily_total_mg']} mg · "
                 f"daily max {res['daily_max_mg']} mg · binding cap: {res['binding_cap'] or 'none'}")
    if res["plan"]:
        st.write("Titration plan:", res["plan"])
    if res["text_regimen"]:
        st.write("Regimen (free text from the formulary, not computed):", res["text_regimen"])
    if res["duration"]:
        st.write("Duration:", res["duration"])
    if not res["final"] and res["pending_confirmations"]:
        st.warning("Provisional: confirm " + ", ".join(res["pending_confirmations"]))
    if res["alternatives"]:
        st.markdown("**Alternatives (side by side)**")
        for a in res["alternatives"]:
            tag = " ⭐ suggested" if a["suggested"] else ""
            with st.expander(f"{a['rule_id']} · {a['indication']} · {a['data_status']}{tag}", expanded=a["selected"]):
                st.write({x: a[x] for x in a if x in ("dose_range_mg", "interval_h", "doses_per_day", "duration", "text_regimen", "note", "conflict")})
                st.write("Sources:", ", ".join(f"{s['name']} ({s['url']})" if s.get("url") else s["name"] for s in a["sources"]))
                if st.button("Use this rule", key=f"dc_use_{k}_{a['rule_id']}"):
                    ss[f"dc_sel_{k}"] = a["rule_id"]
                    ss.pop(f"dc_res_{k}", None)
                    st.rerun()
    with st.expander("Calculation steps", expanded=True):
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
    if st.button("Confirm and save to record", disabled=not service.can_confirm(res), key=f"dc_conf_{k}"):
        store.save(service.confirm(rec, res, doctor_id=user["username"], doctor_inputs=di))
        ss.pop(f"dc_res_{k}", None)
        ss[f"saved_{k}"] = "Dosage check confirmed and saved."
        st.rerun()
    if res["blocks"]:
        st.caption("To override a block, type a written reason above and run the check again. The override is logged.")
