"""Code-side enrichment of validated VLM output. No LLM involvement."""
from .formulary import load_formulary, match_drug
from .frequency import parse_frequency
from .schema import RawExtraction


def enrich(raw: RawExtraction, review_threshold: float = 0.7, terms=None) -> dict:
    terms = terms if terms is not None else load_formulary()
    meds = []
    for m in raw.medications:
        d = m.model_dump()
        match = match_drug(m.nameAsWritten, terms)
        reasons = []
        if m.route and (m.route.strip().lower() == (m.frequencyAsWritten or "").strip().lower()
                        or parse_frequency(m.route)["kind"] != "unknown"):
            d["route"] = None  # model put a frequency in the route field
            reasons.append("route looked like a frequency, cleared")
        if m.confidence < review_threshold:
            reasons.append("low confidence")
        if match["suggestedGeneric"] is None:
            reasons.append("not in formulary")
        else:
            if match["matchScore"] < 1.0:
                reasons.append("fuzzy formulary match, verify spelling")
            if match["ambiguous"]:
                reasons.append("ambiguous formulary match")
        if not m.frequencyAsWritten:
            reasons.append("no frequency")
        d.update(
            frequencyParsed=parse_frequency(m.frequencyAsWritten),
            suggestedGeneric=match["suggestedGeneric"],
            matchScore=match["matchScore"],
            needsReview=bool(reasons),
            reviewReasons=reasons,
        )
        if m.frequencyAsWritten and d["frequencyParsed"]["kind"] == "unknown":
            d["needsReview"] = True
            d["reviewReasons"].append("frequency not understood")
        meds.append(d)
    labs = []
    for l in raw.labResults:
        d = l.model_dump()
        reasons = []
        if l.confidence < review_threshold:
            reasons.append("low confidence")
        if l.value is None:
            reasons.append("no value")
        d.update(needsReview=bool(reasons), reviewReasons=reasons)
        labs.append(d)
    return {
        "documentType": raw.documentType,
        "documentDate": raw.documentDate,
        "medications": meds,
        "labResults": labs,
        "diagnosesAsWritten": raw.diagnosesAsWritten,
        "unreadable": raw.unreadable,
        "warnings": raw.warnings,
    }
