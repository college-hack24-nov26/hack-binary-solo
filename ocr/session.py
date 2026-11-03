"""Short-lived review sessions. The (resized) image lives in the temp folder only until
confirm / cancel / timeout; the folder is purged at startup. Nothing here is logged."""
import secrets
import shutil
import time
from pathlib import Path

_purged: set[Path] = set()


def purge_tmp(tmp_dir: Path) -> None:
    if tmp_dir in _purged:
        return
    shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    _purged.add(tmp_dir)


def create(tmp_dir: Path, image_jpeg: bytes) -> str:
    purge_tmp(tmp_dir)
    sid = secrets.token_hex(8)
    (tmp_dir / f"{sid}.jpg").write_bytes(image_jpeg)
    return sid


def read(tmp_dir: Path, sid: str) -> bytes | None:
    p = tmp_dir / f"{sid}.jpg"
    return p.read_bytes() if p.exists() else None


def delete(tmp_dir: Path, sid: str) -> None:
    (tmp_dir / f"{sid}.jpg").unlink(missing_ok=True)


def sweep(tmp_dir: Path, ttl_s: int) -> int:
    """Delete images older than ttl. Called on every UI rerun."""
    n = 0
    now = time.time()
    for p in tmp_dir.glob("*.jpg"):
        if now - p.stat().st_mtime > ttl_s:
            p.unlink(missing_ok=True)
            n += 1
    return n
