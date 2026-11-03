"""Doctor page: editable structured summary with edit tracking, optional local-LLM paragraph (off by default)."""
import json
from datetime import datetime

import streamlit as st

from intake import llm_summary
from intake.summary import apply_doctor_edits, body_diagram_svgs, build_summary, duration_text, template_paragraph
from intake.ui import dosing_panel
from intake.ui.gate import can_edit, require_login
from intake.doctors import doctor_for_login, get_doctor, load_doctors
import pandas as pd

from records import store
from records.vitals import abnormal, bmi
from records.schema import TimelineEntry

user = require_login()
editable = can_edit(user["role"])
st.title("Doctor summary")
if not editable:
    st.info("Read-only: only a doctor can edit and save the summary.")
st.warning("AI drafts, the doctor decides. Red flags come from DRAFT rules awaiting source check.")
recs = store.list_records()
if not recs:
    st.info("No patients yet.")
    st.stop()
DOCTORS = load_doctors()
me = doctor_for_login(user["username"], DOCTORS)           # the doctor this login is linked to, if any
mine = lambda r: bool(me) and r.assignedDoctor == me.id
recs.sort(key=lambda r: (not mine(r), -len(r.redFlags), r.updatedAt))   # my patients first, then by red flags
token = st.selectbox("Patient token", [r.token for r in recs],
                     format_func=lambda t: next(f"{'👤 ' if mine(r) else ''}{r.token} · {r.complaint.label or '-'}{' · 🔴' if r.redFlags else ''}"
                                                f" · {d.name if (d := get_doctor(r.assignedDoctor, DOCTORS)) else 'no doctor chosen'}"
                                                for r in recs if r.token == t))
rec = store.load(token)
lang = st.radio("Summary language (body regions)", ["en", "hi", "mr"], horizontal=True,
                format_func={"en": "English", "hi": "हिन्दी", "mr": "मराठी"}.get)
summ = build_summary(rec, lang)

c1, c2 = st.columns(2)
c1.metric("Intake duration (measured)", duration_text(rec.intakeDurationSeconds))
c2.metric("Fields captured", rec.fieldsCaptured)

di = rec.dosingInputs
st.header("Clinical overview")
doc = get_doctor(rec.assignedDoctor, DOCTORS)
st.caption(f"{rec.token} · {rec.status.replace('_', ' ')} · complaint: {rec.complaint.label or 'not given'}"
           f" · assigned: {doc.name if doc else 'no doctor chosen'}")
if rec.redFlags:
    st.caption(f"🔴 {len(rec.redFlags)} red flag(s), details under 'Red flags' in the intake summary below (draft rules).")

# -- patient basics and safety information (patient-reported at intake)
st.subheader("Patient and safety basics (patient-reported)")
b1, b2, b3, b4 = st.columns(4)
b1.metric("Age", f"{di.ageYears:g} y" if di.ageYears is not None else "not captured")
b2.metric("Sex", di.sex or "not captured")
b3.metric("Weight (reported)", f"{di.weightKg:g} kg" if di.weightKg is not None else "not captured")
b4.metric("Pregnancy", (di.pregnancy or "not captured").replace("_", " "))
st.write("**Allergies:** " + (", ".join(di.allergies) if di.allergies else "none reported"))
st.write("**Current medicines:** " + (", ".join(di.currentMeds) if di.currentMeds else "none reported"))
conds = [n for n, v in (("kidney disease", di.renal), ("liver disease", di.hepatic), ("diabetes", di.diabetes),
                        ("hypertension", di.hypertension), ("asthma", di.asthma)) if v == "yes"]
unsure = [n for n, v in (("kidney", di.renal), ("liver", di.hepatic), ("diabetes", di.diabetes),
                         ("hypertension", di.hypertension), ("asthma", di.asthma)) if v == "unsure"]
st.write("**Conditions reported:** " + (", ".join(conds) if conds else "none reported") + (f" · not sure: {', '.join(unsure)}" if unsure else ""))
if di.missing:
    st.warning("Not captured at intake (skipped or not sure): " + ", ".join(di.missing))

# -- vitals measured by staff
st.subheader("Vitals (measured by staff)")
vt = rec.vitals
if vt is None or not vt.any_measured():
    st.info("No vitals recorded yet. Staff enter them on the Staff alerts page.")
else:
    flags = abnormal(vt, di.ageYears)
    mark = lambda k, txt: f"{'⚠ ' if k in flags else ''}{txt}"
    cells = [("BP (mmHg)", f"{vt.bpSystolic or '-'}/{vt.bpDiastolic or '-'}", [k for k in ("bpSystolic", "bpDiastolic") if k in flags]),
             ("Pulse (/min)", vt.pulse, ["pulse"]), ("Temp (°C)", vt.tempC, ["tempC"]), ("SpO₂ (%)", vt.spo2, ["spo2"]),
             ("Resp rate (/min)", vt.respRate, ["respRate"]), ("Weight (kg)", vt.weightKg, []), ("Height (cm)", vt.heightCm, []),
             ("BMI", bmi(vt), []), ("Glucose (mg/dL)", vt.bloodGlucose, ["bloodGlucose"])]
    for row in (cells[:5], cells[5:]):
        for col, (lab, val, keys) in zip(st.columns(5), row):
            col.metric(lab, "-" if val in (None, "") else (("⚠ " if any(k in flags for k in keys) else "") + str(val)))
    if flags:
        st.warning("Outside the usual adult range (draft thresholds, doctor decides): " + ", ".join(f"{k} {w}" for k, w in flags.items()))
    elif (di.ageYears or 99) < 12:
        st.caption("Adult ranges are not applied to children.")
    if di.weightKg and vt.weightKg and abs(di.weightKg - vt.weightKg) / vt.weightKg > 0.1:
        st.warning(f"Reported weight {di.weightKg:g} kg differs from measured {vt.weightKg:g} kg. Use the measured value for dosing.")
    st.caption(f"Recorded by {vt.recordedBy or '?'} at {(vt.recordedAt or '')[:16].replace('T', ' ')}" + (f" · {vt.notes}" if vt.notes else ""))

