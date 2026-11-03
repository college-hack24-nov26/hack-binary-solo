"""Staff page: red flags first, with rule id and the triggering answers. Reads local record files, so it
works from a second screen on the same hospital machine."""
from datetime import datetime

import streamlit as st

from intake.engine import answer_label
from intake.models import load_graph
from intake.ui.gate import require_login
from intake.doctors import get_doctor, load_doctors
from pydantic import ValidationError

from records import store
from records.schema import Vitals
from records.vitals import abnormal

user = require_login()   # staff or doctor

g = load_graph()
DOCTORS = load_doctors()
st.title("Staff alerts")
st.caption("Red flags come from draft rules and are only a prompt to look at the patient. Not a diagnosis.")


def vitals_form(r):
    """Staff measure and enter vitals; the doctor page shows them. A save replaces the previous set."""
    v = r.vitals or Vitals()
    st.markdown("**Vitals (measured)**" + (f" · last saved {v.recordedAt[:16].replace('T', ' ')} by {v.recordedBy}" if v.recordedAt else ""))
    with st.form(f"vitals_{r.token}"):
        a, b, c = st.columns(3)
        sys_ = a.number_input("BP systolic (mmHg)", 0, 300, v.bpSystolic or None, step=1)
        dia = b.number_input("BP diastolic (mmHg)", 0, 200, v.bpDiastolic or None, step=1)
        pulse = c.number_input("Pulse (/min)", 0, 250, v.pulse or None, step=1)
        a, b, c = st.columns(3)
        temp = a.number_input("Temperature (°C)", 0.0, 45.0, v.tempC or None, step=0.1, format="%.1f")
        spo2 = b.number_input("SpO₂ (%)", 0, 100, v.spo2 or None, step=1)
        rr = c.number_input("Respiratory rate (/min)", 0, 80, v.respRate or None, step=1)
        a, b, c = st.columns(3)
        wt = a.number_input("Weight (kg)", 0.0, 400.0, v.weightKg or None, step=0.5)
        ht = b.number_input("Height (cm)", 0.0, 250.0, v.heightCm or None, step=1.0)
        glu = c.number_input("Blood glucose (mg/dL)", 0.0, 900.0, v.bloodGlucose or None, step=1.0)
        notes = st.text_input("Notes (e.g. fasting, arm used, taken after rest)", v.notes)
        if st.form_submit_button("Save vitals", type="primary"):
            z = lambda x: x or None            # 0 means "not entered"
            try:
                new = Vitals(bpSystolic=z(sys_), bpDiastolic=z(dia), pulse=z(pulse), tempC=z(temp), spo2=z(spo2), respRate=z(rr),
                             weightKg=z(wt), heightCm=z(ht), bloodGlucose=z(glu), notes=notes.strip(),
                             recordedBy=user["username"], recordedAt=datetime.now().astimezone().isoformat(timespec="seconds"))
            except ValidationError as e:
                st.error("Check the values: " + "; ".join(f"{x['loc'][0]} {x['msg']}" for x in e.errors()))
            else:
                if new.bpSystolic and new.bpDiastolic and new.bpSystolic <= new.bpDiastolic:
                    st.error("Systolic must be higher than diastolic.")
                else:
                    store.save(store.load(r.token).model_copy(update={"vitals": new}))
                    st.session_state[f"vit_saved_{r.token}"] = True
                    st.rerun()
    if st.session_state.pop(f"vit_saved_{r.token}", None):
        st.success("Vitals saved. The doctor can see them now.")
    if r.vitals and (flags := abnormal(r.vitals, r.dosingInputs.ageYears)):
        st.warning("Outside the usual adult range (draft thresholds): " + ", ".join(f"{k} {w}" for k, w in flags.items()))


@st.fragment(run_every=5)
def board():
    recs = sorted(store.list_records(), key=lambda r: (-len([f for f in r.redFlags if f.severity == "urgent"]),
                                                       -len(r.redFlags), r.updatedAt))
    if not recs:
        st.info("No patients yet.")
    for r in recs:
        urgent = [f for f in r.redFlags if f.severity == "urgent"]
        doc = get_doctor(r.assignedDoctor, DOCTORS)
        head = (f"{r.token} · {r.status.replace('_', ' ')} · {r.complaint.label or 'complaint not yet given'}"
                f" · {'→ ' + doc.name if doc else 'no doctor chosen'}")
        icon = "🔴 " if urgent else "🟠 " if r.redFlags else ""
        with st.expander(f"{icon}{head}", expanded=bool(r.redFlags)):
            for f in r.redFlags:
                (st.error if f.severity == "urgent" else st.warning)(
                    f"**{f.severity.upper()}** - {f.staffMessage}\n\nRule `{f.ruleId}` · "
                    f"{'*' + f.label + '*' if f.draft else f.label}")
                for nid, v in f.triggeredBy.items():
                    n = g.node(nid)
                    st.write(f"- {n.shortLabel or n.text.en}: **{answer_label(n, v)}**")
            if not r.redFlags:
                st.write("No red flags.")
            if r.dosingInputs.missing:
                st.write("Missing safety basics: " + ", ".join(r.dosingInputs.missing))
            vitals_form(r)


board()
