"""'Load demo patient' control, shown only when DEMO_MODE is on and a doctor is signed in. It saves the fixture's record
(built by replaying the answers through the real quiz session) and selects it, so the demo starts on the normal doctor
screens with the normal dosage panel. Nothing here is canned output."""
import streamlit as st

from dosing import demo
from intake import offline
from records import store

ss = st.session_state
PICKERS = ("doctor_patient", "dosage_patient")       # the patient selectboxes of the Doctor and Dosage check pages


def _load(key: str) -> None:
    rec = demo.record(key)
    for k in [k for k in ss.keys() if isinstance(k, str) and rec.token in k]:
        del ss[k]                                    # forget earlier dosage-panel state for this demo patient
    store.save(rec)
    for p in PICKERS:
        ss[p] = rec.token
    ss["demo_loaded"] = key


def render(user: dict) -> None:
    if not offline.demo_mode() or user.get("role") != "doctor":
        return
    with st.container(border=True):
        st.caption("DEMO_MODE is on · synthetic patients only")
        c1, c2 = st.columns([3, 1])
        key = c1.selectbox("Demo patient", list(demo.DEMO_PATIENTS), key="demo_pick", label_visibility="collapsed",
                           format_func=lambda k: f"{demo.DEMO_PATIENTS[k]['displayName']} · {demo.DEMO_PATIENTS[k]['title'].split('. ', 1)[1]}")
        c2.button("Load demo patient", key="demo_load", on_click=_load, args=(key,), use_container_width=True)
        if ss.get("demo_loaded"):
            fx = demo.DEMO_PATIENTS[ss["demo_loaded"]]
            st.success(f"Loaded {fx['displayName']} ({fx['token']}). Open the patient below and run the dosage check.")
