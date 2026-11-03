"""Turn raw answers into a PatientRecord (pure; no I/O)."""
import re
from datetime import datetime
from typing import Optional

from intake.conditions import SKIPPED, UNSURE, is_unsure
from intake.engine import answer_label, recompute_path
from intake.models import Graph
from intake.redflags import RedFlagRule, evaluate_rules

from .schema import (AnswerLine, Complaint, Consent, DosingInputs, PatientRecord, RadiationAnswer, SiteAnswer,
                     TimelineEntry)

# dosing field -> graph nodes that must be answered with a real value
_BASIC_NODES = {
    "weightKg": ["weight_kg"], "sex": ["sex"], "pregnancy": ["pregnancy"], "allergies": ["allergies"],
    "renal": ["kidney"], "hepatic": ["liver"], "diabetes": ["diabetes"],
    "hypertension": ["hypertension"], "asthma": ["asthma"],
}
_ALLERGY_LABELS = {"penicillins", "sulfa", "nsaids"}


def _state(path: list[str], answers: dict, node: str) -> str:
    """na (not on path) | pending (not answered yet) | missing (skipped / not sure) | ok"""
    if node not in path:
        return "na"
    if node not in answers:
        return "pending"
    v = answers[node]
    return "missing" if v == SKIPPED or is_unsure(v) else "ok"


def build_dosing_inputs(path: list[str], answers: dict) -> DosingInputs:
    missing: list[str] = []

    def real(node):
        return answers[node] if _state(path, answers, node) == "ok" else None

    def flag(field, *states):
        if "missing" in states:
            missing.append(field)

    age_y, age_m = real("age_years"), real("age_months")
    age = None
    if age_y is not None:
        age = float(age_y) + ((age_m or 0) / 12 if age_y == 0 else 0)
    flag("ageYears", _state(path, answers, "age_years"),
         *(_state(path, answers, "age_months"),) if age_y == 0 else ())

    sex = real("sex")
    pregnancy = real("pregnancy")
    if "pregnancy" not in path and "sex" in answers and "age_years" in answers:
        pregnancy = "not_applicable"

    allergies: list[str] = []
    al = real("allergies")
    if isinstance(al, list):
        allergies = [a for a in al if a in _ALLERGY_LABELS]
    other = real("allergy_other")
    if other:
        allergies.append(f"other: {other.strip()}")

    meds: list[str] = []
    meds_state = _state(path, answers, "meds_any")
    if real("meds_any") == "yes":
        meds_state = _state(path, answers, "meds_list")
        txt = real("meds_list")
        meds = [m.strip() for m in re.split(r"[,;\n]+", txt) if m.strip()] if txt else []

    out = DosingInputs(
        ageYears=age, weightKg=real("weight_kg"), sex=sex, pregnancy=pregnancy, allergies=allergies,
        renal=real("kidney"), hepatic=real("liver"), diabetes=real("diabetes"),
        hypertension=real("hypertension"), asthma=real("asthma"), currentMeds=meds)
    for field, nodes in _BASIC_NODES.items():
        flag(field, *(_state(path, answers, n) for n in nodes))
    flag("currentMeds", meds_state)
    order = ["ageYears", "weightKg", "sex", "pregnancy", "allergies", "currentMeds",
             "renal", "hepatic", "diabetes", "hypertension", "asthma"]
    out.missing = [f for f in order if f in missing]
    return out


def _body_map_answer(node, nid: str, v):
    special = None
    if v == SKIPPED:
        special, v = "skipped", {}
    elif is_unsure(v):
        special, v = "unsure", {}
    else:
        special = v.get("special")
    if node.socrates == "site":
        return SiteAnswer(nodeId=nid, regions=v.get("regions", []), view=v.get("view"),
                          inputMode=v.get("inputMode"), special=special)
    return RadiationAnswer(nodeId=nid, regions=v.get("regions", []), special=special)


def build_record(graph: Graph, rules: list[RedFlagRule], answers: dict, *, token: str, language: str,
                 consent_at: Optional[datetime], created_at: datetime, now: datetime, complete: bool,
                 timeline: Optional[list[TimelineEntry]] = None, prior: Optional[PatientRecord] = None,
                 assigned_doctor: Optional[str] = None) -> PatientRecord:
    res = recompute_path(graph, answers)
    ans, path = res.answers, res.path

    complaint = Complaint()
    if (cid := ans.get("chief_complaint")) is not None:
        node = graph.node("chief_complaint")
        other = ans.get("other_text")
        complaint = Complaint(id=cid if node.option(cid) else None, label=answer_label(node, cid),
                              text=other if isinstance(other, str) and other not in (SKIPPED, UNSURE) else None)

    socrates: dict = {}
    history: list[AnswerLine] = []
    for nid in path:
        if nid not in ans:
            continue
        node = graph.node(nid)
        if node.type == "body_map":
            socrates[node.socrates] = _body_map_answer(node, nid, ans[nid])
            continue
        line = AnswerLine(nodeId=nid, label=node.shortLabel or node.text.en, question=node.text.en, answer=answer_label(node, ans[nid]), raw=ans[nid])
        if node.section == "history":
            history.append(line)
        elif node.section == "module" and node.socrates:
            socrates.setdefault(node.socrates, []).append(line)

    captured = sum(1 for n in path if n != "consent" and n in ans and ans[n] != SKIPPED and not is_unsure(ans[n]))
    started = consent_at
    rec = PatientRecord(
        token=token, status="complete" if complete else "in_progress",
        createdAt=created_at.isoformat(timespec="seconds"), updatedAt=now.isoformat(timespec="seconds"),
        language=language,
        consent=Consent(given=ans.get("consent") == "agree",
                        timestamp=consent_at.isoformat(timespec="seconds") if consent_at else None,
                        graphVersion=graph.version),
        dosingInputs=build_dosing_inputs(path, ans), complaint=complaint, socrates=socrates, history=history,
        answers=ans, redFlags=evaluate_rules(rules, ans), timeline=timeline or [],
        intakeDurationSeconds=int((now - started).total_seconds()) if complete and started else None,
        fieldsCaptured=captured, assignedDoctor=assigned_doctor or (prior.assignedDoctor if prior else None))
    if prior is not None:  # doctor edits survive a rebuild
        rec.doctorEdits, rec.editedByDoctor, rec.editedFields = prior.doctorEdits, prior.editedByDoctor, prior.editedFields
    return rec
