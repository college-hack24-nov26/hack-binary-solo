"""DTOs for patient identity, kiosk scans, staff lookup and the doctor's patient-papers panel."""
from typing import Any, Literal, Optional

from pydantic import Field

from .schemas import In, Lang, Out

IdKind = Literal["mobile", "abha"]
CONSENT_VERSION = "2026-11-a"
CONSENT_COVERS = ["identifier", "answers", "scans"]


class IdentifyIn(In):
    type: IdKind
    identifier: str = Field(min_length=1, max_length=40)


class IdentifyOut(Out):
    exists: bool
    masked: str


class ConsentIn(In):
    agreed: Literal[True]            # a decline never reaches the server as a consent record: it is the anonymous path
    language: Lang
    covers: list[Literal["identifier", "answers", "scans"]] = Field(default_factory=lambda: ["identifier", "answers", "scans"])


class RegisterIn(In):
    type: IdKind
    identifier: str = Field(min_length=1, max_length=40)
    pin: str = Field(min_length=4, max_length=4)
    consent: ConsentIn


class LoginIn(In):
    type: IdKind
    identifier: str = Field(min_length=1, max_length=40)
    pin: str = Field(min_length=4, max_length=4)


class WalkInIn(In):
    language: Lang


class IdentityOut(Out):
    identityToken: str
    masked: str
    returning: bool
    walkIn: bool = False
    lastVisit: Optional[str] = None
    expiresInS: int


class ScanField(Out):
    value: Optional[str] = None
    confidence: Optional[float] = None
    check: bool = False                      # low confidence: the UI asks the patient to check it


class ScanMedicine(Out):
    name: ScanField
    dose: ScanField
    frequency: ScanField


class ScanOut(Out):
    id: str
    status: Literal["queued", "preparing", "reading", "structuring", "done", "failed", "retake", "unavailable"]
    stage: str
    progress: float                          # 0..1, from real stages and streamed tokens
    elapsedS: float
    docType: Optional[Literal["prescription", "lab_report", "other"]] = None
    docDate: Optional[ScanField] = None
    medicines: list[ScanMedicine] = []
    freeText: str = ""
    confirmed: bool = False
    hasImage: bool = False
    message: Optional[str] = None            # plain-language reason for retake / failed / unavailable
    unverified: Literal[True] = True


class ScanEditIn(In):
    docType: Optional[Literal["prescription", "lab_report", "other"]] = None
    docDate: Optional[str] = Field(None, max_length=40)
    medicines: Optional[list[dict[str, Optional[str]]]] = Field(None, max_length=40)
    freeText: Optional[str] = Field(None, max_length=2000)


class ScansOut(Out):
    scans: list[ScanOut]


# ---------------------------------------------------------------- staff
class PatientAdminOut(Out):
    id: str
    identifierType: str
    masked: str
    needsStaff: bool
    locked: bool
    lockedUntil: Optional[str] = None
    createdAt: str
    visitIds: list[str]
    consents: int
    lastConsentVersion: Optional[str] = None


class PatientLookupOut(Out):
    patients: list[PatientAdminOut]


class ResetPinOut(Out):
    id: str
    pin: str                                  # shown once to the staff member; stored only as a hash
    note: str = "Tell the patient this PIN. They can only use it once to get in; it is not shown again."


class WalkInCompleteIn(In):
    type: IdKind
    identifier: str = Field(min_length=1, max_length=40)


class WalkInCompleteOut(Out):
    patient: PatientAdminOut
    pin: str


# ---------------------------------------------------------------- doctor
class DoctorScanOut(Out):
    id: str
    uploadedAt: str
    docType: Optional[str] = None
    docDate: Optional[str] = None
    medicines: list[dict[str, Any]]
    freeText: str
    confirmedByPatient: bool
    hasImage: bool
    usedByDoctor: Optional[str] = None
    label: str = "Patient-supplied, unverified text"


class DoctorScansOut(Out):
    visit: str
    patientMasked: Optional[str] = None
    scans: list[DoctorScanOut]


class PreviousVisit(Out):
    token: str
    date: str
    complaint: Optional[str] = None
    queueNumber: Optional[int] = None


class PreviousVisitsOut(Out):
    visits: list[PreviousVisit]


class UseMedicinesOut(Out):
    added: int
    scan: str
