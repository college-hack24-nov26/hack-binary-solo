"""Read-only audit-log viewer. Doctor role only. No edit or delete controls; exports are of the rows currently shown."""
import streamlit as st

from dosing import audit, audit_view
from intake.ui.gate import require_login

user = require_login(allowed=("doctor",))
st.title("Audit log")
st.caption("Read-only. Every dosage evaluation, confirmation, override and History-check answer, newest first.")

entries = audit.read()
if audit.verify():
    st.success("Chain verified: no line has been changed, removed or reordered.")
else:
    st.error("Chain broken: the log was edited, truncated or reordered after it was written.")

all_rows = audit_view.rows(entries)
if not all_rows:
    st.info("No audit entries yet.")
    st.stop()

c1, c2, c3 = st.columns(3)
patient = c1.selectbox("Patient", [""] + sorted({r["patient"] for r in all_rows if r["patient"]}), key="al_patient", format_func=lambda v: v or "all")
drug = c2.selectbox("Drug", [""] + sorted({r["drug"] for r in all_rows if r["drug"] and r["drug"] != "-"}), key="al_drug", format_func=lambda v: v or "all")
action = c3.selectbox("Action", [""] + list(audit_view.ACTIONS.values()), key="al_action", format_func=lambda v: v or "all")
d1, d2 = st.columns(2)
start = d1.date_input("From", value=None, key="al_from")
end = d2.date_input("To", value=None, key="al_to")
shown = audit_view.filter_rows(all_rows, patient or None, drug or None, action or None, start, end)

st.write(f"**{len(shown)}** of {len(all_rows)} entries")
st.dataframe([{k: r[k] for k in ("time", "doctor", "patient", "drug", "status", "action")} for r in shown], width="stretch", hide_index=True)
e1, e2 = st.columns(2)
e1.download_button("Export shown rows (JSON)", audit_view.to_json(shown), "audit_log.json", "application/json", key="al_json")
e2.download_button("Export shown rows (CSV)", audit_view.to_csv(shown), "audit_log.csv", "text/csv", key="al_csv")

st.subheader("Details")
for r in shown[:200]:
    with st.expander(f"{r['time']} · {r['patient']} · {r['drug']} · {r['status'] or '-'} · {r['action']}"):
        d = audit_view.detail(r["entry"])
        if d["override_category"] or d["override_reason"]:
            st.markdown(f":red[**Override**] · category: {d['override_category']} · reason: {d['override_reason']}"
                        + (f" · block: {d['overridden_block']}" if d["overridden_block"] else ""))
        st.markdown("**Inputs**")
        st.json(d["inputs"], expanded=False)
        st.markdown("**Provenance**")
        st.json(d["provenance"], expanded=False)
        for title, key in (("Calculation steps", "calculation_steps"), ("Warnings", "warnings"), ("Interactions", "interactions"), ("Blocks", "blocks")):
            if d[key]:
                st.markdown(f"**{title}**")
                for x in d[key]:
                    st.write("• " + str(x))
        if d["sources"]:
            st.markdown("**Sources**")
            for s in d["sources"]:
                st.write(f"• {s.get('id') or '-'} · {s.get('name')}" + (f" · {s['url']}" if s.get("url") else ""))
        st.caption(f"hash {r['hash']}")
if len(shown) > 200:
    st.caption("Showing the newest 200 details; exports contain every shown row.")
