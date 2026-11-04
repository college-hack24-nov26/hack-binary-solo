"""Kiosk intake sessions: one IntakeSession per token, in memory, guarded by a per-session kiosk key.

The key is a random secret the tablet keeps in sessionStorage; only its SHA-256 is stored (data_local/kiosk_keys.json) so a
server restart can rebuild the session from the saved record's answers and still check the key. Callers hold WRITE_LOCK
around anything that saves."""
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import Optional

from intake.engine import recompute_path
from intake.models import Graph
from intake.redflags import RedFlagRule
from intake.session import IntakeSession
from records import store
from records.schema import PatientRecord


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def keys_path() -> Path:
    return store.data_dir().parent / "kiosk_keys.json"


class Registry:
    def __init__(self, graph: Graph, rules: list[RedFlagRule]):
        self.graph, self.rules = graph, rules
        self._s: dict[str, IntakeSession] = {}

    # -- keys
    def _keys(self) -> dict:
        p = keys_path()
        try:
            return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        except (OSError, ValueError):
            return {}

    def _save_keys(self, keys: dict) -> None:
        p = keys_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(keys), encoding="utf-8")
        os.replace(tmp, p)

    # -- sessions
    def create(self, language: str) -> tuple[IntakeSession, str]:
        keys = self._keys()
        while True:
            s = IntakeSession(self.graph, self.rules, language=language)
            if s.token not in keys and store.load(s.token) is None:
                break
        key = secrets.token_urlsafe(24)
        keys[s.token] = _hash(key)
        self._save_keys(keys)
        self._s[s.token] = s
        return s, key

    def check_key(self, token: str, key: Optional[str]) -> bool:
        want = self._keys().get(token)
        return bool(key) and want is not None and hmac.compare_digest(want, _hash(key))

    def get(self, token: str) -> Optional[IntakeSession]:
        """The live session, rebuilt from the saved record after a restart. None if nothing is known (e.g. never consented)."""
        if token in self._s:
            return self._s[token]
        rec = store.load(token)
        if rec is None:
            return None
        s = rebuild(self.graph, self.rules, rec)
        self._s[token] = s
        return s

    def forget(self, token: str, drop_key: bool = False) -> None:
        self._s.pop(token, None)
        if drop_key:
            keys = self._keys()
            if keys.pop(token, None) is not None:
                self._save_keys(keys)


def rebuild(graph: Graph, rules: list[RedFlagRule], rec: PatientRecord) -> IntakeSession:
    """Replay the record's answers (in path order) through a fresh IntakeSession and restore its clock fields, so to_record()
    gives the same record. Uses only the public answer() API."""
    s = IntakeSession(graph, rules, language=rec.language, token=rec.token)
    s.created_at = datetime.fromisoformat(rec.createdAt)
    for nid in recompute_path(graph, rec.answers).path:
        if nid in rec.answers:
            s.answer(nid, rec.answers[nid])
    s.consent_at = datetime.fromisoformat(rec.consent.timestamp) if rec.consent.timestamp else None
    s.assigned_doctor = rec.assignedDoctor
    s.timeline = list(rec.timeline)
    if rec.finishedAt:
        s.finished_at = datetime.fromisoformat(rec.finishedAt)
    return s


def build_for_save(s: IntakeSession, complete: bool = False) -> PatientRecord:
    """The record to save for a kiosk session. Mirrors the old Streamlit kiosk page: during the quiz the prior record's doctor/staff
    fields survive (records.build does that); on finish, staff vitals are kept and doctor edits cleared. Staff-attached scans
    (timeline, pendingScans) and the queue fields are owned by the API and always carried over."""
    prior = store.load(s.token)
    if complete:
        rec = s.finish()
        rec = rec.model_copy(update={"doctorEdits": {}, "editedFields": [], "vitals": prior.vitals if prior else None})
        if prior is not None:   # Streamlit dropped these on finish; a doctor may already have worked on an unfinished patient
            rec = rec.model_copy(update={"doctorNotes": prior.doctorNotes, "dosingChecks": prior.dosingChecks,
                                         "visitHistory": prior.visitHistory, "visitHistoryBy": prior.visitHistoryBy,
                                         "visitHistoryAt": prior.visitHistoryAt})
    else:
        rec = s.to_record(complete=False, prior=prior)
    if prior is not None:
        rec = rec.model_copy(update={"timeline": prior.timeline or rec.timeline, "pendingScans": prior.pendingScans,
                                     "queueNumber": prior.queueNumber, "queueDate": prior.queueDate, "finishedAt": prior.finishedAt,
                                     "patientId": prior.patientId, "identifierType": prior.identifierType,
                                     "identifierMasked": prior.identifierMasked, "returning": prior.returning, "kioskScans": prior.kioskScans})
    ident = getattr(s, "identity", None)          # set by POST .../bind; covers the first save, before a prior record exists
    if ident:
        rec = rec.model_copy(update=ident)
    return rec
