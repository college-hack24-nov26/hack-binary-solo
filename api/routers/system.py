import os

from fastapi import APIRouter, Depends

from dosing import ENGINE_VERSION
from intake import offline
from ocr import service as ocr_service

from ..deps import formulary_status, staff_or_doctor
from ..schemas import Health, OfflineStatus, SystemConfig

router = APIRouter(prefix="/api/system", tags=["system"])


def opd_minutes() -> int:
    try:
        return max(1, int(os.environ.get("OPD_MINUTES_PER_PATIENT", "10")))
    except ValueError:
        return 10


@router.get("/health", response_model=Health)
def health():
    ok, _ = formulary_status()
    return {"ok": True, "engineVersion": ENGINE_VERSION, "formularyLoaded": ok}


@router.get("/config", response_model=SystemConfig)
def config():
    ok, err = formulary_status()
    try:
        h = ocr_service.health()
        ocr_ok = bool(h.get("ollamaUp") and h.get("modelPresent"))
    except Exception:  # noqa: BLE001 - a bad OLLAMA_URL means OCR is unavailable, nothing more
        ocr_ok = False
    return {"demoMode": offline.demo_mode(), "languages": ["en", "hi", "mr"], "ocrAvailable": ocr_ok, "formularyLoaded": ok,
            "formularyError": err, "strict": offline.strict(), "opdMinutesPerPatient": opd_minutes()}


@router.get("/offline-status", response_model=OfflineStatus, dependencies=[Depends(staff_or_doctor)])
def offline_status():
    st = offline.status()
    level, text = offline.headline(st)
    p = offline.probe_config()
    return {"level": level, "headline": text, "strict": st["strict"], "localModel": st["local_model"], "services": st["services"],
            "internet": st["internet"], "probe": {"host": p.host, "port": p.port, "timeoutS": p.timeout_s, "intervalS": p.interval_s}}
