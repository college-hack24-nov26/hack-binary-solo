"""Intake UI (Streamlit). Run: .venv/bin/streamlit run intake_app.py
Pages: patient kiosk, staff alerts, doctor summary. The OCR page is a separate app (app.py)."""
import streamlit as st

st.set_page_config(page_title="Patient intake", layout="wide")
pg = st.navigation([
    st.Page("intake/ui/patient.py", title="Patient", icon="🧑", default=True, url_path="patient"),
    st.Page("intake/ui/staff.py", title="Staff", icon="🚨", url_path="staff"),
    st.Page("intake/ui/doctor.py", title="Doctor", icon="🩺", url_path="doctor"),
])
pg.run()
