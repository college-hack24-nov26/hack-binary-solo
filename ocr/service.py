"""The OCR service API (what POST /api/ocr/extract and GET /api/ocr/health do).
Streamlit calls these functions directly; they are framework-free so they can be put
behind a REST route later."""
import json
import logging
import time

from pydantic import ValidationError

from . import ollama_client, session
from .config import Settings, load_settings
from .imageprep import prepare_image
from .postprocess import enrich
from .prompt import RETRY_SUFFIX, SYSTEM_PROMPT, USER_PROMPT
from .schema import RawExtraction, vlm_json_schema

log = logging.getLogger("ocr")  # log ids, sizes, latency only, never content
ALLOWED_ROLES = {"doctor", "staff", "kiosk"}   # "kiosk": the patient scanning their own papers (api/scan_jobs.py)


class OcrRefused(Exception):
    pass


def health(s: Settings | None = None) -> dict:
    return ollama_client.health(s or load_settings())


def extract(image_bytes: bytes, consent: bool, role: str, s: Settings | None = None) -> dict:
    s = s or load_settings()
    if role not in ALLOWED_ROLES:
        raise OcrRefused("role not permitted")
    if consent is not True:
        raise OcrRefused("explicit patient consent required")
    t0 = time.time()
    try:
        jpeg = prepare_image(image_bytes, s.max_edge)
    except ValueError as e:
        return _fail(str(e))

    schema = vlm_json_schema()
    raw, last_err, attempts = None, "", 0
    for attempt in range(2):  # first try + one retry
        attempts += 1
        user = USER_PROMPT + (RETRY_SUFFIX if attempt else "")
        try:
            content = ollama_client.chat_json(s, SYSTEM_PROMPT, user, jpeg, schema)
            raw = RawExtraction.model_validate(json.loads(content))
            break
        except ollama_client.OllamaError as e:
            last_err = f"model call failed ({e})"
        except (json.JSONDecodeError, ValidationError):
            last_err = "model output failed schema validation"
    if raw is None:
        log.warning("extract failed after %d attempts: %s", attempts, last_err)
        return _fail(last_err)

    result = enrich(raw, s.review_threshold)
    sid = session.create(s.tmp_dir, jpeg)
    latency = round(time.time() - t0, 2)
    log.info("extract ok session=%s meds=%d labs=%d attempts=%d latency=%.1fs",
             sid, len(result["medications"]), len(result["labResults"]), attempts, latency)
    return {"ok": True, "sessionId": sid, "result": result, "latencyS": latency, "attempts": attempts}


def _fail(msg: str) -> dict:
    return {"ok": False, "error": msg, "needsManualEntry": True}
