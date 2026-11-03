import os
from datetime import datetime, timedelta, timezone

import pytest

from intake.conditions import SKIPPED, UNSURE
from intake.models import load_graph
from intake.redflags import load_rules
from intake.summary import apply_doctor_edits, build_summary, render_text, template_paragraph
from intake.synthetic import PATIENTS, run_bank
from ocr.timeline import to_timeline_entry
from records import store
from records.schema import PatientRecord, TimelineEntry

G, RULES = load_graph(), load_rules()
T0 = datetime(2026, 11, 3, 10, 0, 0, tzinfo=timezone.utc)


def clock():
    t = [T0]

    def now():
        t[0] += timedelta(seconds=30)
        return t[0]
    return now


def rec(ov=None, token="PT-AAAAAA"):
    return run_bank(G, RULES, ov, clock=clock(), token=token).finish()


def test_clean_record_has_nothing_missing():
    r = rec({"sex": "female", "age_years": 30})
    assert r.dosingInputs.missing == []
    d = r.dosingInputs
    assert (d.ageYears, d.weightKg, d.sex, d.pregnancy, d.renal) == (30, 70, "female", "no", "no")
    assert d.allergies == ["other: dust"] or d.allergies == []   # "none" + free text skipped by flow
    assert r.status == "complete" and r.consent.given and r.consent.timestamp


@pytest.mark.parametrize("node,field,extra", [
    ("age_years", "ageYears", {}), ("weight_kg", "weightKg", {}), ("sex", "sex", {}),
    ("allergies", "allergies", {}), ("kidney", "renal", {}), ("liver", "hepatic", {}),
    ("diabetes", "diabetes", {}), ("hypertension", "hypertension", {}), ("asthma", "asthma", {}),
    ("meds_any", "currentMeds", {}),
    ("pregnancy", "pregnancy", {"sex": "female"}),
])
@pytest.mark.parametrize("kind", [UNSURE, SKIPPED])
def test_missing_basics_flagged(node, field, extra, kind):
    val = [kind] if node == "allergies" and kind == UNSURE else kind
    r = rec({**extra, node: val})
    assert field in r.dosingInputs.missing


def test_meds_yes_but_list_skipped_is_missing():
    assert "currentMeds" in rec({"meds_any": "yes", "meds_list": SKIPPED}).dosingInputs.missing
    assert "currentMeds" not in rec({"meds_any": "no"}).dosingInputs.missing


def test_not_applicable_pregnancy_is_not_missing():
    r = rec()
    assert r.dosingInputs.pregnancy == "not_applicable" and "pregnancy" not in r.dosingInputs.missing


def test_infant_age_and_allergy_classes():
    r = rec({"age_years": 0, "age_months": 3, "allergies": ["penicillins", "nsaids"], "allergy_other": "egg"})
    assert r.dosingInputs.ageYears == 0.25
    assert r.dosingInputs.allergies == ["penicillins", "nsaids", "other: egg"]
    assert "ageYears" in rec({"age_years": 0, "age_months": UNSURE}).dosingInputs.missing


def test_meds_split():
    assert rec({"meds_any": "yes", "meds_list": "a; b,\nc"}).dosingInputs.currentMeds == ["a", "b", "c"]


def test_fields_captured_excludes_unsure_skipped_and_consent():
    a = rec()
    b = rec({"weight_kg": UNSURE, "kidney": SKIPPED})
    assert b.fieldsCaptured == a.fieldsCaptured - 2
    assert a.fieldsCaptured == len(a.answers) - 1


def test_duration_is_measured_from_consent_to_finish():
    s = run_bank(G, RULES, clock=clock())
    r = s.finish()
    assert r.intakeDurationSeconds == 30            # one tick between consent and finish


def test_in_progress_record_has_no_duration_and_no_pending_missing():
    s = run_bank(G, RULES, stop_at="kidney")
    r = s.to_record()
    assert r.status == "in_progress" and r.intakeDurationSeconds is None
    assert "renal" not in r.dosingInputs.missing        # not yet asked is not "missing"


def test_record_has_no_name_fields_and_token_format():
    r = rec()
    assert store.TOKEN_RE.match(r.token)
    assert not any("name" in k.lower() for k in PatientRecord.model_fields)


def test_store_roundtrip_list_and_bad_token(tmp_path):
    r = rec()
    store.save(r, tmp_path)
    assert store.load(r.token, tmp_path) == r
    (tmp_path / "PT-ZZZZZZ.json").write_text("{broken")
    assert [x.token for x in store.list_records(tmp_path)] == [r.token]
    store.delete(r.token, tmp_path)
    assert store.load(r.token, tmp_path) is None
    for bad in ("../x", "PT-1", "pt-aaaaaa"):
        with pytest.raises(ValueError):
            store.load(bad, tmp_path)


