from ocr.timeline import edited_fields, to_timeline_entry

ORIG = {"documentType": "prescription", "documentDate": "12/03/2024", "diagnosesAsWritten": [],
        "medications": [{"nameAsWritten": "Tab. X", "frequencyAsWritten": "BD", "needsReview": True}], "labResults": []}


def test_no_edits():
    e = to_timeline_entry(ORIG, edited_fields(ORIG, ORIG))
    assert e["source"] == "ocr" and e["editedByDoctor"] is False and e["date"] == "12/03/2024"


def test_edit_tracking():
    ed = {**ORIG, "medications": [{**ORIG["medications"][0], "frequencyAsWritten": "TDS"}]}
    assert edited_fields(ORIG, ed) == ["medications[0].frequencyAsWritten"]
    assert to_timeline_entry(ed, edited_fields(ORIG, ed))["editedByDoctor"] is True


def test_added_row_counts_as_edit():
    ed = {**ORIG, "medications": ORIG["medications"] + [{"nameAsWritten": "Y"}]}
    assert "medications.count" in edited_fields(ORIG, ed)
