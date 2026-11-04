"""Pure wording for the Dosage check result card: one plain header per status, the reason in one sentence, the rule or input
responsible, sources for blocks and a fill-in checklist for needs_input. Display only: it never computes or alters a dose.
Moved here from the retired Streamlit result card; tests in tests/test_demo_features.py."""
from dosing.config import OVERRIDE_CATEGORIES
from dosing.engine import CALC_INPUTS, NUM_FIELDS, STR_FIELDS, is_tri_field

HEADERS = {"ok": "Dose ready for doctor review", "needs_input": "More information needed",
           "blocked": "Blocked: safety rule", "refused": "Refused: no data for this case"}
MIN_REASON = 10
BLOCK_KINDS = {"block_ci": "contraindication", "block_allergy_other": "free-text allergy", "block_renal": "kidney function band",
               "block_interaction": "drug interaction", "block_pregnancy": "pregnancy", "block_age": "age outside the rule",
               "block_weight": "weight outside the rule", "block_offlabel_child": "off-label use in a child"}

# needs_input field name -> (input kind, doctor_inputs key). kinds: num, tri, choice, text, form, rule, elsewhere
_ALIASES = {"age": ("num", "age_months"), "age_exact": ("num", "age_exact_days"), "form": ("form", "form")}
ELSEWHERE = {"indication": "Choose an indication in the form above."}


def field_kind(name: str) -> tuple[str, str]:
    if name in _ALIASES:
        return _ALIASES[name]
    if name in ELSEWHERE:
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


def choice_options(name: str) -> list[str]:
    """Allowed values for a 'choice' checklist field (same lists the Streamlit card offered)."""
    return ["yes", "no", "possible"] if name == "pregnant" else sorted(STR_FIELDS.get(name, ()))


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