# -- prior OPD records scanned with OCR
st.subheader("Attached OCR records (prior OPD)")
if not rec.timeline:
    st.info("No scanned prescriptions or lab reports attached.")
for e in sorted(rec.timeline, key=lambda e: e.date, reverse=True):
    tag = "✏ edited by doctor" if e.editedByDoctor else "as read by OCR"
    with st.expander(f"{e.date} · {e.type.replace('_', ' ')} · {len(e.items)} item(s) · {tag}", expanded=True):
        if e.diagnoses:
            st.write("**Diagnoses as written:** " + "; ".join(e.diagnoses))
        if e.items:
            cols = ["nameAsWritten", "strength", "frequencyAsWritten", "durationAsWritten", "notes"] if e.type == "prescription" \
                else ["test", "value", "unit", "referenceRange", "flag"]
            df = pd.DataFrame(e.items)
            show = [c for c in cols if c in df.columns and df[c].notna().any()] or list(df.columns[:5])
            st.dataframe(df[show], hide_index=True, width="stretch")
        st.caption(f"Confirmed by {getattr(e, 'confirmedBy', None) or 'unknown'} · source: {e.source}"
                   + (f" · edited fields: {', '.join(e.editedFields)}" if e.editedFields else ""))

# -- doctor's own notes
st.subheader("Doctor's notes (assessment / plan)")
if not editable:
    st.caption("Read-only for staff.")
with st.form(f"notes_{token}"):
    notes = st.text_area("Notes", value=rec.doctorNotes, height=140, disabled=not editable, key=f"notes_{token}_t",
                         placeholder="Assessment, investigations, plan, follow-up. Written by the doctor.")
    if st.form_submit_button("Save notes", type="primary", disabled=not editable):
        store.save(rec.model_copy(update={"doctorNotes": notes.strip()}))
        st.session_state[f"saved_{token}"] = "Notes saved."
        st.rerun()
st.divider()
st.header("Intake summary (editable)")

if msg := st.session_state.pop(f"saved_{token}", None):      # shown once, after the rerun that reloads the saved record
    st.success(msg)
values = {}
with st.form(f"edit_{token}"):
    for sec in summ.sections:
        st.subheader(sec.title)
        for f in sec.fields:
            if not f.editable:
                (st.error if sec.title == "Red flags" else st.write)(f"**{f.label}**: {f.value}")
                continue
            lbl = f"{'⚠ ' if f.missing else ''}{f.label}{' :orange[**(edited)**]' if f.edited else ''}"
            values[f.key] = st.text_area(lbl, value=f.value, key=f"{token}_{lang}_{f.key}", height=70, disabled=not editable)
            if f.missing:
                st.caption("⚠ missing - not captured at intake")
            if f.edited:
                st.caption(f"Original: {f.original}")
    if st.form_submit_button("Save edits", type="primary", disabled=not editable):
        rec = apply_doctor_edits(rec, values, datetime.now().astimezone(), lang)
        store.save(rec)
        st.session_state[f"saved_{token}"] = f"Saved. Edited fields: {', '.join(rec.editedFields) or 'none'}"
        st.rerun()

svgs = body_diagram_svgs(rec, lang)
if svgs:
    with st.expander("Body diagram (site red, radiation orange)"):
        for col, svg in zip(st.columns(len(svgs)), svgs):
            col.image(svg)

with st.expander("Attach scanned-record timeline entries (JSON from the OCR page)"):
    raw = st.text_area("Paste a JSON list of timeline entries", key=f"tl_{token}", disabled=not editable)
    if st.button("Attach", disabled=not editable) and raw.strip():
        try:
            entries = [TimelineEntry.model_validate(e) for e in json.loads(raw)]
            store.save(rec.model_copy(update={"timeline": rec.timeline + entries}))
            st.rerun()
        except Exception as e:  # noqa: BLE001
            st.error(f"Could not read entries: {type(e).__name__}")

st.subheader("Short paragraph")
use_llm = st.toggle("Draft with local AI (Ollama on this machine)", value=False)
if use_llm and st.button("Generate"):
    with st.spinner("Asking the local model..."):
        st.session_state[f"para_{token}"] = llm_summary.draft_paragraph(summ, enabled=True)
res = st.session_state.get(f"para_{token}") if use_llm else None
if res and res.source == "ai-drafted":
    st.caption(f"🤖 {llm_summary.LABEL}")
    st.write(res.text)
else:
    if res:
        st.caption(f"Template used: {res.reason}")
    st.caption("Template summary (deterministic)")
    st.write(template_paragraph(summ))

st.divider()
# -- dosage check (doctor only), last on the page
dosing_panel.render(rec, user, editable)
