"""Patient kiosk page: consent -> questions -> review -> done. Large tap targets, Back, language toggle."""
import html

import streamlit as st

from intake.conditions import SKIPPED, UNSURE
from intake.demo import load_demo
from intake.doctors import get_doctor, load_doctors
from intake.engine import answer_label
from intake.models import load_graph
from intake.redflags import load_rules
from intake.session import IntakeSession
from intake.ui import common
from intake.ui.gate import signed_in
from intake.ui.bodymap_input import body_map_input
from intake.ui.ocr_panel import render as render_scan
from intake.ui.strings import t
from records import store

st.markdown("""<style>
div.stButton > button { min-height: 4.2rem; font-size: 1.35rem; white-space: normal; }
div.block-container { padding-top: 2.5rem; }
h1 { font-size: 2rem !important; padding: 0 0 .25rem 0 !important; }
div[data-testid="stCheckbox"] label p { font-size: 1.3rem; }
</style>""", unsafe_allow_html=True)

ss = st.session_state


_data = common.data
_new = common.new_session

if "sess" not in ss:
    _new()
sess: IntakeSession = ss.sess
g, _ = _data()


def _save():
    if sess.consented:
        store.save(sess.to_record(complete=False, prior=store.load(sess.token)))


def _set(node_id, value):
    sess.answer(node_id, value)
    ss.view = None
    if sess.declined:
        store.delete(sess.token)
    else:
        _save()


def _demo():
    g, r = _data()
    ss.sess, ss.view, ss.stage = load_demo(g, r, language=ss.get("lang", "en")), None, "flow"
    ss.demo = True
    store.save(ss.sess.to_record(complete=False))   # no prior: a repeat demo replaces the record, doctor edits included


def _go_back(view):
    ss.view = sess.previous(view)


# ---- language toggle (always visible)
labels = {"en": "English", "hi": "हिन्दी", "mr": "मराठी"}
# the widget key is already updated on the run that switches language, so the label follows it immediately
lang = st.radio(t("language", ss.get("lang_radio", ss.get("lang", "en"))), list(labels), format_func=labels.get, horizontal=True,
                index=list(labels).index(ss.get("lang", "en")), key="lang_radio")
ss.lang = sess.language = lang
st.title(t("title", lang))

# red-flag banner: neutral message only, no detail, no diagnosis
if sess.red_flags and not sess.declined:
    st.warning(sess.red_flags[0].patientMessage[lang], icon="⚠️")

if sess.declined:
    st.info(t("declined", lang))
    st.button(t("new", lang), on_click=_new)
    st.stop()

if ss.stage == "scan":                             # optional: scan old records before the quiz (staff / doctor signed in)
    if not signed_in():
        ss.stage = "flow"
        st.rerun()

    def _to_quiz():
        ss.stage = "flow"
        st.rerun()

    st.subheader("Scan old records")
    render_scan(ss.auth, sess, _to_quiz)
    st.stop()

if ss.stage == "doctor":                           # patient picks the doctor after the quiz
    st.subheader(t("choose_doctor", lang))
    st.caption(t("choose_doctor_hint", lang))

    def _choose(doctor_id):
        sess.assigned_doctor = doctor_id
        rec = store.load(sess.token)
        if rec is not None:
            store.save(rec.model_copy(update={"assignedDoctor": doctor_id}))
        ss.stage = "done"

    for d in load_doctors():
        st.button(f"**{d.name}**  \n{d.specialty.get(lang)}", key=f"doc_{d.id}", use_container_width=True, on_click=_choose, args=(d.id,))
    st.button(t("any_doctor", lang), key="doc_any", use_container_width=True, on_click=_choose, args=(None,))
    st.stop()

if ss.stage == "done":
    if (d := get_doctor(sess.assigned_doctor)):
        st.info(f"{t('your_doctor', lang)}: {d.label(lang)}")
    st.success(t("done", lang))
    st.button(t("new", lang), on_click=_new)
    st.stop()

