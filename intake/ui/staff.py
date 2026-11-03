"""Staff page: red flags first, with rule id and the triggering answers. Reads local record files, so it
works from a second screen on the same hospital machine."""
import streamlit as st

from intake.engine import answer_label
from intake.models import load_graph
from records import store

g = load_graph()
st.title("Staff alerts")
st.caption("Red flags come from draft rules and are only a prompt to look at the patient. Not a diagnosis.")


@st.fragment(run_every=5)
def board():
    recs = sorted(store.list_records(), key=lambda r: (-len([f for f in r.redFlags if f.severity == "urgent"]),
                                                       -len(r.redFlags), r.updatedAt))
    if not recs:
        st.info("No patients yet.")
    for r in recs:
        urgent = [f for f in r.redFlags if f.severity == "urgent"]
        head = f"{r.token} · {r.status.replace('_', ' ')} · {r.complaint.label or 'complaint not yet given'}"
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


board()
