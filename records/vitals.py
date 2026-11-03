"""Staff-measured vitals: abnormal flags and BMI. DRAFT adult thresholds, unsourced; a prompt to look, not a diagnosis."""
from typing import Optional

from .schema import Vitals

ADULT_MIN_AGE = 12


def bmi(v: Vitals) -> Optional[float]:
    return round(v.weightKg / (v.heightCm / 100) ** 2, 1) if v.weightKg and v.heightCm else None


def abnormal(v: Vitals, age_years: Optional[float]) -> dict[str, str]:
    """field -> short reason. Empty for children (adult ranges do not apply) and for unmeasured fields."""
    if age_years is not None and age_years < ADULT_MIN_AGE:
        return {}
    out: dict[str, str] = {}
    if v.bpSystolic is not None and (v.bpSystolic >= 140 or v.bpSystolic < 90):
        out["bpSystolic"] = "high" if v.bpSystolic >= 140 else "low"
    if v.bpDiastolic is not None and (v.bpDiastolic >= 90 or v.bpDiastolic < 60):
        out["bpDiastolic"] = "high" if v.bpDiastolic >= 90 else "low"
    if v.pulse is not None and (v.pulse > 100 or v.pulse < 50):
        out["pulse"] = "fast" if v.pulse > 100 else "slow"
    if v.tempC is not None and (v.tempC >= 38.0 or v.tempC < 35.0):
        out["tempC"] = "fever" if v.tempC >= 38.0 else "low"
    if v.spo2 is not None and v.spo2 < 94:
        out["spo2"] = "low"
    if v.respRate is not None and (v.respRate > 20 or v.respRate < 12):
        out["respRate"] = "fast" if v.respRate > 20 else "slow"
    if v.bloodGlucose is not None and (v.bloodGlucose >= 200 or v.bloodGlucose < 70):
        out["bloodGlucose"] = "high" if v.bloodGlucose >= 200 else "low"
    return out