view = ss.view or sess.pending
if view is None:                                   # path complete -> review screen
    st.subheader(t("review", lang))
    if ss.get("demo"):
        st.info(t("demo_note", lang))
    for nid in sess.path:
        n = g.node(nid)
        if n.section == "consent":
            continue
        c1, c2 = st.columns([5, 1])
        c1.markdown(f"**{n.text.get(lang)}**  \n{answer_label(n, sess.answers[nid], lang)}")
        if c2.button(t("change", lang), key=f"chg_{nid}"):
            ss.view = nid
            st.rerun()
    if st.button(t("confirm", lang), type="primary", use_container_width=True):
        rec = sess.finish()
        prior = store.load(sess.token)   # staff may have recorded vitals while the patient was answering
        rec = rec.model_copy(update={"doctorEdits": {}, "editedFields": [], "vitals": prior.vitals if prior else None})
        store.save(rec)
        ss.stage = "doctor"
        st.rerun()
    st.stop()

node = g.node(view)
done, total = sess.progress()
cur = sess.answers.get(view)
is_consent = node.section == "consent"
q_col = st.container()
if node.type == "body_map":   # map on the left, question and buttons on the right: Next stays on screen on a 768 px tablet
    map_col, q_col = st.columns([5, 6])
with q_col:
    st.progress(min(done / max(total, 1), 1.0), text=f"{t('progress', lang)} {done + 1 if view not in sess.answers else done} / ~{total}")
if is_consent:   # the consent paragraph is long: normal-weight text, not a page-sized header
    st.markdown(f"<p style='font-size:1.35rem;line-height:1.5'>{html.escape(node.text.get(lang))}</p>", unsafe_allow_html=True)
else:
    with q_col:
        st.header(node.text.get(lang))

if node.type in ("single_choice", "yes_no_unsure"):
    for o in node.options:
        if st.button(o.get(lang), key=f"{view}_{o.id}", use_container_width=True,
                     type="primary" if cur == o.id else "secondary"):
            _set(view, o.id)
            st.rerun()
elif node.type == "multi_choice":
    st.caption(t("pick_many", lang))
    prev = cur if isinstance(cur, list) and cur != [UNSURE] else []
    picks = [o.id for o in node.options if st.checkbox(o.get(lang), value=o.id in prev, key=f"{view}_{o.id}")]
    if st.button(t("next", lang), key=f"{view}_next", type="primary", use_container_width=True, disabled=not picks):
        try:
            _set(view, picks)
            st.rerun()
        except ValueError as e:
            st.error(str(e))
elif node.type == "number":
    d = cur if isinstance(cur, (int, float)) and not isinstance(cur, bool) else None
    val = st.number_input(node.text.get(lang), min_value=float(node.min), max_value=float(node.max), value=d, key=f"{view}_num",
                          step=1.0, label_visibility="collapsed")
    if st.button(t("next", lang), key=f"{view}_next", type="primary", use_container_width=True, disabled=val is None):
        _set(view, int(val) if float(val).is_integer() else float(val))
        st.rerun()
elif node.type == "scale_0_10":
    cols = st.columns(11)
    for i, c in enumerate(cols):
        if c.button(str(i), key=f"{view}_s{i}", type="primary" if cur == i else "secondary"):
            _set(view, i)
            st.rerun()
elif node.type == "body_map":
    ans = body_map_input(node, lang, cur, map_col, q_col)
    if ans is not None:
        _set(view, ans)
        st.rerun()
else:  # free_text
    txt = st.text_area(t("type_here", lang), value=cur if isinstance(cur, str) and cur not in (UNSURE, SKIPPED) else "",
                       key=f"{view}_txt", label_visibility="collapsed")
    if st.button(t("next", lang), key=f"{view}_next", type="primary", use_container_width=True, disabled=not txt.strip()):
        _set(view, txt.strip())
        st.rerun()

st.divider()
b1, b2, b3 = st.columns(3)
if sess.previous(view) is not None:
    b1.button(t("back", lang), key="back", on_click=_go_back, args=(view,), use_container_width=True)
if not is_consent:
    if node.type not in ("yes_no_unsure", "body_map") and b2.button(t("unsure", lang), key="unsure", use_container_width=True):
        _set(view, [UNSURE] if node.type == "multi_choice" else UNSURE)
        st.rerun()
    if b3.button(t("skip", lang), key="skip", use_container_width=True):
        _set(view, SKIPPED)
        st.rerun()
else:
    st.button(t("demo", lang), key="demo_mode", on_click=_demo, use_container_width=True)
