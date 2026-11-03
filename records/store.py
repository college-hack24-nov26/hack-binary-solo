"""Local JSON storage. Default folder is gitignored; override with INTAKE_DATA_DIR."""
import os
import re
from pathlib import Path
from typing import Optional

from intake.models import ROOT

from .schema import PatientRecord

TOKEN_RE = re.compile(r"^PT-[A-Z2-7]{6}$")


def data_dir() -> Path:
    d = Path(os.environ.get("INTAKE_DATA_DIR", ROOT / "data_local")).resolve() / "records"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path(token: str, base: Optional[Path]) -> Path:
    if not TOKEN_RE.match(token):
        raise ValueError(f"bad token {token!r}")
    return (base or data_dir()) / f"{token}.json"


def save(rec: PatientRecord, base: Optional[Path] = None) -> Path:
    p = _path(rec.token, base)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(rec.model_dump_json(indent=1), encoding="utf-8")
    os.replace(tmp, p)
    return p


def load(token: str, base: Optional[Path] = None) -> Optional[PatientRecord]:
    p = _path(token, base)
    return PatientRecord.model_validate_json(p.read_text(encoding="utf-8")) if p.exists() else None


def delete(token: str, base: Optional[Path] = None) -> None:
    _path(token, base).unlink(missing_ok=True)


def list_records(base: Optional[Path] = None) -> list[PatientRecord]:
    d = base or data_dir()
    out = []
    for f in sorted(d.glob("PT-*.json")):
        try:
            out.append(PatientRecord.model_validate_json(f.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001 - a half-written or foreign file must not break the staff page
            continue
    return out
