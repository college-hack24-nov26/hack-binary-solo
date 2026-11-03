"""Settings from environment (optionally a local .env). Nothing here leaves localhost."""
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _load_dotenv() -> None:
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


@dataclass(frozen=True)
class Settings:
    model: str
    ollama_url: str
    max_edge: int
    keep_alive: str
    session_ttl_s: int
    tmp_dir: Path
    review_threshold: float
    fallback: str | None
    timeout_s: int = 300


def load_settings() -> Settings:
    _load_dotenv()
    e = os.environ
    s = Settings(
        model=e.get("OCR_MODEL", "qwen3-vl:8b-instruct"),
        ollama_url=e.get("OLLAMA_URL", "http://localhost:11434").rstrip("/"),
        max_edge=int(e.get("OCR_MAX_EDGE", "1400")),
        keep_alive=e.get("OCR_KEEP_ALIVE", "30m"),
        session_ttl_s=int(e.get("OCR_SESSION_TTL_S", "900")),
        tmp_dir=(ROOT / e.get("OCR_TMP_DIR", "./tmp/ocr")).resolve(),
        review_threshold=float(e.get("OCR_REVIEW_THRESHOLD", "0.7")),
        fallback=e.get("OCR_FALLBACK") or None,
    )
    host = urlparse(s.ollama_url).hostname
    if host not in _LOCAL_HOSTS:
        raise ValueError(f"OLLAMA_URL must be localhost (offline-only), got host {host!r}")
    return s
