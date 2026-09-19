import math
import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def available_cpus() -> int:
    """CPUs this process may actually use, honouring Docker/cgroup CPU limits.

    `os.cpu_count()` reports the host's cores, so an ONNX Runtime pool sized from it
    would spin up far more threads than a `cpus: 2` container is allowed to run.
    """
    limit = os.cpu_count() or 1
    if hasattr(os, "sched_getaffinity"):
        limit = min(limit, len(os.sched_getaffinity(0)))

    try:  # cgroup v2
        quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()[:2]
        if quota != "max":
            limit = min(limit, math.ceil(int(quota) / int(period)))
    except (OSError, ValueError):
        try:  # cgroup v1
            quota = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").read_text())
            period = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read_text())
            if quota > 0:
                limit = min(limit, math.ceil(quota / period))
        except (OSError, ValueError):
            pass
    return max(1, limit)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"

    max_upload_mb: int = 20
    max_input_width: int = 6000
    max_input_height: int = 6000

    max_output_width: int = 10000
    max_output_height: int = 10000
    max_output_pixels: int = 50_000_000

    job_ttl_minutes: int = 60
    max_ai_workers: int = 1
    # Jobs allowed to wait behind the running ones; beyond this new jobs are refused.
    max_queue_size: int = 5
    # ONNX Runtime / OpenCV threads per job. 0 = auto (the container's CPU limit).
    ai_threads: int = 0
    poll_interval_ms: int = 1500

    upscale_tile_size: int = 256
    upscale_tile_overlap: int = 16

    rate_limit_per_minute: int = 10

    temp_root: str = "/tmp/image-lab"

    models_dir: str = "/app/models"

    @property
    def effective_ai_threads(self) -> int:
        return self.ai_threads if self.ai_threads > 0 else available_cpus()

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
