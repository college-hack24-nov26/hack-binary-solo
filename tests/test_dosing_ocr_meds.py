"""Medicines from doctor-confirmed scans feed the interaction check; unconfirmed scans never do."""
import pytest

from dosing import service
from dosing.config import Config
from dosing.mapper import map_record
from records.schema import PatientRecord, TimelineEntry

from dosing_helpers import quiz

CFG = Config(allow_unverified=False)


@pytest.fixture(autouse=True)
def datadir(tmp_path, monkeypatch):
    monkeypatch.setenv("INTAKE_DATA_DIR", str(tmp_path))


def scan(names, date="2025-11-02", confirmed=True, type_="prescription"):
    e = {"date": date, "type": type_, "items": [{"nameAsWritten": n, "needsReview": False} for n in names], "diagnoses": [],
         "source": "ocr", "editedByDoctor": False, "editedFields": []}
    if confirmed:
        e["confirmedBy"] = "dr_demo"
    return TimelineEntry.model_validate(e)


def rec(timeline=(), **kw):
    return PatientRecord(token="PT-ABCDEF", createdAt="2026-01-01T00:00:00", updatedAt="2026-01-01T00:00:00",
                         answers=quiz(**kw), timeline=list(timeline))


def metro(r):
    return service.evaluate_for_record(r, "metronidazole", "amoebiasis (India)", doctor_id="D1", cfg=CFG, log=False)


def test_confirmed_scan_with_warfarin_triggers_metronidazole_interaction_with_tag():
    res = metro(rec([scan(["Tab Warfarin 5 mg"])], hx_abdomen=["none"]))
    hits = [i for i in res["interactions"] if "Monitor PT/INR" in i["action"]]
    assert hits and hits[0]["severity"] == "major"
    assert "from scanned prescription (2025-11-02)" in hits[0]["with"]
    o = hits[0]["origins"]
    assert o[0]["source"] == "ocr_doctor_confirmed" and o[0]["scan_ref"] == "timeline[0]"


def test_unconfirmed_scan_does_not_trigger_it():
    res = metro(rec([scan(["warfarin"], confirmed=False)], hx_abdomen=["none"]))
    assert not [i for i in res["interactions"] if "Monitor PT/INR" in i["action"]]
    ctx = map_record(rec([scan(["warfarin"], confirmed=False)]))
    assert ctx.ocr_meds == [] and ctx.ocr_unparsed == []


def test_unrecognised_token_is_surfaced_not_dropped():
    res = metro(rec([scan(["warfarin", "Zorbitex"])], hx_abdomen=["none"]))
    w = [x["text"] for x in res["warnings"] if x["code"] == "warn_unparsed_ocr_med"]
    assert w == ["unparsed from prescription: doctor to review: 'Zorbitex' (scan dated 2025-11-02)"]


def test_merge_with_self_reported_is_deduplicated_and_shows_both_sources():
    r = rec([scan(["Warfarin"])], meds_any="yes", meds_list="Coumadin", hx_abdomen=["none"])
    ctx = map_record(r)
    merged = [m for m in ctx.all_meds() if m.generic == "warfarin"]
    assert len(merged) == 1 and merged[0].source == "patient_reported" and merged[0].also[0]["source"] == "ocr_doctor_confirmed"
    res = metro(r)
    hits = [i for i in res["interactions"] if "Monitor PT/INR" in i["action"]]
    assert len(hits) == 1 and "patient-reported" in hits[0]["with"] and "from scanned prescription" in hits[0]["with"]


def test_lab_rows_and_self_reported_only_text_are_unchanged():
    ctx = map_record(rec([scan([], type_="lab_report")], meds_any="yes", meds_list="warfarin"))
    assert ctx.ocr_meds == [] and [m.generic for m in ctx.all_meds()] == ["warfarin"]
    res = metro(rec(meds_any="yes", meds_list="warfarin", hx_abdomen=["none"]))
    hit = next(i for i in res["interactions"] if "Monitor PT/INR" in i["action"])
    assert hit["with"].endswith("(current medicine)")


def test_doctor_typed_medicine_list_keeps_confirmed_scan_medicines():
    from dosing.engine import Request, evaluate
    ctx = map_record(rec([scan(["warfarin"])], hx_abdomen=["none"]))
    res = evaluate(Request("metronidazole", ctx, "amoebiasis (India)", doctor_inputs={"meds_text": "vitamin D"}), CFG)
    assert [i for i in res["interactions"] if "Monitor PT/INR" in i["action"]]
