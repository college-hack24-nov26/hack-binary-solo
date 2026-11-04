"""Request/response DTOs. Engine results are passed through untouched as `result: dict` (never reshaped)."""
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Lang = Literal["en", "hi", "mr"]


class Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- system
class Health(Out):
    ok: bool
    engineVersion: str
    formularyLoaded: bool


class SystemConfig(Out):
    demoMode: bool
    languages: list[str]
    ocrAvailable: bool
    formularyLoaded: bool
    formularyError: Optional[str] = None
    strict: bool
    opdMinutesPerPatient: int


class LocalModel(Out):
    host: str
    port: int
    reachable: bool
    error: Optional[str] = None


class Service(Out):
    name: str
    target: str


class ProbeConfig(Out):
    host: str
    port: int
    timeoutS: float
    intervalS: int


class OfflineStatus(Out):
    level: Literal["ok", "warn", "pending"]
    headline: str
    strict: bool
    localModel: LocalModel
    services: list[Service]
    internet: Optional[dict] = None
    probe: ProbeConfig


# ---------------------------------------------------------------- auth
class LoginIn(In):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class Me(Out):
    username: str
    role: Literal["staff", "doctor"]
    doctorId: Optional[str] = None


# ---------------------------------------------------------------- reference
class Region(Out):
    id: str
    view: Literal["front", "back"]
    side: str
    label: dict[str, str]
    polygon: list[list[float]]


class BodyRegions(Out):
    viewBox: list[int]
    sideLabels: dict[str, dict[str, str]]
    viewLabels: dict[str, dict[str, str]]
    translationStatus: str
    regions: list[Region]


class DoctorOut(Out):
    id: str
    name: str
    specialty: dict[str, str]
    room: Optional[str] = None
    floor: Optional[dict[str, str]] = None
    lineColor: Optional[str] = None
    lineName: Optional[dict[str, str]] = None
    lineTextColor: Optional[str] = None


# ---------------------------------------------------------------- kiosk
class NewKioskSession(In):
    language: Lang = "en"


class KioskOption(Out):
    id: str
    label: str


class KioskNode(Out):
    id: str
    type: str
    section: str
    text: str
    options: list[KioskOption] = []
    min: Optional[float] = None
    max: Optional[float] = None
    maxSelections: Optional[int] = None


class Progress(Out):
    done: int
    total: int


class KioskScreen(Out):
    token: str
    language: Lang
    stage: Literal["consent", "question", "review", "done", "declined"]
    node: Optional[KioskNode] = None
    value: Any = None
    progress: Progress
    canGoBack: bool
    redFlagMessage: Optional[str] = None
    doctorId: Optional[str] = None


class KioskCreated(Out):
    token: str
    kioskKey: str
    screen: KioskScreen


class AnswerIn(In):
    nodeId: str
    value: Any


class BodyMapIn(In):
    nodeId: str
    regions: list[str] = []
    view: Literal["front", "back"] = "front"
    inputMode: Literal["map", "list"] = "map"
    special: Optional[str] = None


class NodeIn(In):
    nodeId: str


class BackIn(In):
    nodeId: Optional[str] = None      # None = from the review screen


class LanguageIn(In):
    language: Lang


class ConsentIn(In):
    choice: Literal["agree", "decline"]


class DoctorChoiceIn(In):
    doctorId: Optional[str] = None


class ReviewItem(Out):
    nodeId: str
    question: str
    answer: str


class Review(Out):
    items: list[ReviewItem]


class TokenSlip(Out):
    queueNumber: int
    queueDate: str
    token: str
    doctor: Optional[DoctorOut] = None
    room: Optional[str] = None
    floor: Optional[dict[str, str]] = None
    guidance: str
    estimatedWaitMinutes: int
    patientsAhead: int
    estimateLabel: str = "estimate"


# ---------------------------------------------------------------- patients
class TriggerLine(Out):
    nodeId: str
    label: str
    answer: str


