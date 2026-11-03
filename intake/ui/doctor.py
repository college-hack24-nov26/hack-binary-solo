"""Doctor page: editable structured summary with edit tracking, optional local-LLM paragraph (off by default)."""
import json
from datetime import datetime

import streamlit as st

from intake import llm_summary
from intake.summary import apply_doctor_edits, body_diagram_svgs, build_summary, duration_text, template_paragraph
from records import store
from records.schema import TimelineEntry

st.title("Doctor summary")
st.warning("AI drafts, the doctor decides. Red flags come from DRAFT rules awaiting source check.")
recs = store.list_records()
if not recs:
    st.info("No patients yet.")
    st.stop()
recs.sort(key=lambda r: (-len(r.redFlags), r.updatedAt))
token = st.selectbox("Patient token", [r.token for r in recs],
                     format_func=lambda t: next(f"{r.token} · {r.complaint.label or '-'}{' · 🔴' if r.redFlags else ''}" for r in recs if r.token == t))
rec = store.load(token)
lang = st.radio("Summary language (body regions)", ["en", "hi", "mr"], horizontal=True,
                format_func={"en": "English", "hi": "हिन्दी", "mr": "मराठी"}.get)
summ = build_summary(rec, lang)

c1, c2 = st.columns(2)
c1.metric("Intake duration (measured)", duration_text(rec.intakeDurationSeconds))
c2.metric("Fields captured", rec.fieldsCaptured)

values = {}
with st.form(f"edit_{token}"):
    for sec in summ.sections:
        st.subheader(sec.title)
        for f in sec.fields:
            if not f.editable:
                (st.error if sec.title == "Red flags" else st.write)(f"**{f.label}**: {f.value}")
                continue
            lbl = f"{'⚠ ' if f.missing else ''}{f.label}{' (edited)' if f.edited else ''}"
            values[f.key] = st.text_area(lbl, value=f.value, key=f"{token}_{lang}_{f.key}", height=70)
            if f.missing:
                st.caption("⚠ missing - not captured at intake")
            if f.edited:
                st.caption(f"Original: {f.original}")
    if st.form_submit_button("Save edits", type="primary"):
        rec = apply_doctor_edits(rec, values, datetime.now().astimezone(), lang)
        store.save(rec)
        st.success(f"Saved. Edited fields: {', '.join(rec.editedFields) or 'none'}")
        st.rerun()

svgs = body_diagram_svgs(rec, lang)
if svgs:
    with st.expander("Body diagram (site red, radiation orange)"):
        for col, svg in zip(st.columns(len(svgs)), svgs):
            col.html(svg)

with st.expander("Attach scanned-record timeline entries (JSON from the OCR page)"):
    raw = st.text_area("Paste a JSON list of timeline entries", key=f"tl_{token}")
    if st.button("Attach") and raw.strip():
        try:
            entries = [TimelineEntry.model_validate(e) for e in json.loads(raw)]
            store.save(rec.model_copy(update={"timeline": rec.timeline + entries}))
            st.rerun()
        except Exception as e:  # noqa: BLE001
            st.error(f"Could not read entries: {type(e).__name__}")

st.subheader("Short paragraph")
use_llm = st.toggle("Draft with local AI (Ollama on this machine)", value=False)
if use_llm and st.button("Generate"):
    with st.spinner("Asking the local model..."):
        st.session_state[f"para_{token}"] = llm_summary.draft_paragraph(summ, enabled=True)
res = st.session_state.get(f"para_{token}") if use_llm else None
if res and res.source == "ai-drafted":
    st.caption(f"🤖 {llm_summary.LABEL}")
    st.write(res.text)
else:
    if res:
        st.caption(f"Template used: {res.reason}")
    st.caption("Template summary (deterministic)")
    st.write(template_paragraph(summ))
