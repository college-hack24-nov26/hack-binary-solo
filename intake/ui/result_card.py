"""Result card for the Dosage check: one plain header per status, the reason in one sentence, the rule or input responsible,
sources for blocks, a fill-in checklist for needs_input and an override form for blocked. Display only: it never computes or
alters a dose. card_model() is pure so the wording is testable without Streamlit."""
import streamlit as st

from dosing.config import OVERRIDE_CATEGORIES
from dosing.engine import CALC_INPUTS, NUM_FIELDS, STR_FIELDS, is_tri_field

ss = st.session_state
HEADERS = {"ok": "Dose ready for doctor review", "needs_input": "More information needed",
           "blocked": "Blocked: safety rule", "refused": "Refused: no data for this case"}
MIN_REASON = 10
BLOCK_KINDS = {"block_ci": "contraindication", "block_allergy_other": "free-text allergy", "block_renal": "kidney function band",
               "block_interaction": "drug interaction", "block_pregnancy": "pregnancy", "block_age": "age outside the rule",
               "block_weight": "weight outside the rule", "block_offlabel_child": "off-label use in a child"}

# needs_input field name -> (input kind, doctor_inputs key). kinds: num, tri, choice, text, form, elsewhere
_ALIASES = {"age": ("num", "age_months"), "age_exact": ("num", "age_exact_days"), "form": ("form", "form")}
_ELSEWHERE = {"indication": "Choose an indication in the form above."}


def field_kind(name: str) -> tuple[str, str]:
    if name in _ALIASES:
        return _ALIASES[name]
    if name in _ELSEWHERE:
        return "elsewhere", name
    if name == "selected_rule_id":
        return "rule", name
    if name == "meds_text":
        return "text", name
    if name == "pregnant":
        return "choice", name
    if name in STR_FIELDS:
        return "choice", name
    if is_tri_field(name):
        return "tri", name
    if name in NUM_FIELDS or name in CALC_INPUTS:
        return "num", name
    return "elsewhere", name


def _first_sentence(text: str) -> str:
    t = " ".join((text or "").split())
    for i, ch in enumerate(t):
        if ch in ".!?" and (i + 1 == len(t) or t[i + 1] == " ") and i > 20:
            return t[:i + 1]
    return t


def card_model(res: dict) -> dict:
    status = res["status"]
    m = {"status": status, "header": HEADERS[status], "reason": "", "responsible": "", "sources": [], "missing": [],
         "show_numbers": status not in ("blocked", "refused"), "overrides": []}
    seen_ov = set()
    for o in res.get("overrides") or []:                    # one line per category + reason (one reason can cover several blocks)
        key = (o["category"], o["reason"], o["doctor_id"])
        if key not in seen_ov:
            seen_ov.add(key)
            m["overrides"].append(o)
    if status == "ok":
        m["reason"] = "Every required input is present and no safety rule stopped this dose."
        m["responsible"] = "Rule " + str(res.get("selected_rule_id") or "-")
    elif status == "needs_input":
        grouped: dict = {}
        for x in res["needs_input"]:                       # one checklist line per field, reasons joined
            grouped[x["field"]] = (grouped[x["field"]] + " " + x["why"]) if x["field"] in grouped else x["why"]
        n = len(grouped)
        m["reason"] = f"{n} item{'s' if n != 1 else ''} must be filled in before a dose can be shown."
        m["responsible"] = "Missing: " + ", ".join(grouped)
        m["missing"] = [{"field": f, "why": w} for f, w in grouped.items()]
    elif status == "blocked":
        b = res["blocks"][0]
        m["reason"] = _first_sentence(b["text"])
        kind = BLOCK_KINDS.get(b["code"], b["code"].replace("block_", "").replace("_", " "))
        m["responsible"] = f"Rule type: {kind}" + (f" · {len(res['blocks'])} safety rules fired, all listed below" if len(res["blocks"]) > 1 else "")
        seen = set()
        for blk in res["blocks"]:
            for s in blk.get("sources", []):
                key = (s.get("id"), s.get("name"))
                if key not in seen:
                    seen.add(key)
                    m["sources"].append({"id": s.get("id"), "name": s.get("name"), "url": s.get("url")})
    else:
        m["reason"] = _first_sentence(res["refused_reasons"][0]) if res["refused_reasons"] else "The engine has no usable rule for this case."
        m["responsible"] = "No usable formulary rule for: " + f"{res.get('drug')} / {res.get('indication') or '-'}"
    return m


def override_error(category, reason) -> str | None:
    if category not in OVERRIDE_CATEGORIES:
        return "Choose a reason category."
    if len((reason or "").strip()) < MIN_REASON:
        return f"Write a reason of at least {MIN_REASON} characters."
    return None


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