class RedFlagOut(Out):
    ruleId: str
    severity: str
    staffMessage: str
    patientMessage: dict
    draft: bool
    label: str
    triggeredBy: list[TriggerLine]


class BoardRow(Out):
    token: str
    queueNumber: Optional[int] = None
    status: str
    ageYears: Optional[float] = None
    sex: Optional[str] = None
    complaint: Optional[str] = None
    complaintText: Optional[str] = None
    redFlags: list[RedFlagOut]
    urgent: bool
    assignedDoctor: Optional[str] = None
    vitalsPresent: bool
    pendingScans: int
    minutesWaiting: int
    createdAt: str
    updatedAt: str
    mine: bool = False


class Board(Out):
    rows: list[BoardRow]
    date: str


class AnswerLineOut(Out):
    nodeId: str
    label: str
    question: str
    answer: str
    section: str


class PendingScanMeta(Out):
    id: str
    uploadedBy: str
    uploadedAt: str
    documentType: Optional[str] = None
    documentDate: Optional[str] = None
    items: int
    imageAvailable: bool


class PendingScanOut(Out):
    id: str
    uploadedBy: str
    uploadedAt: str
    latencyS: float
    draft: dict


class PatientView(Out):
    token: str
    status: str
    createdAt: str
    updatedAt: str
    language: str
    queueNumber: Optional[int] = None
    queueDate: Optional[str] = None
    finishedAt: Optional[str] = None
    complaint: dict
    dosingInputs: dict
    redFlags: list[RedFlagOut]
    answers: list[AnswerLineOut]
    assignedDoctor: Optional[str] = None
    vitals: Optional[dict] = None
    abnormal: dict[str, str] = {}
    bmi: Optional[float] = None
    weightMismatch: Optional[str] = None
    pendingScans: list[PendingScanMeta] = []
    timelineCount: int = 0
    role: Literal["staff", "doctor"]
    # doctor-only below (None for staff)
    socrates: Optional[dict] = None
    doctorNotes: Optional[str] = None
    dosingChecks: Optional[list[dict]] = None
    visitHistory: Optional[dict[str, str]] = None
    visitHistoryBy: Optional[str] = None
    visitHistoryAt: Optional[str] = None
    intakeDurationSeconds: Optional[int] = None
    fieldsCaptured: Optional[int] = None
    editedFields: Optional[list[str]] = None


class VitalsIn(In):
    bpSystolic: Optional[int] = Field(None, ge=40, le=300)
    bpDiastolic: Optional[int] = Field(None, ge=20, le=200)
    pulse: Optional[int] = Field(None, ge=20, le=250)
    tempC: Optional[float] = Field(None, ge=30, le=45)
    spo2: Optional[int] = Field(None, ge=50, le=100)
    respRate: Optional[int] = Field(None, ge=4, le=80)
    weightKg: Optional[float] = Field(None, gt=0, le=400)
    heightCm: Optional[float] = Field(None, ge=30, le=250)
    bloodGlucose: Optional[float] = Field(None, ge=10, le=900)
    notes: str = Field("", max_length=500)


class HelpRequest(Out):
    id: int
    token: str
    at: str
    dismissed: bool


class HelpRequests(Out):
    items: list[HelpRequest]


# ---------------------------------------------------------------- doctor
class SummaryField(Out):
    key: str
    label: str
    value: str
    missing: bool
    editable: bool
    edited: bool
    original: Optional[str] = None


class SummarySection(Out):
    title: str
    fields: list[SummaryField]


class SummaryOut(Out):
    token: str
    lang: Lang
    sections: list[SummarySection]
    intakeDurationSeconds: Optional[int] = None
    durationText: str
    fieldsCaptured: int
    editedByDoctor: bool
    editedFields: list[str]
    paragraph: str


class SummaryPatch(In):
    lang: Lang = "en"
    values: dict[str, str]


class Paragraph(Out):
    source: str
    text: str
    reason: Optional[str] = None
    label: Optional[str] = None


