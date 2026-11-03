"""Audit log, confirmation and override logging; quiz answers stay untouched."""
import json
from datetime import datetime

import pytest

from dosing import audit, service
from records.schema import PatientRecord

from dosing_helpers import quiz

NOW = datetime(2026, 1, 2, 3, 4, 5).astimezone()


@pytest.fixture(autouse=True)
def datadir(tmp_path, monkeypatch):
    monkeypatch.setenv("INTAKE_DATA_DIR", str(tmp_path))
    return tmp_path


def rec(**kw):
    return PatientRecord(token="PT-ABCDEF", createdAt="2026-01-01T00:00:00", updatedAt="2026-01-01T00:00:00", answers=quiz(**kw))


def test_evaluate_is_logged_with_inputs_provenance_and_doctor():
    r = rec(age_y=5, wt=18)
    res = service.evaluate_for_record(r, "paracetamol", "pain/fever", doctor_id="D1", doctor_inputs={"weight_kg": 18}, now=NOW)
    e = audit.read()
    assert len(e) == 1 and e[0]["event"] == "evaluate" and e[0]["doctor_id"] == "D1" and e[0]["token"] == "PT-ABCDEF"
    assert e[0]["result"]["status"] == res["status"] and e[0]["inputs"]["doctor_inputs"] == {"weight_kg": 18}
    assert e[0]["provenance"]["weight_kg"]["provenance"] == "doctor_entered"
    assert audit.verify()


def test_override_is_logged_with_its_reason():
    r = rec(allergies=["nsaids"])
    service.evaluate_for_record(r, "ibuprofen", "pain/fever", doctor_id="D2", override_category="patient_tolerates", override_reason="Specialist advised, tolerated before", now=NOW)
    ev = audit.read()
    assert [x["event"] for x in ev] == ["evaluate", "override"]
    assert ev[1]["override_reason"].startswith("Specialist") and ev[1]["override_category"] == "patient_tolerates" and "NSAID" in ev[1]["overridden_block"]
    assert audit.verify()


def test_confirm_requires_a_final_ok_result_and_saves_beside_the_answers():
    r = rec(age_y=5, wt=18)
    answers_before = json.dumps(r.answers, sort_keys=True)
    res = service.evaluate_for_record(r, "paracetamol", "pain/fever", doctor_id="D1", now=NOW)
    assert not service.can_confirm(res)                      # weight not yet confirmed
    with pytest.raises(ValueError):
        service.confirm(r, res, doctor_id="D1")
    res = service.evaluate_for_record(r, "paracetamol", "pain/fever", doctor_id="D1", confirmed=["weight_kg"], now=NOW)
    assert service.can_confirm(res)
    r2 = service.confirm(r, res, doctor_id="D1", doctor_inputs={}, now=NOW)
    assert len(r2.dosingChecks) == 1 and r2.dosingChecks[0].drug == "paracetamol"
    assert json.dumps(r2.answers, sort_keys=True) == answers_before and r2.dosingInputs == r.dosingInputs
    assert audit.read()[-1]["event"] == "confirm"


def test_tampering_is_detected():
    service.evaluate_for_record(rec(), "paracetamol", "pain/fever", doctor_id="D1", now=NOW)
    p = audit.log_path()
    p.write_text(p.read_text().replace('"D1"', '"D9"'))
    assert not audit.verify()


def test_record_with_dosing_checks_round_trips_through_the_store():
    from records import store
    r = rec(age_y=5, wt=18)
    res = service.evaluate_for_record(r, "paracetamol", "pain/fever", doctor_id="D1", confirmed=["weight_kg"], now=NOW, log=False)
    store.save(service.confirm(r, res, doctor_id="D1", now=NOW))
    assert store.load("PT-ABCDEF").dosingChecks[0].ruleId == "paracetamol#2"


def test_unchecked_free_text_contraindications_need_the_acknowledgement_to_confirm():
    r = rec(age_y=40, wt=70)
    res = service.evaluate_for_record(r, "amoxicillin_clavulanate", "severe infection", doctor_id="D1", now=NOW, log=False,
                                      selected_rule_id="amoxicillin_clavulanate#1", form="tablet 500 mg + 125 mg")
    assert any("cholestatic" in t for t in res["acknowledge_items"])
    ready = dict(res, status="ok", final=True, needs_input=[], blocks=[])           # isolate the acknowledgement rule
    assert not service.can_confirm(ready) and service.can_confirm(ready, acknowledged=True)
    with pytest.raises(ValueError):
        service.confirm(r, ready, doctor_id="D1", now=NOW)
    r2 = service.confirm(r, ready, doctor_id="D1", now=NOW, acknowledged=True)
    assert r2.dosingChecks[0].acknowledgedItems == res["acknowledge_items"]
    assert audit.read()[-1]["inputs"]["acknowledged_items"] == res["acknowledge_items"]
    none = service.evaluate_for_record(rec(age_y=5, wt=18), "paracetamol", "pain/fever", doctor_id="D1", confirmed=["weight_kg"], now=NOW, log=False)
    assert none["acknowledge_items"] == [] and service.can_confirm(none)
