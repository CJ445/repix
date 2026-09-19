from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.job import JobStatus, Operation


class JobOptions(BaseModel):
    scale: int | None = Field(default=None, description="Upscale factor: 2 or 4")
    output_format: str | None = Field(default=None, description="png | jpeg | webp")


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    operation: Operation | None = None
    scale: int | None = None
    queue_position: int | None = None
    progress: float | None = None
    download_url: str | None = None
    error_message: str | None = None

    model_config = {"use_enum_values": True}
