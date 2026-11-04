"""Kiosk scan jobs: the patient's photo goes through the existing local OCR (ocr.service.extract) on a background thread.

Status lives on the visit record (`kioskScans`) so it survives a page reload; live progress (stage, streamed token count) lives in
memory. One worker: the local model handles one image at a time. The OCR function is injectable (`app.state.ocr_fn`) so tests use
a fake backend. Text read here is patient-supplied and UNVERIFIED; nothing in this module touches dosing."""
import io
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Callable, Optional

from PIL import Image, ImageFilter, ImageStat

from ocr import service as ocr_service
from ocr import session as ocr_session
from ocr.config import load_settings
from ocr.imageprep import prepare_image
from records import identity_audit, scanfiles, store

from .deps import WRITE_LOCK

RUNNING = ("queued", "preparing", "reading", "structuring")
EXPECTED_TOKENS = 500          # a typical structured reply; progress is capped at 92 % until the reply really ends
BLUR_MIN, DARK_MAX = 600.0, 70.0      # calibrated on fixtures/: clean pages score ~1800+ edge variance, a 3 px blur ~450


class Live:
    __slots__ = ("stage", "tokens", "started")

    def __init__(self):
        self.stage, self.tokens, self.started = "queued", 0, time.time()


LIVE: dict[str, Live] = {}
_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kiosk-ocr")


def quality(jpeg: bytes) -> Optional[str]:
    """None if the picture looks readable, else 'dark' or 'blurry' (checked before spending a minute on the model)."""
    im = Image.open(io.BytesIO(jpeg)).convert("L")
    im.thumbnail((700, 700))
    if ImageStat.Stat(im).mean[0] < DARK_MAX:
        return "dark"
    if ImageStat.Stat(im.filter(ImageFilter.FIND_EDGES)).var[0] < BLUR_MIN:
        return "blurry"
    return None


def progress_of(entry: dict) -> tuple[str, float, float]:
    """(stage, 0..1, elapsed seconds) from the real stage and the streamed token count."""
    st = entry["status"]
    live = LIVE.get(entry["id"])
    el = round(time.time() - live.started, 1) if live and st in RUNNING else float(entry.get("elapsedS", 0))
    if st not in RUNNING:
        return st, 1.0 if st == "done" else 0.0, el
    if live is None:
        return st, 0.0, el
    base = {"queued": 0.02, "preparing": 0.08, "reading": 0.12, "structuring": 0.95}[live.stage]
    if live.stage == "reading":
        base = min(0.92, 0.12 + 0.8 * live.tokens / EXPECTED_TOKENS)
    return live.stage, round(base, 3), el


def _field(value, conf, threshold):
    return {"value": value or None, "confidence": conf, "check": bool(value) and conf is not None and conf < threshold}


def to_entry_fields(result: dict, threshold: float) -> dict:
    meds = []
    for m in result["medications"]:
        c = m.get("confidence")
        meds.append({"name": _field(m.get("nameAsWritten"), c, threshold),
                     "dose": {**_field(m.get("strength"), c, threshold), "check": (not m.get("strength")) or (c is not None and c < threshold)},
                     "frequency": {**_field(m.get("frequencyAsWritten"), c, threshold), "check": (not m.get("frequencyAsWritten")) or (c is not None and c < threshold)}})
    lines = [" ".join(x for x in (r.get("test"), r.get("value"), r.get("unit")) if x) for r in result["labResults"]]
    free = "\n".join(lines + list(result.get("diagnosesAsWritten") or []))
    dt = result["documentType"]
    return {"docType": dt if dt in ("prescription", "lab_report") else "other", "docDate": _field(result.get("documentDate"), None, threshold),
            "medicines": meds, "freeText": free}


def _update(token: str, sid: str, **fields) -> None:
    with WRITE_LOCK:
        rec = store.load(token)
        if rec is None:
            return
        scans = [({**s, **fields} if s["id"] == sid else s) for s in rec.kioskScans]
        store.save(rec.model_copy(update={"kioskScans": scans}))


def _run(token: str, sid: str, raw: bytes, ocr_fn: Callable, publish) -> None:
    live = LIVE[sid]
    s = load_settings()

    def prog(stage, n):
        live.stage, live.tokens = stage, n

    try:
        live.stage = "preparing"
        r = ocr_fn(raw, True, "kiosk", s, progress=prog)
        if not r["ok"]:
            _update(token, sid, status="failed", message="read_failed", elapsedS=round(time.time() - live.started, 1))
            return
        if r.get("sessionId"):
            ocr_session.delete(s.tmp_dir, r["sessionId"])              # the kiosk keeps its own copy under data_local/scans
        _update(token, sid, status="done", elapsedS=round(time.time() - live.started, 1), **to_entry_fields(r["result"], s.review_threshold))
        with WRITE_LOCK:
            identity_audit.write("scan.read", actor="kiosk", token=token, scan=sid, count=len(r["result"]["medications"]))
    except Exception:  # noqa: BLE001 - any failure must end the job so the tablet never waits forever; no content is logged
        _update(token, sid, status="failed", message="read_failed", elapsedS=round(time.time() - live.started, 1))
    finally:
        LIVE.pop(sid, None)
        publish()


def submit(app, token: str, raw: bytes, publish) -> dict:
    """Store the (EXIF-stripped, resized) picture, check quality and availability, then queue the OCR job. Returns the entry."""
    s = load_settings()
    sid = scanfiles.new_id()
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    entry = {"id": sid, "uploadedAt": now, "status": "queued", "docType": None, "docDate": {"value": None, "confidence": None, "check": False},
             "medicines": [], "freeText": "", "confirmed": False, "imageKept": True, "message": None, "patientEdited": False, "elapsedS": 0.0,
             "usedBy": None}
    try:
        jpeg = prepare_image(raw, s.max_edge)
    except ValueError:
        return {**entry, "status": "failed", "message": "unreadable_file", "imageKept": False, "_transient": True}
    bad = quality(jpeg)
    if bad:
        return {**entry, "status": "retake", "message": bad, "imageKept": False, "_transient": True}      # nothing is stored for a bad picture
    scanfiles.write(sid, jpeg)
    try:
        h = ocr_service.health(s)
        up = bool(h.get("ollamaUp") and h.get("modelPresent")) if app.state.ocr_fn is ocr_service.extract else True
    except ValueError:
        up = False
    if not up:
        entry.update(status="unavailable", message="model_down")
    with WRITE_LOCK:
        rec = store.load(token)
        store.save(rec.model_copy(update={"kioskScans": rec.kioskScans + [entry]}))
        identity_audit.write("scan.created", actor="kiosk", token=token, scan=sid)
    if entry["status"] == "queued":
        LIVE[sid] = Live()
        _POOL.submit(_run, token, sid, jpeg, app.state.ocr_fn, lambda: app.state.events.publish("patient.updated", {"token": token}))
    return entry
