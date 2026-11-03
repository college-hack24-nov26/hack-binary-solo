"""Deterministic doctor summary. Same record in, same text out. Doctor edits are tracked per field
(editedByDoctor / editedFields, like the OCR module) and never overwrite the raw answers."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from records.schema import DoctorEdit, PatientRecord, RadiationAnswer, SiteAnswer

from . import bodymap
from .conditions import SKIPPED, is_unsure
from .engine import answer_label
from .models import ROOT, load_graph

MISSING = "MISSING"
_SOCRATES_ORDER = [("site", "Site"), ("onset", "Onset"), ("character", "Character"), ("radiation", "Radiation"),
                   ("associated", "Associated symptoms"), ("time_course", "Time course"),
                   ("exacerbating_relieving", "Exacerbating / relieving"), ("severity", "Severity")]
_DOSING = [("ageYears", "Age (years)", ["age_years", "age_months"]), ("weightKg", "Weight (kg)", ["weight_kg"]),
           ("sex", "Sex", ["sex"]), ("pregnancy", "Pregnancy", ["pregnancy"]), ("renal", "Kidney disease", ["kidney"]),
           ("hepatic", "Liver disease", ["liver"]), ("diabetes", "Diabetes", ["diabetes"]),
           ("hypertension", "Hypertension", ["hypertension"]), ("asthma", "Asthma", ["asthma"])]
_YNU = {"yes": "Yes", "no": "No", "unsure": "Not sure"}


class Field(BaseModel):
    key: str
    label: str
    value: str
    missing: bool = False
    editable: bool = True
    edited: bool = False
    original: Optional[str] = None


class Section(BaseModel):
    title: str
    fields: list[Field]


class Summary(BaseModel):
    token: str
    sections: list[Section]
    intakeDurationSeconds: Optional[int]
    fieldsCaptured: int
    editedByDoctor: bool
    editedFields: list[str]


def _why(rec: PatientRecord, nodes: list[str]) -> str:
    for n in nodes:
        if n in rec.answers:
            v = rec.answers[n]
            if v == SKIPPED:
                return "skipped"
            if is_unsure(v):
                return "patient not sure"
    return "not captured"


def _fmt_age(x: float) -> str:
    if x < 1:
        return f"{round(x * 12)} months"
    return f"{x:g}"


_SPECIAL_TEXT = {"tell_doctor": "Prefers to tell the doctor", "none": "None / does not spread",
                 "unsure": "Not sure", "skipped": "Skipped"}


def _body_text(a, lang: str) -> str:
    if a.special:
        if a.special == "none":
            return _NONE_TEXT["site" if isinstance(a, SiteAnswer) else "radiation"][lang]
        return _SPECIAL_BY_LANG[lang][a.special]
    return bodymap.regions_text(a.regions, lang)


_NONE_TEXT = {"site": {"en": "No particular place", "hi": "कोई खास जगह नहीं", "mr": "विशिष्ट जागा नाही"},
              "radiation": {"en": "Does not spread", "hi": "कहीं नहीं फैलता", "mr": "कुठेही पसरत नाही"}}
_SPECIAL_BY_LANG = {
    "en": _SPECIAL_TEXT,
    "hi": {"tell_doctor": "डॉक्टर को खुद बताना चाहते हैं", "none": "कोई नहीं / नहीं फैलता", "unsure": "पक्का नहीं", "skipped": "छोड़ा गया"},
    "mr": {"tell_doctor": "डॉक्टरांना स्वतः सांगणार", "none": "काही नाही / पसरत नाही", "unsure": "खात्री नाही", "skipped": "वगळले"},
}


def _base_fields(rec: PatientRecord, lang: str = "en") -> list[tuple[str, Field]]:
    """(section title, field) from machine data only, ignoring doctor edits."""
    out: list[tuple[str, Field]] = []
    d = rec.dosingInputs

    # 1. red flags (read-only; the rules are the audit trail)
    sec = "Red flags"
    if rec.redFlags:
        for t in rec.redFlags:
            g = load_graph()
            ans = "; ".join(f"{g.node(n).shortLabel or g.node(n).text.en}: {answer_label(g.node(n), v, lang)}"
                            for n, v in t.triggeredBy.items())
            out.append((sec, Field(key=f"redFlag.{t.ruleId}", label=t.severity.upper(), editable=False,
                                   value=f"{t.staffMessage} [rule {t.ruleId}; {t.label}] Triggered by: {ans}")))
    else:
        out.append((sec, Field(key="redFlag.none", label="None", editable=False,
                               value="No draft red-flag rule was triggered by the answers given.")))

    # 2. dosing inputs
    sec = "Dosing inputs"
    for field, label, nodes in _DOSING:
        val = getattr(d, field)
        miss = field in d.missing
        if miss or val is None:
            text, miss = f"{MISSING} ({_why(rec, nodes)})", True
        elif field == "ageYears":
            text = _fmt_age(val)
        elif field == "pregnancy":
            text = {"not_applicable": "Not applicable"}.get(val, _YNU.get(val, str(val)))
        else:
            text = _YNU.get(val, str(val).capitalize()) if isinstance(val, str) else f"{val:g}"
        out.append((sec, Field(key=f"dosing.{field}", label=label, value=text, missing=miss)))

    # 3. complaint + SOCRATES
    sec = "Complaint and SOCRATES"
    main = rec.complaint.label or "Not captured"
    if rec.complaint.text:
        main += f": {rec.complaint.text}"
    out.append((sec, Field(key="complaint.main", label="Main complaint", value=main, missing=rec.complaint.label is None)))
    for key, label in _SOCRATES_ORDER:
        lines = rec.socrates.get(key)
        if isinstance(lines, (SiteAnswer, RadiationAnswer)):
            via = f" (via {lines.inputMode})" if getattr(lines, "inputMode", None) else ""
            out.append((sec, Field(key=f"socrates.{key}", label=label, value=_body_text(lines, lang) + via)))
        elif lines:
            out.append((sec, Field(key=f"socrates.{key}", label=label,
                                   value="; ".join(f"{l.label}: {l.answer}" if len(lines) > 1 else l.answer for l in lines))))

    # 4. history
    for l in rec.history:
        out.append(("History", Field(key=f"history.{l.nodeId}", label=l.label or l.question, value=l.answer)))

    # 5. allergies, 6. medicines
    al_missing = "allergies" in d.missing
    out.append(("Allergies", Field(
        key="allergies.list", label="Drug allergies", missing=al_missing,
        value=f"{MISSING} ({_why(rec, ['allergies'])})" if al_missing else
        (", ".join(d.allergies) if d.allergies else "None reported"))))
    me_missing = "currentMeds" in d.missing
    out.append(("Current medicines", Field(
        key="meds.list", label="Current medicines", missing=me_missing,
        value=f"{MISSING} ({_why(rec, ['meds_any', 'meds_list'])})" if me_missing else
        ("; ".join(d.currentMeds) if d.currentMeds else "None reported"))))

    # 7. OCR timeline (edited in the OCR module; shown read-only here)
    sec = "Old records (OCR timeline)"
    if not rec.timeline:
        out.append((sec, Field(key="timeline.none", label="Entries", editable=False, value="No scanned records attached.")))
    for i, e in enumerate(sorted(rec.timeline, key=lambda e: e.date)):
        names = [it.get("nameAsWritten") or it.get("test") or "?" for it in e.items]
        flag = f" (edited by doctor: {', '.join(e.editedFields)})" if e.editedByDoctor else ""
        out.append((sec, Field(key=f"timeline.{i}", label=f"{e.date} {e.type}", editable=False,
                               value=f"{len(e.items)} items: {', '.join(names)}{flag}")))
    return out


def build_summary(rec: PatientRecord, lang: str = "en") -> Summary:
    sections: dict[str, list[Field]] = {}
    for title, f in _base_fields(rec, lang):
        if (ed := rec.doctorEdits.get(f.key)) is not None:
            f = f.model_copy(update={"value": ed.edited, "missing": False, "edited": True, "original": ed.original})
        sections.setdefault(title, []).append(f)
    return Summary(token=rec.token, sections=[Section(title=t, fields=fs) for t, fs in sections.items()],
                   intakeDurationSeconds=rec.intakeDurationSeconds, fieldsCaptured=rec.fieldsCaptured,
                   editedByDoctor=rec.editedByDoctor, editedFields=rec.editedFields)


def apply_doctor_edits(rec: PatientRecord, values: dict[str, str], now: datetime, lang: str = "en") -> PatientRecord:
    """Record edits for the keys in `values` whose text differs from the machine-generated text."""
    base = {f.key: f for _, f in _base_fields(rec, lang)}
    edits = dict(rec.doctorEdits)
    for key, new in values.items():
        f = base.get(key)
        if f is None or not f.editable:
            raise KeyError(f"{key} is not an editable field")
        new = new.strip()
        if new == f.value:
            edits.pop(key, None)
        else:
            edits[key] = DoctorEdit(original=f.value, edited=new, editedAt=now.isoformat(timespec="seconds"))
    return rec.model_copy(update={"doctorEdits": edits, "editedByDoctor": bool(edits), "editedFields": sorted(edits)})


def duration_text(sec: Optional[int]) -> str:
    return "not completed" if sec is None else f"{sec // 60} min {sec % 60} s"


def render_text(s: Summary) -> str:
    lines = [f"INTAKE SUMMARY  {s.token}", "AI drafts, the doctor decides. Draft red-flag rules are unverified.", ""]
    for sec in s.sections:
        lines.append(sec.title.upper())
        for f in sec.fields:
            mark = "!! " if f.missing else ""
            tag = "  [edited by doctor]" if f.edited else ""
            lines.append(f"  {mark}{f.label}: {f.value}{tag}")
        lines.append("")
    lines += ["MEASURED", f"  Intake duration: {duration_text(s.intakeDurationSeconds)}",
              f"  Fields captured: {s.fieldsCaptured}"]
    if s.editedByDoctor:
        lines.append(f"  Edited by doctor: {', '.join(s.editedFields)}")
    return "\n".join(lines) + "\n"


def template_paragraph(s: Summary) -> str:
    """Deterministic fallback paragraph built from the same fields."""
    f = {x.key: x for sec in s.sections for x in sec.fields}

    def val(k):
        return f[k].value if k in f and not f[k].missing else ""

    age = val("dosing.ageYears")
    who = " ".join(x for x in (f"{age} years" if age and "month" not in age else age, val("dosing.sex").lower()) if x)
    parts = [f"{who.capitalize() or 'Patient'}, presenting with {f['complaint.main'].value}."]
    for key, label in _SOCRATES_ORDER:
        if f"socrates.{key}" in f:
            parts.append(f"{label}: {f[f'socrates.{key}'].value}.")
    n_flags = sum(1 for k in f if k.startswith("redFlag.") and k != "redFlag.none")
    parts.append(f"Red flags triggered: {n_flags} (see list)." if n_flags else "No red-flag rule triggered.")
    parts.append(f"Allergies: {f['allergies.list'].value}. Medicines: {f['meds.list'].value}.")
    miss = [x.label for sec in s.sections for x in sec.fields if x.missing]
    if miss:
        parts.append("Missing: " + ", ".join(miss) + ".")
    return " ".join(parts)


def body_diagram_svgs(rec: PatientRecord, lang: str = "en", width: int = 160) -> list[str]:
    """Small highlighted diagrams (site red, radiation orange) for the views that have a selection.
    Empty when no regions were chosen."""
    site, rad = rec.socrates.get("site"), rec.socrates.get("radiation")
    groups = {"site": list(getattr(site, "regions", []) or []), "radiation": list(getattr(rad, "regions", []) or [])}
    views = [v for v in ("front", "back") if any(bodymap.region(r).view == v for ids in groups.values() for r in ids)]
    return [bodymap.render_svg(v, {k: [r for r in ids if bodymap.region(r).view == v] for k, ids in groups.items()}, lang, width)
            for v in views]
