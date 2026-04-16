from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from config import settings
from logging_config import get_logger

log = get_logger(__name__)


def _ensure_temp_dir() -> Path:
    path = Path(settings.temp_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


@asynccontextmanager
async def managed_tempfile(task_id: str, suffix: str = "") -> AsyncIterator[Path]:
    path = _ensure_temp_dir() / f"{task_id}{suffix}"
    try:
        yield path
    finally:
        _safe_remove(path)


def _safe_remove(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError as e:
        log.warning("temp_file_remove_failed", path=str(path), error=str(e))


def cleanup_stale_files(task_id: str) -> None:
    temp_dir = Path(settings.temp_dir)
    if not temp_dir.exists():
        return
    for path in temp_dir.glob(f"{task_id}*"):
        _safe_remove(path)
