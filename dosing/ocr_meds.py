"""Medicine names from DOCTOR-CONFIRMED scans of old prescriptions -> current-medicine candidates for the interaction check.
Reads the timeline the OCR panel already writes (a TimelineEntry is only appended after the doctor clicks Confirm; the
entry then carries `confirmedBy`). OCR parsing is not touched, and unconfirmed OCR text never reaches this module.
Names go through the same synonym table as self-reported medicines. A name the table cannot place is returned as
'unparsed from prescription', never dropped."""
from dataclasses import replace

from . import meds as medsmod

PROVENANCE = "ocr_doctor_confirmed"


def confirmed_entries(timeline) -> list:
    """(index, entry) for scans a doctor confirmed. An entry without `confirmedBy` is treated as unconfirmed."""
    out = []
    for i, e in enumerate(timeline or []):
        by = getattr(e, "confirmedBy", None) if not isinstance(e, dict) else e.get("confirmedBy")
        if by and (getattr(e, "source", None) if not isinstance(e, dict) else e.get("source")) == "ocr":
            out.append((i, e))
    return out


def _get(e, k, default=None):
    return e.get(k, default) if isinstance(e, dict) else getattr(e, k, default)


def from_timeline(timeline) -> tuple[list, list]:
    """-> (MedMatch list with source/scan link, [{"token","scan_ref","scan_date"}] unparsed)."""
    matches, unparsed = [], []
    for i, e in confirmed_entries(timeline):
        ref, date = f"timeline[{i}]", _get(e, "date")
        for item in _get(e, "items", []) or []:
            name = item.get("nameAsWritten") if isinstance(item, dict) else None
            if not name or not str(name).strip():
                continue                                    # lab rows have no medicine name
            found, left = medsmod.parse_names(str(name))
            matches += [replace(m, source=PROVENANCE, scan_ref=ref, scan_date=date) for m in found]
            unparsed += [{"token": t, "scan_ref": ref, "scan_date": date} for t in left]
    seen, uniq = set(), []
    for u in unparsed:
        k = (u["token"].lower(), u["scan_ref"])
        if k not in seen:
            seen.add(k)
            uniq.append(u)
    return matches, uniq


def apply_to_context(ctx, timeline) -> None:
    ctx.ocr_meds, ctx.ocr_unparsed = from_timeline(timeline)
