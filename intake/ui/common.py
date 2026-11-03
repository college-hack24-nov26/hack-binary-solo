"""Shared by the flow pages: the cached graph/rules and the one IntakeSession of the patient being seen."""
import streamlit as st

from intake.models import load_graph
from intake.redflags import load_rules
from intake.session import IntakeSession
from intake.ui.gate import signed_in

ss = st.session_state


@st.cache_resource
def data():
    return load_graph(), load_rules()


def new_session() -> None:
    g, r = data()
    # a signed-in staff/doctor session starts with the optional old-records scan; the open kiosk goes straight to the quiz
    ss.sess, ss.view, ss.stage = IntakeSession(g, r, language=ss.get("lang", "en")), None, "scan" if signed_in() else "flow"
    ss.demo = False


def get_session() -> IntakeSession:
    if "sess" not in ss:
        new_session()
    return ss.sess
