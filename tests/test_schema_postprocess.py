import pytest
from pydantic import ValidationError
from ocr.postprocess import enrich
from ocr.schema import RawExtraction

GOOD = {"documentType": "prescription", "documentDate": "12/03/2024",
        "medications": [
            {"nameAsWritten": "Tab. Paracetamol", "strength": "500 mg", "frequencyAsWritten": "1-0-1", "confidence": 0.95},
            {"nameAsWritten": "Zorbitex", "frequencyAsWritten": "OD", "confidence": 0.9},
            {"nameAsWritten": "Tab. Metformin", "frequencyAsWritten": "BD", "confidence": 0.4},
            {"nameAsWritten": "Cap. Doxycycline", "frequencyAsWritten": "weird", "confidence": 0.9}],
        "labResults": [{"test": "Hb", "value": None, "confidence": 0.9}],
        "diagnosesAsWritten": [], "unreadable": [], "warnings": []}


def test_valid_parses_and_extra_keys_ignored():
    r = RawExtraction.model_validate({**GOOD, "patientName": "x"})
    assert len(r.medications) == 4


@pytest.mark.parametrize("bad", [
    {**GOOD, "documentType": "xray"},
    {**GOOD, "medications": [{"nameAsWritten": "A", "confidence": 1.5}]},
    {k: v for k, v in GOOD.items() if k != "documentType"},
    {**GOOD, "medications": [{"confidence": 0.9}]},
])
def test_invalid_rejected(bad):
    with pytest.raises(ValidationError):
        RawExtraction.model_validate(bad)


def test_needs_review_rules():
    out = enrich(RawExtraction.model_validate(GOOD))
    m = out["medications"]
    assert not m[0]["needsReview"] and m[0]["suggestedGeneric"] == "paracetamol"
    assert m[1]["needsReview"] and "not in formulary" in m[1]["reviewReasons"]
    assert m[2]["needsReview"] and "low confidence" in m[2]["reviewReasons"]
    assert m[3]["needsReview"] and "frequency not understood" in m[3]["reviewReasons"]
    assert m[0]["nameAsWritten"] == "Tab. Paracetamol"  # never rewritten
    assert out["labResults"][0]["needsReview"]


def test_frequency_in_route_is_cleared():
    r = RawExtraction.model_validate({**GOOD, "medications": [
        {"nameAsWritten": "Tab. Paracetamol", "route": "1-0-1", "frequencyAsWritten": "1-0-1", "confidence": 0.9},
        {"nameAsWritten": "Inj. Ondansetron", "route": "IV", "frequencyAsWritten": "SOS", "confidence": 0.9}]})
    m = enrich(r)["medications"]
    assert m[0]["route"] is None and m[0]["needsReview"]
    assert m[1]["route"] == "IV"


def test_vlm_schema_requires_all_fields():
    from ocr.schema import vlm_json_schema
    sc = vlm_json_schema()
    assert set(sc["required"]) == set(sc["properties"])
    assert "frequencyAsWritten" in sc["$defs"]["RawMedication"]["required"]


def test_fuzzy_match_flagged_but_name_untouched():
    r = RawExtraction.model_validate({**GOOD, "medications": [
        {"nameAsWritten": "Tab. Amlodipne", "frequencyAsWritten": "OD", "confidence": 0.99}]})
    m = enrich(r)["medications"][0]
    assert m["suggestedGeneric"] == "amlodipine" and m["needsReview"]
    assert m["nameAsWritten"] == "Tab. Amlodipne"
