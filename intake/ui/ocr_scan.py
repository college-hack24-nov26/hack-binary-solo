"""Standalone scan page (also embedded as the first stage of the patient section). Optional: next is the quiz."""
import streamlit as st

from intake.ui import common
from intake.ui.gate import require_login
from intake.ui.ocr_panel import render

user = require_login()
sess = common.get_session()
st.title("Step 2 · Scan old records")
render(user, sess, lambda: st.switch_page("intake/ui/patient.py"))
