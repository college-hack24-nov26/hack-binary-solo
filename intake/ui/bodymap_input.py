"""Streamlit input for body_map nodes: tappable SVG (local component) plus a plain checkbox list.
Both write the same selection list and both build the answer through bodymap.make_answer."""
from pathlib import Path
from typing import Optional

import streamlit as st
import streamlit.components.v1 as components

from intake import bodymap
from intake.models import Node
from intake.ui.strings import t

_tap = components.declare_component("intake_bodymap", path=str(Path(__file__).parent / "bodymap_component"))
SLOP = 4.0   # viewBox units: a tap that lands in a gap between regions resolves to the nearest region


def _toggle(sel_key: str, rid: str, max_sel: int, err_key: str) -> None:
    ss = st.session_state
    sel = ss[sel_key]
    if rid in sel:
        sel.remove(rid)
    elif len(sel) >= max_sel:
        ss[err_key] = True
    else:
        sel.append(rid)


def body_map_input(node: Node, lang: str, current) -> Optional[dict]:
    """Render the map + list. Returns an answer dict when the patient presses Next / a special option,
    otherwise None. A not-sure answer is returned as the string 'unsure'."""
    ss = st.session_state
    nid = node.id
    k = lambda s: f"bm_{s}_{nid}"
    cur = current if isinstance(current, dict) else {}
    if ss.get("bm_active") != nid:          # entering (or re-entering) this question: start from its stored answer
        ss["bm_active"] = nid
        ss[k("sel")] = list(cur.get("regions", []))
        ss[k("mode")] = cur.get("inputMode", "map")
        ss[k("view")] = cur.get("view", "front")
    sel: list = ss[k("sel")]
    cat = bodymap.catalog()
    views = ["front", "back"]
    view = st.radio(" ", views, horizontal=True, key=k("view"), label_visibility="collapsed",
                    format_func=lambda v: cat.viewLabels[v][lang])

    ev = _tap(svg=bodymap.render_svg(view, {"sel": sel}, lang, width=280), key=k("comp"), default=None)
    if ev and ev.get("t") != ss.get(k("last")):
        ss[k("last")] = ev["t"]
        rid = bodymap.hit_test(view, ev["x"], ev["y"], slop=SLOP)
        if rid:
            _toggle(k("sel"), rid, node.maxSelections, k("err"))
            ss[k("mode")] = "map"
            st.rerun()

    if ss.pop(k("err"), False):
        st.warning({"en": f"You can choose at most {node.maxSelections}.",
                    "hi": f"आप अधिकतम {node.maxSelections} चुन सकते हैं।",
                    "mr": f"तुम्ही जास्तीत जास्त {node.maxSelections} निवडू शकता."}[lang])
    st.caption(("✔ " + bodymap.regions_text(sel, lang)) if sel else t("bm_none_selected", lang))

    def _from_list(rid):
        ss[k("mode")] = "list"
        _toggle(k("sel"), rid, node.maxSelections, k("err"))

    with st.expander(t("bm_list", lang)):
        for r in bodymap.regions_in_view(view):
            ss[f"{k('cb')}_{r.id}"] = r.id in sel            # keep the box in step with map taps
            st.checkbox(r.label(lang), key=f"{k('cb')}_{r.id}", on_change=_from_list, args=(r.id,))

    c1, c2 = st.columns(2)
    if c1.button(t("next", lang), key=k("next"), type="primary", use_container_width=True, disabled=not sel):
        return bodymap.make_answer(sel, ss[k("mode")])
    if c2.button(t("bm_clear", lang), key=k("clear"), use_container_width=True, disabled=not sel):
        sel.clear()
        st.rerun()
    for o in node.options:                                    # I'm not sure / prefer to tell the doctor / none
        if st.button(o.get(lang), key=k(f"opt_{o.id}"), use_container_width=True):
            return "unsure" if o.id == "unsure" else bodymap.make_answer([], ss[k("mode")], o.id)
    return None
