"""Doctors the patient can choose from (data/doctors.json, synthetic). The choice is the patient's own: nothing here
recommends a doctor from the answers."""
import json
from typing import Optional

from pydantic import BaseModel, ConfigDict

from .models import ROOT, Text

DOCTORS_PATH = ROOT / "data" / "doctors.json"
ANY = "any"   # the patient has no preference; stored as no assignment (assignedDoctor stays empty)


class Doctor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    specialty: Text
    username: Optional[str] = None   # login that sees this doctor's patients first

    def label(self, lang: str) -> str:
        return f"{self.name} - {self.specialty.get(lang)}"


def load_doctors(path=DOCTORS_PATH) -> list[Doctor]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    docs = [Doctor.model_validate(d) for d in raw["doctors"]]
    ids = [d.id for d in docs]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate doctor ids")
    return docs


def get_doctor(doctor_id: Optional[str], doctors: Optional[list[Doctor]] = None) -> Optional[Doctor]:
    return next((d for d in (doctors or load_doctors()) if d.id == doctor_id), None)


def doctor_for_login(username: str, doctors: Optional[list[Doctor]] = None) -> Optional[Doctor]:
    return next((d for d in (doctors or load_doctors()) if d.username and d.username == username.strip().lower()), None)
