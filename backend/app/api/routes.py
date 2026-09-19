import json
import logging

from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import Settings, get_settings
from app.jobs.manager import JobError, JobManager, QueueFullError
from app.models.job import JobStatus, Operation
from app.schemas.jobs import JobOptions, JobResponse

logger = logging.getLogger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


def get_job_manager(request: Request) -> JobManager:
    return request.app.state.job_manager


def to_response(job, request: Request) -> JobResponse:
    manager: JobManager = request.app.state.job_manager
    download_url = None
    if job.status == JobStatus.COMPLETED:
        download_url = f"/api/jobs/{job.id}/download"
    return JobResponse(
        job_id=job.id,
        status=job.status,
        operation=job.operation,
        scale=job.scale,
        queue_position=manager.queue_position(job),
        progress=job.progress if job.status == JobStatus.PROCESSING else None,
        download_url=download_url,
        error_message=job.error_message if job.status == JobStatus.FAILED else None,
    )


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/ready")
def ready(request: Request):
    manager: JobManager = request.app.state.job_manager
    models_ok = request.app.state.models_loaded
    if not models_ok:
        raise HTTPException(status_code=503, detail="Models are not loaded yet.")
    return {"status": "ok"}


@router.post("/api/jobs", response_model=JobResponse)
@limiter.limit("10/minute")
async def create_job(
    request: Request,
    file: UploadFile = File(...),
    operation: str = Form(...),
    options: str | None = Form(default=None),
    settings: Settings = Depends(get_settings),
    manager: JobManager = Depends(get_job_manager),
):
    try:
        op = Operation(operation)
    except ValueError:
        raise HTTPException(status_code=400, detail="Unknown operation.")

    parsed_options = JobOptions()
    if options:
        try:
            parsed_options = JobOptions(**json.loads(options))
        except (json.JSONDecodeError, TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid options.")

    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {settings.max_upload_mb} MB.",
        )
    if not data:
        raise HTTPException(status_code=400, detail="No file was uploaded.")

    try:
        job = manager.create_job(operation=op, file_bytes=data, scale=parsed_options.scale)
    except QueueFullError as exc:
        raise HTTPException(status_code=503, detail=str(exc), headers={"Retry-After": "30"})
    except JobError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return to_response(job, request)


@router.get("/api/jobs/{job_id}", response_model=JobResponse, name="get_job")
def get_job(job_id: str, request: Request, manager: JobManager = Depends(get_job_manager)):
    job = manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return to_response(job, request)


@router.get("/api/jobs/{job_id}/download", name="download_job")
def download_job(job_id: str, manager: JobManager = Depends(get_job_manager)):
    job = manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status != JobStatus.COMPLETED or job.output_path is None or not job.output_path.exists():
        raise HTTPException(status_code=409, detail="This result isn't ready or has expired.")
    return FileResponse(job.output_path, media_type=job.output_mime or "image/png")


@router.delete("/api/jobs/{job_id}")
def delete_job(job_id: str, manager: JobManager = Depends(get_job_manager)):
    manager.cancel_job(job_id)
    return {"status": "deleted"}


def register_limiter(app: FastAPI) -> None:
    app.state.limiter = limiter
