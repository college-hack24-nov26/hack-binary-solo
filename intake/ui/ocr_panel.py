"""The scan-old-records panel (local OCR): used inside the patient section before the quiz, and by the standalone page.
A doctor confirms each scan; confirmed entries go straight onto the current patient's record timeline. Optional."""
import copy
import io

import pandas as pd
import streamlit as st
from PIL import Image

from intake.ui.gate import can_edit
from ocr import ollama_client, service, session
from ocr.config import load_settings
from ocr.timeline import edited_fields, to_timeline_entry
from records import store
from records.schema import TimelineEntry

MED_COLS = ["nameAsWritten", "strength", "form", "route", "frequencyAsWritten", "durationAsWritten", "notes"]
LAB_COLS = ["test", "value", "unit", "referenceRange", "flag"]
DOC_TYPES = ["prescription", "lab_report", "discharge_summary", "other"]

ss = st.session_state


def render(user: dict, sess, on_continue) -> None:
    """Draw the panel for `sess`. `on_continue()` is called when the user moves on to the quiz. May st.stop()."""
    role = user["role"]
    S = load_settings()
    session.purge_tmp(S.tmp_dir)
    session.sweep(S.tmp_dir, S.session_ttl_s)
    ss.setdefault("review", None)   # {sessionId, original, latencyS}


    def clear_review(delete_image=True):
        if ss.review and delete_image:
            session.delete(S.tmp_dir, ss.review["sessionId"])
        ss.review = None


    def hl(row):
        return ["background-color: #fff3cd; color: #000" if row["⚠ review"] else "" for _ in row]


    st.caption(f"Patient token {sess.token} · {len(sess.timeline)} scan(s) attached. Printed/typed text only. AI drafts, the doctor decides.")
    with st.sidebar:
        h = service.health(S)
        st.write(f"Ollama: {'🟢 up' if h['ollamaUp'] else '🔴 down'}")
        st.write(f"Model `{S.model}`: {'🟢 present' if h['modelPresent'] else '🔴 missing'}")
        if h["ollamaUp"] and h["modelPresent"] and st.button("Pre-warm model"):
            with st.spinner("Loading model…"):
                ollama_client.warm(S)

    if ss.review is None:
        consent = st.checkbox("Patient has given explicit consent to scan this document")
        tab_up, tab_cam = st.tabs(["Upload", "Camera"])
        with tab_up:
            up = st.file_uploader("Prescription / lab report image", type=["png", "jpg", "jpeg", "webp"])
        with tab_cam:
            cam = st.camera_input("Take a photo of the document")
        f = up or cam
        if f and st.button("Extract", type="primary", disabled=not consent):
            with st.spinner(f"Reading document with {S.model} (can take ~30-60 s)…"):
                try:
                    r = service.extract(f.getvalue(), consent, role, S)
                except service.OcrRefused as e:
                    st.error(f"Refused: {e}")
                    st.stop()
            if not r["ok"]:
                st.error(f"Could not read this document ({r['error']}). Please enter the details manually.")
            else:
                ss.review = {"sessionId": r["sessionId"], "original": r["result"], "latencyS": r["latencyS"]}
                st.rerun()
        if not consent:
            st.info("Tick consent to enable extraction.")
        st.divider()
        if st.button("Next: patient quiz →" if sess.timeline else "Skip scanning, go to the quiz →", type="primary"):
            on_continue()
        st.stop()

    rv = ss.review
    img = session.read(S.tmp_dir, rv["sessionId"])
    if img is None:
        st.error("Review session timed out and the image was deleted. Please scan again.")
        clear_review(False)
        st.button("OK")
        st.stop()
    orig = rv["original"]
    left, right = st.columns([2, 3])
    with left:
        st.image(Image.open(io.BytesIO(img)), caption=f"Source (deleted on confirm/cancel/timeout) · {rv['latencyS']}s", width="stretch")
    with right:
        dt = st.selectbox("Document type", DOC_TYPES, index=DOC_TYPES.index(orig["documentType"]))
        date = st.text_input("Document date (as written)", orig["documentDate"] or "")
        n_review = sum(x["needsReview"] for x in orig["medications"] + orig["labResults"])
        if n_review:
            st.warning(f"{n_review} item(s) need your review (highlighted).")
        for w in orig["warnings"]:
            st.caption(f"⚠ model note: {w}")
        if orig["unreadable"]:
            st.error("Unreadable: " + "; ".join(orig["unreadable"]))

        st.subheader("Medications")
        mdf = pd.DataFrame([{**{c: m[c] for c in MED_COLS},
                             "parsed frequency": m["frequencyParsed"]["display"] or "not understood",
                             "formulary match": f"{m['suggestedGeneric']} ({m['matchScore']})" if m["suggestedGeneric"] else "none",
                             "why flagged": ", ".join(m["reviewReasons"]), "⚠ review": m["needsReview"]} for m in orig["medications"]])
        m_out = st.data_editor(mdf.style.apply(hl, axis=1) if len(mdf) else mdf, num_rows="dynamic", width="stretch",
                               disabled=["parsed frequency", "formulary match", "why flagged", "⚠ review"], key="med_editor")
        st.subheader("Lab results")
        ldf = pd.DataFrame([{**{c: l[c] for c in LAB_COLS}, "why flagged": ", ".join(l["reviewReasons"]), "⚠ review": l["needsReview"]}
                            for l in orig["labResults"]])
        l_out = st.data_editor(ldf.style.apply(hl, axis=1) if len(ldf) else ldf, num_rows="dynamic", width="stretch",
                               disabled=["why flagged", "⚠ review"], key="lab_editor")
        dx = st.text_area("Diagnoses (one per line)", "\n".join(orig["diagnosesAsWritten"]))

        def rows(df, cols):
            return [{c: (None if pd.isna(r[c]) or r[c] == "" else r[c]) for c in cols} for _, r in df.iterrows()]

        edited = copy.deepcopy(orig)
        edited.update(documentType=dt, documentDate=date or None, diagnosesAsWritten=[x.strip() for x in dx.splitlines() if x.strip()])
        for src, new in ((edited["medications"], rows(m_out, MED_COLS)), (edited["labResults"], rows(l_out, LAB_COLS))):
            for i, row in enumerate(new):
                if i < len(src):
                    src[i].update(row)
                else:
                    src.append(row)
            del src[len(new):]
        edits = edited_fields(orig, edited)
        if edits:
            st.caption(f"Edited by you: {len(edits)} field(s)")

        c1, c2 = st.columns(2)
        if not can_edit(role):
            c1.caption("Only a doctor can confirm. Ask the doctor to review this screen.")
        if c1.button("✅ Confirm and attach to patient", type="primary", disabled=not can_edit(role)):
            sess.timeline.append(TimelineEntry.model_validate(to_timeline_entry(edited, edits, user["username"])))
            if sess.consented:   # before the quiz consent nothing is stored; the entry is saved with the record once consent is given
                store.save(sess.to_record(complete=False, prior=store.load(sess.token)))
            clear_review()
            st.rerun()
        if c2.button("Cancel (discard)"):
            clear_review()
            st.rerun()
