"""Dosage check page: pick a patient, run the doctor-only dosage panel."""
import streamlit as st

from intake.ui import dosing_panel
from intake.ui.gate import can_edit, require_login
from records import store

user = require_login()
st.title("Dosage check")
recs = store.list_records()
if not recs:
    st.info("No patients yet. Complete the quiz on the Patient page first.")
    st.stop()
token = st.selectbox("Patient token", [r.token for r in recs], key="dosage_patient",
                     format_func=lambda t: next(f"{r.token} · {r.complaint.label or '-'}" for r in recs if r.token == t))
dosing_panel.render(store.load(token), user, can_edit(user["role"]))
