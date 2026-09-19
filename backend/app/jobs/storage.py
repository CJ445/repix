from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def ensure_root(temp_root: str) -> Path:
    root = Path(temp_root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def make_job_dir(temp_root: str, job_id: str) -> Path:
    root = ensure_root(temp_root)
    job_dir = root / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def delete_job_dir(job_dir: Path | None) -> None:
    if job_dir is None:
        return
    try:
        shutil.rmtree(job_dir, ignore_errors=True)
    except OSError:
        logger.warning("Failed to remove temporary job directory %s", job_dir)