class NotesIn(In):
    notes: str = Field("", max_length=20000)


class NotesOut(Out):
    doctorNotes: str


class Timeline(Out):
    confirmed: list[dict]
    pending: list[dict]


class ScanConfirmIn(In):
    documentType: Literal["prescription", "lab_report", "discharge_summary", "other"]
    documentDate: Optional[str] = None
    medications: list[dict] = []
    labResults: list[dict] = []
    diagnosesAsWritten: list[str] = []


# ---------------------------------------------------------------- dosing
class DrugIndication(Out):
    key: str
    labels: list[str]


class Drug(Out):
    id: str
    generic: str
    indications: list[DrugIndication]
    forms: list[str]


class Drugs(Out):
    drugs: list[Drug]
    overrideCategories: dict[str, str]
    banner: str
    demoBanner: str
    allowUnverified: bool
    demoMode: bool


class HistoryItemsIn(In):
    token: str
    drug: str


class HistoryItem(Out):
    field: str
    label: str
    question: str
    value: str
    prov: str
    required: bool
    source: str


class ContextField(Out):
    name: str
    label: str
    value: Optional[str] = None
    provenance: str


class MedicineLine(Out):
    generic: str
    raw: str
    sources: list[str]


class HistoryItems(Out):
    items: list[HistoryItem]
    unknown: list[HistoryItem]
    context: list[ContextField]
    medicines: list[MedicineLine]
    unparsed: list[str]
    ocrUnparsed: list[dict]


class HistoryIn(In):
    answers: dict[str, Literal["yes", "no", "unsure"]]


class HistoryOut(Out):
    visitHistory: dict[str, str]
    by: Optional[str] = None
    at: Optional[str] = None


class EvaluateIn(In):
    """Mirrors dosing.service.evaluate_for_record's arguments (doctor_id comes from the login, never the client)."""
    token: str
    drug: str
    indication: Optional[str] = None
    doctorInputs: dict[str, Any] = {}
    confirmed: list[str] = []
    visitDrugs: list[str] = []
    selectedRuleId: Optional[str] = None
    form: Optional[str] = None
    route: Optional[str] = None
    showAllRules: bool = False
    overrideReason: Optional[str] = None
    overrideCategory: Optional[str] = None


class MissingItem(Out):
    field: str
    why: str
    kind: str
    key: str
    options: list[str] = []
    hint: Optional[str] = None


class Card(Out):
    status: str
    header: str
    reason: str
    responsible: str
    sources: list[dict]
    missing: list[MissingItem]
    show_numbers: bool
    overrides: list[dict]


class Evaluation(Out):
    resultId: str
    result: dict
    card: Card
    canConfirm: bool
    canConfirmIfAcknowledged: bool


class ConfirmIn(In):
    token: str
    resultId: Optional[str] = None
    request: Optional[EvaluateIn] = None
    acknowledged: bool = False


class Confirmed(Out):
    dosingChecks: list[dict]


# ---------------------------------------------------------------- audit
class AuditRow(Out):
    index: int
    time: str
    doctor: Optional[str] = None
    patient: Optional[str] = None
    drug: Optional[str] = None
    status: Optional[str] = None
    action: str
    event: str
    overrideCategory: Optional[str] = None
    overrideReason: Optional[str] = None
    hash: Optional[str] = None
    prev: Optional[str] = None


class AuditPage(Out):
    rows: list[AuditRow]
    nextCursor: Optional[str] = None
    total: int
    totalAll: int
    facets: dict[str, list[str]]


class AuditVerify(Out):
    ok: bool
    entries: int
    firstBadIndex: Optional[int] = None


class AuditDetail(Out):
    index: int
    hash: Optional[str] = None
    prev: Optional[str] = None
    detail: dict


# ---------------------------------------------------------------- demo
class Fixture(Out):
    key: str
    displayName: str
    title: str
    token: str
    drug: str
    indication: Optional[str] = None


class Loaded(Out):
    token: str
