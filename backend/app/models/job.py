from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class Operation(str, Enum):
    COLORIZE = "colorize"
    UPSCALE = "upscale"


@dataclass
class Job:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    token: str = field(default_factory=lambda: uuid.uuid4().hex)
    operation: Operation = Operation.COLORIZE
    scale: int | None = None
    status: JobStatus = JobStatus.QUEUED
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    ttl_seconds: int = 3600
    job_dir: Path | None = None
    input_path: Path | None = None
    output_path: Path | None = None
    output_mime: str | None = None
    input_width: int | None = None
    input_height: int | None = None
    output_width: int | None = None
    output_height: int | None = None
    error_message: str | None = None
    cancel_requested: bool = False

    @property
    def expires_at(self) -> float:
        return self.created_at + self.ttl_seconds

    def is_expired(self, now: float | None = None) -> bool:
        return (now or time.time()) > self.expires_at

    def touch(self) -> None:
        self.updated_at = time.time()
