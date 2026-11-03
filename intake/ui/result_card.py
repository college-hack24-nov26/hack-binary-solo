"""Result card for the Dosage check: one plain header per status, the reason in one sentence, the rule or input responsible,
sources for blocks, a fill-in checklist for needs_input and an override form for blocked. Display only: it never computes or
alters a dose. card_model() is pure so the wording is testable without Streamlit."""
import streamlit as st

from api.result_card import (BLOCK_KINDS, ELSEWHERE as _ELSEWHERE, HEADERS, MIN_REASON, STR_FIELDS,  # noqa: F401 - re-exported
                             card_model, field_kind, override_error)
from dosing.config import OVERRIDE_CATEGORIES

ss = st.session_state


def _source_line(s: dict) -> str:
    label = f"**{s['id']}** · {s['name']}" if s.get("id") else s["name"]
    return label + (f" · [{s['url']}]({s['url']})" if s.get("url") else "")


def _fill_widget(k: str, name: str, kind: str, res: dict):
    key = f"dc_need_{k}_{name}"
    if kind == "rule":
        alts = {a["rule_id"]: a for a in res["alternatives"]}
        return st.selectbox(name, [""] + list(alts), key=key, label_visibility="collapsed",
                            format_func=lambda r: "choose a rule…" if not r else f"{r} · {alts[r]['indication']} · {alts[r]['data_status']}"
                                                  + (" · suggested" if alts[r]["suggested"] else "")) or None
    if kind == "num":
        v = st.text_input(name, key=key, label_visibility="collapsed").strip()
        try:
            return float(v) if v else None
        except ValueError:
            st.error(f"{name}: enter a number")
            return None
    if kind == "tri":
        return st.selectbox(name, ["", "yes", "no", "unsure"], key=key, label_visibility="collapsed") or None
    if kind == "choice":
        opts = ["yes", "no", "possible"] if name == "pregnant" else sorted(STR_FIELDS[name])
        return st.selectbox(name, [""] + opts, key=key, label_visibility="collapsed") or None
    return st.text_input(name, key=key, label_visibility="collapsed").strip() or None


def render(res: dict, k: str, drug_id: str, indication) -> None:
    """Draws the header block. Fill-in and override submit into session state and rerun; dosing_panel re-evaluates."""
    m = card_model(res)
    box = {"ok": st.success, "needs_input": st.info, "blocked": st.error, "refused": st.error}[m["status"]]
    box(f"**{m['header']}**")
    st.write(m["reason"])
    st.caption(m["responsible"])
    if m["sources"]:
        st.markdown("**Source:** " + " · ".join(_source_line(s) for s in m["sources"]))
    for o in m["overrides"]:
        st.markdown(f":red[**Override recorded**] · {o['category_label']} · \"{o['reason']}\" · {o['doctor_id']}")

    if m["status"] == "needs_input":
        st.markdown("**Fill in the missing items**")
        with st.form(f"dc_fill_{k}"):
            got: dict = {}
            for n in m["missing"]:
                kind, key = field_kind(n["field"])
                st.markdown(f"☐ **{n['field']}** · {n['why']}")
                if kind == "elsewhere":
                    st.caption(_ELSEWHERE.get(key, "Enter this in the 'Doctor-entered inputs' section above."))
                    continue
                v = _fill_widget(k, n["field"], kind, res)
                if v is not None:
                    got[key] = v
            if st.form_submit_button("Update and recompute", type="primary"):
                if got:
                    if "selected_rule_id" in got:
                        ss[f"dc_sel_{k}"] = got.pop("selected_rule_id")
                    ss[f"dc_extra_{k}"] = {**ss.get(f"dc_extra_{k}", {}), **got}
                    ss[f"dc_recalc_{k}"] = True
                    st.rerun()
                st.info("Nothing filled in yet.")

    if m["status"] == "blocked":
        st.markdown("**Override (doctor only, logged)**")
        with st.form(f"dc_ovform_{k}"):
            cat = st.selectbox("Reason category", [""] + list(OVERRIDE_CATEGORIES), key=f"dc_ovc_{k}",
                               format_func=lambda c: OVERRIDE_CATEGORIES.get(c, "choose…"))
            why = st.text_area(f"Written reason (at least {MIN_REASON} characters)", key=f"dc_ov_{k}", height=70)
            if st.form_submit_button("Record override and show dose", key=f"dc_ovgo_{k}"):
                err = override_error(cat, why)
                if err:
                    st.error(err)
                else:
                    ss[f"dc_ovr_{k}"] = {"drug": drug_id, "ind": indication, "category": cat, "reason": why.strip()}
                    ss[f"dc_recalc_{k}"] = True
                    st.rerun()