def test_default_data_dir_is_gitignored():
    from intake.models import ROOT
    assert "data_local/" in (ROOT / ".gitignore").read_text()


def test_timeline_uses_ocr_entry_shape():
    entry = to_timeline_entry({"documentType": "prescription", "documentDate": "2025-01-02",
                               "medications": [{"nameAsWritten": "Tab. X"}], "labResults": [],
                               "diagnosesAsWritten": []}, ["medications[0].strength"])
    te = TimelineEntry.model_validate(entry)
    assert te.editedByDoctor and te.editedFields == ["medications[0].strength"] and te.source == "ocr"
    s = run_bank(G, RULES, clock=clock())
    s.timeline = [te]
    text = render_text(build_summary(s.finish()))
    assert "2025-01-02 prescription: 1 items: Tab. X" in text and "edited by doctor" in text


# ------------------------------------------------------------ summary
SNAP = os.path.join(os.path.dirname(__file__), "snapshots", "summary_adult_chest_pain.txt")


def test_summary_snapshot():
    r = run_bank(G, RULES, PATIENTS["adult_chest_pain"], clock=clock(), token="PT-SNAPAA").finish()
    text = render_text(build_summary(r))
    if os.environ.get("UPDATE_SNAPSHOTS") or not os.path.exists(SNAP):
        open(SNAP, "w", encoding="utf-8").write(text)
    assert text == open(SNAP, encoding="utf-8").read()
    # order: red flags, dosing, complaint, history, allergies, medicines, timeline, measured
    heads = ["RED FLAGS", "DOSING INPUTS", "COMPLAINT AND SOCRATES", "HISTORY", "ALLERGIES", "CURRENT MEDICINES",
             "OLD RECORDS", "MEASURED"]
    assert [text.index(h) for h in heads] == sorted(text.index(h) for h in heads)


def test_summary_is_deterministic_and_highlights_missing():
    r = rec({"weight_kg": UNSURE})
    assert render_text(build_summary(r)) == render_text(build_summary(r))
    f = {x.key: x for s in build_summary(r).sections for x in s.fields}
    assert f["dosing.weightKg"].missing and "MISSING (patient not sure)" in f["dosing.weightKg"].value
    assert "!! Weight (kg)" in render_text(build_summary(r))
    r2 = rec({"weight_kg": SKIPPED})
    assert "MISSING (skipped)" in render_text(build_summary(r2))


def test_summary_shows_only_measured_numbers():
    text = render_text(build_summary(rec()))
    assert "Intake duration: 0 min 30 s" in text and "Fields captured:" in text
    assert "saved" not in text.lower()


def test_doctor_edit_tracking_and_revert():
    r = rec({"weight_kg": UNSURE})
    later = T0 + timedelta(hours=1)
    r2 = apply_doctor_edits(r, {"dosing.weightKg": "64", "allergies.list": "None reported"}, later)
    assert r2.editedByDoctor and r2.editedFields == ["dosing.weightKg"]    # unchanged text not an edit
    assert r2.answers == r.answers and r2.dosingInputs == r.dosingInputs   # raw data untouched
    f = {x.key: x for s in build_summary(r2).sections for x in s.fields}
    w = f["dosing.weightKg"]
    assert w.value == "64" and w.edited and not w.missing and "MISSING" in w.original
    assert "[edited by doctor]" in render_text(build_summary(r2))
    r3 = apply_doctor_edits(r2, {"dosing.weightKg": w.original}, later)
    assert not r3.editedByDoctor and r3.editedFields == []


def test_red_flags_and_timeline_are_not_editable():
    r = run_bank(G, RULES, PATIENTS["adult_chest_pain"], clock=clock()).finish()
    for key in ("redFlag.RF_CHEST_PAIN_RADIATION_SWEATING", "timeline.none", "nope"):
        with pytest.raises(KeyError):
            apply_doctor_edits(r, {key: "x"}, T0)


def test_edits_survive_rebuild_from_session():
    s = run_bank(G, RULES, clock=clock())
    r = apply_doctor_edits(s.finish(), {"dosing.weightKg": "99"}, T0)
    rebuilt = s.to_record(complete=True, prior=r)
    assert rebuilt.editedFields == ["dosing.weightKg"]


def test_template_paragraph_deterministic():
    r = run_bank(G, RULES, PATIENTS["infant_fever_weight_unknown"], clock=clock()).finish()
    p = template_paragraph(build_summary(r))
    assert p == template_paragraph(build_summary(r))
    assert "Red flags triggered: 1" in p and "Missing:" in p and "Weight (kg)" in p
