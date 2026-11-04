"""How the kiosk proves who someone is. One interface, one working implementation (identifier + 4-digit PIN).

There is no SMS gateway offline, so a real one-time password cannot exist here. `OtpProvider` is a documented stub for the day a
gateway is installed; it raises instead of pretending, and no OTP screen exists in the kiosk. Nothing here says "verified"."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from records import identity, patients


class AuthError(Exception):
    def __init__(self, code: str, retry_after_s: int = 0):
        super().__init__(code)
        self.code, self.retry_after_s = code, retry_after_s


@dataclass
class AuthResult:
    patient: patients.Patient
    event: str                      # identity.login | identity.login_failed | identity.locked


class IdentityProvider(ABC):
    @abstractmethod
    def authenticate(self, patient: patients.Patient, secret: str) -> AuthResult:
        """Return the patient on success or raise AuthError. Callers hold WRITE_LOCK and save the patient afterwards."""

    @abstractmethod
    def enrol(self, kind: str, normalised: str, secret: str, consent: patients.ConsentRecord) -> patients.Patient: ...


class PinProvider(IdentityProvider):
    max_failures = patients.LOCK_AFTER
    lock_seconds = patients.LOCK_SECONDS

    def authenticate(self, patient, secret):
        now = datetime.now().astimezone()
        if patients.is_locked(patient, now):
            left = int((datetime.fromisoformat(patient.lockedUntil) - now).total_seconds()) + 1
            raise AuthError("locked", left)
        if not patient.pinHash or not patient.lookupHash:
            raise AuthError("no_pin")                       # a walk-in not yet completed by staff
        if identity.verify_pin(patient.lookupHash, secret, patient.pinHash):
            patient.failedAttempts, patient.lockedUntil = 0, None
            return AuthResult(patient, "identity.login")
        patient.failedAttempts += 1
        if patient.failedAttempts >= self.max_failures:
            patient.failedAttempts = 0
            patient.lockedUntil = (now + timedelta(seconds=self.lock_seconds)).isoformat(timespec="seconds")
            return AuthResult(patient, "identity.locked")
        return AuthResult(patient, "identity.login_failed")

    def enrol(self, kind, normalised, secret, consent):
        if not identity.valid_pin(secret):
            raise AuthError("pin_format")
        return patients.create(kind, normalised, secret, consent)


class OtpProvider(IdentityProvider):
    """STUB. When an SMS gateway exists: send a code to the mobile number (decrypt `identifierEnc` only inside this class),
    store a salted hash of the code with a 5-minute expiry, and compare in `authenticate`. Keep the same lockout rules.
    Until then this raises, so nothing can be mistaken for working OTP."""

    def authenticate(self, patient, secret):
        raise NotImplementedError("OTP needs an SMS gateway, which this offline kiosk does not have")

    def enrol(self, kind, normalised, secret, consent):
        raise NotImplementedError("OTP needs an SMS gateway, which this offline kiosk does not have")


def default_provider() -> IdentityProvider:
    return PinProvider()
