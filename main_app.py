"""One entry point with the three steps in order. Run: .venv/bin/streamlit run main_app.py
1. Sign in (staff / doctor)  2. Scan old records (OCR, optional)  3. Patient quiz.  Staff board and Doctor summary follow."""
import streamlit as st

from intake.ui.gate import signed_in

st.set_page_config(page_title="Patient intake", layout="wide")
if not signed_in():
    pages = [st.Page("intake/ui/signin.py", title="1 · Sign in", icon="🔐", default=True, url_path="signin")]
else:
    pages = [
        st.Page("intake/ui/ocr_scan.py", title="2 · Scan old records", icon="📄", default=True, url_path="scan"),
        st.Page("intake/ui/patient.py", title="3 · Patient quiz", icon="🧑", url_path="quiz"),
        st.Page("intake/ui/staff.py", title="Staff board", icon="🚨", url_path="staff"),
        st.Page("intake/ui/doctor.py", title="Doctor summary", icon="🩺", url_path="doctor"),
    ]
st.navigation(pages).run()
