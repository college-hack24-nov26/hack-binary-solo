from datetime import date


def edited_fields(original: dict, edited: dict) -> list[str]:
    """Paths of fields the doctor changed, e.g. 'medications[0].frequencyAsWritten'."""
    out = []
    skip = {"needsReview", "reviewReasons", "frequencyParsed", "suggestedGeneric", "matchScore"}
    for key in ("medications", "labResults"):
        for i, (a, b) in enumerate(zip(original.get(key, []), edited.get(key, []))):
            for f in a:
                if f not in skip and a[f] != b.get(f):
                    out.append(f"{key}[{i}].{f}")
        if len(edited.get(key, [])) != len(original.get(key, [])):
            out.append(f"{key}.count")
    for f in ("documentType", "documentDate", "diagnosesAsWritten"):
        if original.get(f) != edited.get(f):
            out.append(f)
    return out


def to_timeline_entry(edited: dict, edits: list[str]) -> dict:
    items = edited["medications"] if edited["documentType"] == "prescription" else edited["labResults"]
    if edited["documentType"] not in ("prescription", "lab_report"):
        items = edited["medications"] + edited["labResults"]
    return {
        "date": edited.get("documentDate") or date.today().isoformat(),
        "type": edited["documentType"],
        "items": items,
        "diagnoses": edited.get("diagnosesAsWritten", []),
        "source": "ocr",
        "editedByDoctor": bool(edits),
        "editedFields": edits,
    }
