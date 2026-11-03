"""PatientRecord: what is saved locally for one patient. Pseudonym token, no real name or contact."""
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from intake.redflags import Triggered

SCHEMA_VERSION = "0.1"
YNU = Optional[Literal["yes", "no", "unsure"]]


class Consent(BaseModel):
    given: bool = False
    timestamp: Optional[str] = None       # ISO-8601, set when the patient taps "I agree"
    graphVersion: Optional[str] = None


class DosingInputs(BaseModel):
    """Safety basics for the (future) dosage engine. None = not captured; see `missing`."""
    ageYears: Optional[float] = None
    weightKg: Optional[float] = None
    sex: Optional[Literal["female", "male", "other"]] = None
    pregnancy: Optional[Literal["yes", "no", "unsure", "not_applicable"]] = None
    allergies: list[str] = []             # penicillins | sulfa | nsaids | "other: <text>"
    renal: YNU = None
    hepatic: YNU = None
    diabetes: YNU = None
    hypertension: YNU = None
    asthma: YNU = None
    currentMeds: list[str] = []
    missing: list[str] = []               # fields that are skipped / "not sure" / not captured


class Complaint(BaseModel):
    id: Optional[str] = None
    label: Optional[str] = None
    text: Optional[str] = None            # free text when the complaint is "something else"


class AnswerLine(BaseModel):
    nodeId: str
    label: str = ""                        # short English label (doctor summary)
    question: str
    answer: str                           # English display text, "Not sure" and "Skipped" kept distinct
    raw: Any = None


class SiteAnswer(BaseModel):
    """socrates.site from a body_map node. special: tell_doctor | none | unsure | skipped (regions empty)."""
    nodeId: str
    regions: list[str] = []
    view: Optional[Literal["front", "back"]] = None
    inputMode: Optional[Literal["map", "list"]] = None
    special: Optional[str] = None


class RadiationAnswer(BaseModel):
    nodeId: str
    regions: list[str] = []
    special: Optional[str] = None


class TimelineEntry(BaseModel):
    """Shape produced by ocr.timeline.to_timeline_entry."""
    model_config = ConfigDict(extra="allow")
    date: str
    type: str
    items: list[dict] = []
    diagnoses: list[str] = []
    source: str = "ocr"
    editedByDoctor: bool = False
    editedFields: list[str] = []


class DoctorEdit(BaseModel):
    original: str
    edited: str
    editedAt: str


class Vitals(BaseModel):
    """Measured by staff at triage (not patient-reported). None = not measured. Bounds reject typos, not diagnoses."""
    bpSystolic: Optional[int] = Field(None, ge=40, le=300)
    bpDiastolic: Optional[int] = Field(None, ge=20, le=200)
    pulse: Optional[int] = Field(None, ge=20, le=250)
    tempC: Optional[float] = Field(None, ge=30, le=45)
    spo2: Optional[int] = Field(None, ge=50, le=100)
    respRate: Optional[int] = Field(None, ge=4, le=80)
    weightKg: Optional[float] = Field(None, gt=0, le=400)
    heightCm: Optional[float] = Field(None, ge=30, le=250)
    bloodGlucose: Optional[float] = Field(None, ge=10, le=900)   # mg/dL
    notes: str = ""
    recordedBy: Optional[str] = None
    recordedAt: Optional[str] = None      # ISO-8601

    def any_measured(self) -> bool:
        return any(getattr(self, f) is not None for f in ("bpSystolic", "bpDiastolic", "pulse", "tempC", "spo2",
                                                          "respRate", "weightKg", "heightCm", "bloodGlucose"))


class DosingCheck(BaseModel):
    """A dosage check the doctor confirmed. Stored beside the quiz data; never overwrites DosingInputs or answers."""
    at: str
    doctorId: str
    drug: str
    indication: Optional[str] = None
    ruleId: Optional[str] = None
    status: str
    dataStatus: str = "UNVERIFIED"
    result: dict = {}                      # the full engine Result at confirmation
    doctorInputs: dict = {}                # what the doctor typed (weight, creatinine, ...), kept apart from the quiz answers
    overrideReasons: list[str] = []
    overrideCategories: list[str] = []
    acknowledgedItems: list[str] = []      # unchecked free-text contraindications the doctor ticked 'I have checked these' for


class PatientRecord(BaseModel):
    schemaVersion: str = SCHEMA_VERSION
    token: str
    status: Literal["in_progress", "complete"] = "in_progress"
    createdAt: str
    updatedAt: str
    language: Literal["en", "hi", "mr"] = "en"
    consent: Consent = Consent()
    dosingInputs: DosingInputs = DosingInputs()
    complaint: Complaint = Complaint()
    socrates: dict[str, Union[SiteAnswer, RadiationAnswer, list[AnswerLine]]] = {}
    history: list[AnswerLine] = []
    answers: dict[str, Any] = {}          # raw answers, only for nodes on the final path
    redFlags: list[Triggered] = []
    timeline: list[TimelineEntry] = []
    intakeDurationSeconds: Optional[int] = None
    fieldsCaptured: int = 0
    assignedDoctor: Optional[str] = None   # doctor id chosen by the patient (data/doctors.json); None = no preference
    vitals: Optional[Vitals] = None        # entered by staff on the Staff page
    doctorNotes: str = ""                  # assessment / plan, written by the doctor
    doctorEdits: dict[str, DoctorEdit] = {}
    editedByDoctor: bool = False
    editedFields: list[str] = Field(default_factory=list)
    visitHistory: dict[str, str] = {}      # History-check answers (yes/no/unsure), doctor-confirmed, reused for every drug this visit
    visitHistoryBy: Optional[str] = None
    visitHistoryAt: Optional[str] = None
    dosingChecks: list[DosingCheck] = []   # confirmed dosage checks (doctor), see dosing/service.py
