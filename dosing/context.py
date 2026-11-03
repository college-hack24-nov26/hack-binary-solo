"""PatientContext: every value carries provenance. 'unknown' (not asked, skipped, not sure) is never 'no'."""
from dataclasses import dataclass, field
from typing import Any

PATIENT = "patient_reported"
DOCTOR = "doctor_entered"
CONFIRMED = "doctor_confirmed"
DERIVED = "derived"
UNKNOWN = "unknown"
PROVENANCE = (PATIENT, DOCTOR, CONFIRMED, DERIVED, UNKNOWN)
TRUSTED = (DOCTOR, CONFIRMED)            # provenance that counts as doctor-verified


@dataclass
class Val:
    value: Any
    prov: str = UNKNOWN
    note: str = ""


@dataclass
class PatientContext:
    f: dict = field(default_factory=dict)              # name -> Val
    meds: list = field(default_factory=list)           # list[meds.MedMatch]
    unparsed_meds: list = field(default_factory=list)  # raw tokens nobody recognised
    ocr_meds: list = field(default_factory=list)       # meds.MedMatch from doctor-confirmed scans (provenance ocr_doctor_confirmed)
    ocr_unparsed: list = field(default_factory=list)   # [{"token","scan_ref","scan_date"}] scan names the synonym table cannot place
    allergy_other_raw: str = ""
    red_flags: list = field(default_factory=list)      # [{"ruleId","severity","label"}] read-only from the red-flag service

    def set(self, name: str, value, prov: str, note: str = "") -> None:
        self.f[name] = Val(value, prov if value is not None else UNKNOWN, note)

    def get(self, name: str, default=None):
        v = self.f.get(name)
        return default if v is None or v.value is None else v.value

    def prov(self, name: str) -> str:
        v = self.f.get(name)
        return UNKNOWN if v is None or v.value is None else v.prov

    def tri(self, name: str) -> str:
        """'yes' | 'no' | 'unknown'. Anything that is not an explicit yes/no (including 'unsure') is unknown."""
        v = self.get(name)
        return v if v in ("yes", "no") else "unknown"

    def trusted(self, name: str) -> bool:
        return self.prov(name) in TRUSTED

    def all_meds(self) -> list:
        """Self-reported (or doctor-typed) medicines merged with those from doctor-confirmed scans, de-duplicated.
        A medicine found in both keeps one entry and lists the scan under `also`."""
        from dataclasses import replace
        out, index = [], {}
        for m in self.meds:
            m2 = replace(m, also=list(m.also))
            out.append(m2)
            index[m.drug_id or m.generic] = m2
        for m in self.ocr_meds:
            k = m.drug_id or m.generic
            origin = {"source": m.source, "scan_ref": m.scan_ref, "scan_date": m.scan_date}
            if k in index:
                if origin not in index[k].also:
                    index[k].also.append(origin)
            else:
                m2 = replace(m, also=list(m.also))
                out.append(m2)
                index[k] = m2
        return out

    def provenance_dict(self) -> dict:
        return {k: {"value": v.value, "provenance": v.prov, **({"note": v.note} if v.note else {})}
                for k, v in sorted(self.f.items())}

    def copy(self) -> "PatientContext":
        c = PatientContext(f={k: Val(v.value, v.prov, v.note) for k, v in self.f.items()}, meds=list(self.meds),
                           unparsed_meds=list(self.unparsed_meds), ocr_meds=list(self.ocr_meds),
                           ocr_unparsed=list(self.ocr_unparsed), allergy_other_raw=self.allergy_other_raw,
                           red_flags=list(self.red_flags))
        return c

    # age helpers: days, as a [lo, hi] window (hi exclusive). Doctor-entered exact age collapses the window.
    def age_days(self):
        lo = self.get("age_days_lo")
        hi = self.get("age_days_hi")
        return (None, None) if lo is None else (lo, hi)
