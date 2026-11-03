"""Synthetic answers only (no real patient data). BANK gives a benign, valid answer for every node;
tests and the smoke script override a few to build a scenario."""
from typing import Any, Callable, Optional

from .bodymap import make_answer
from .conditions import SKIPPED, UNSURE
from .models import Graph
from .redflags import RedFlagRule
from .session import IntakeSession

NONE = ["none"]
BANK: dict[str, Any] = {
    "consent": "agree", "age_years": 35, "age_months": 6, "sex": "male", "pregnancy": "no", "preg_bleeding": "no",
    "weight_kg": 70, "allergies": NONE, "allergy_other": "dust", "meds_any": "no", "meds_list": "vitamin D",
    "kidney": "no", "liver": "no", "diabetes": "no", "hypertension": "no", "asthma": "no",
    "chief_complaint": "fever", "other_text": "feels tired",
    "fev_site": make_answer([], "list", "none"), "fev_onset": "d1_3", "fev_course": "constant", "fev_temp": "f100_102", "fev_assoc": ["chills"],
    "fev_relieve": "helped", "fev_severity": 3,
    "cb_main": "both", "cb_site": make_answer([], "list", "none"), "cb_onset": "days", "cb_rest": "no", "cb_sputum": "dry", "cb_assoc": NONE,
    "cb_pattern": "all_day", "cb_severity": 3, "cb_relieve": "rest",
    "ab_site": make_answer(["lower_abdomen_right"], "map"), "ab_onset": "days", "ab_character": "dull", "ab_assoc": NONE, "ab_pattern": "constant", "ab_severity": 3, "ab_relieve": "nothing",
    "hd_site": make_answer(["head_front"], "map"), "hd_onset": "days", "hd_character": "dull", "hd_worst": "no", "hd_assoc": NONE,
    "hd_course": "constant", "hd_severity": 3, "hd_trigger": "stress", "hd_relieve": "medicine",
    "cp_site": make_answer(["chest_right"], "map"), "cp_onset": "days", "cp_char": "sharp", "body_map_radiation": make_answer([], "list", "none"), "cp_assoc": NONE,
    "cp_course": "episodes", "cp_exac": "movement", "cp_relieve": "rest", "cp_severity": 3,
    "cpx_episode_len": "m5_30", "cpx_arm_numb": "no", "cpx_skin": "no", "abx_meals": "no_link", "abx_urine_stool": "no",
    "hdx_eyes_nose": "no", "hdx_neck_tight": "no",
    "danger_signs": NONE, "hx_fever": NONE, "hx_cough": NONE, "hx_abdomen": NONE, "hx_head": NONE,
    "hx_chest": NONE, "hx_similar": "no",
}


def run_bank(graph: Graph, rules: list[RedFlagRule], overrides: Optional[dict] = None, *,
             clock: Optional[Callable] = None, token: Optional[str] = None, language: str = "en",
             stop_at: Optional[str] = None, allow_unused: bool = False) -> IntakeSession:
    """Answer each pending node from overrides, else BANK. Stops before `stop_at` if given.
    Unless allow_unused, an override that was never asked raises (catches stale scenarios)."""
    overrides = overrides or {}
    kw = {"clock": clock} if clock else {}
    s = IntakeSession(graph, rules, language=language, token=token, **kw)
    asked = set()
    while s.pending and s.pending != stop_at and not s.declined:
        nid = s.pending
        s.answer(nid, overrides.get(nid, BANK[nid]))
        asked.add(nid)
    if not allow_unused and set(overrides) - asked:
        raise KeyError(f"overrides never asked: {sorted(set(overrides) - asked)}")
    return s


# Three scenarios for scripts/intake_smoke.py and tests
PATIENTS: dict[str, dict] = {
    "adult_chest_pain": {
        "age_years": 54, "weight_kg": 72, "allergies": ["penicillins"], "allergy_other": "peanuts",
        "meds_any": "yes", "meds_list": "metformin, aspirin", "diabetes": UNSURE, "hypertension": "yes",
        "chief_complaint": "chest_pain", "cp_site": make_answer(["chest_center"], "map"), "cp_onset": "sudden", "cp_char": "pressure",
        "body_map_radiation": make_answer(["upper_arm_left", "jaw_front"], "map"), "cp_assoc": ["sweating", "nausea"], "cp_course": "constant",
        "cpx_episode_len": "over_30", "cpx_arm_numb": "yes", "cp_exac": "exertion", "cp_severity": 8, "hx_chest": ["heart", "smoking"]},
    "infant_fever_weight_unknown": {
        "age_years": 0, "age_months": 2, "weight_kg": SKIPPED, "allergies": [UNSURE], "kidney": UNSURE,
        "chief_complaint": "fever", "fev_onset": "today", "fev_assoc": ["chills", "vomiting"], "fev_severity": 6},
    "woman_cough_no_flags": {
        "age_years": 30, "sex": "female", "weight_kg": 58, "allergies": ["sulfa"], "meds_any": "yes",
        "meds_list": "salbutamol inhaler, cetirizine", "asthma": "yes", "chief_complaint": "cough_breath",
        "cb_main": "both", "cb_site": make_answer([], "list", "none"), "cb_onset": "weeks", "cb_sputum": "clear", "cb_assoc": ["wheeze"],
        "cb_pattern": "night", "cb_relieve": "inhaler", "cb_severity": 5, "hx_cough": ["dust_allergy"]},
}
