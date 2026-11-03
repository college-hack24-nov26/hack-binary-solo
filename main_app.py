"""One entry point with the three steps in order. Run: .venv/bin/streamlit run main_app.py
1. Sign in (staff / doctor)  2. Patient section: scan old records (OCR, optional) then the quiz.  Staff board, Doctor summary and Dosage check follow."""
import streamlit as st

from intake.ui import offline_badge
from intake.ui.gate import signed_in

st.set_page_config(page_title="Patient intake", layout="wide")
offline_badge.render()
if not signed_in():
    pages = [st.Page("intake/ui/signin.py", title="1 · Sign in", icon="🔐", default=True, url_path="signin")]
else:
    pages = [
        st.Page("intake/ui/patient.py", title="2 · Patient (scan, then quiz)", icon="🧑", default=True, url_path="patient"),
        st.Page("intake/ui/staff.py", title="Staff board", icon="🚨", url_path="staff"),
        st.Page("intake/ui/doctor.py", title="Doctor summary", icon="🩺", url_path="doctor"),
        st.Page("intake/ui/dosage.py", title="Dosage check", icon="💊", url_path="dosage"),
    ]
    if st.session_state["auth"]["role"] == "doctor":          # the page also refuses other roles; this just hides the link
        pages.append(st.Page("intake/ui/audit_log.py", title="Audit log", icon="📜", url_path="audit"))
st.navigation(pages).run()
