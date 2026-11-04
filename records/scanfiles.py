"""Original scan images the patient took at the kiosk: `<data>/scans/<random id>.jpg`, mode 0600. File names are random ids,
never a name, token or number. The folder is inside the gitignored data folder."""
import os
import re
import secrets
from pathlib import Path
from typing import Optional

from . import store

ID_RE = re.compile(r"^[0-9a-f]{16}$")


def folder() -> Path:
    d = store.data_dir().parent / "scans"
    d.mkdir(parents=True, exist_ok=True)
    return d


def new_id() -> str:
    return secrets.token_hex(8)


def _p(sid: str) -> Path:
    if not ID_RE.match(sid):
        raise ValueError("bad scan id")
    return folder() / f"{sid}.jpg"


def write(sid: str, jpeg: bytes) -> None:
    p = _p(sid)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(jpeg)


def read(sid: str) -> Optional[bytes]:
    try:
        p = _p(sid)
    except ValueError:
        return None
    return p.read_bytes() if p.exists() else None


def delete(sid: str) -> None:
    try:
        _p(sid).unlink(missing_ok=True)
    except ValueError:
        pass
