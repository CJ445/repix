from __future__ import annotations

import io
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

from app.core.config import Settings
from app.engines.base import ColorizationEngine, UpscalingEngine
from app.engines.upscaling.realesrgan import CancelledError
from app.jobs import storage
from app.models.job import Job, JobStatus, Operation
from app.utils.validation import ImageValidationError, validate_and_normalize

logger = logging.getLogger(__name__)


class JobError(Exception):
    """User-facing error raised during job creation (bad request)."""


class JobManager:
    def __init__(
        self,
        settings: Settings,
        colorization_engine: ColorizationEngine | None,
        upscaling_engine: UpscalingEngine | None,
    ):
        self._settings = settings
        self._colorization_engine = colorization_engine
        self._upscaling_engine = upscaling_engine
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max(1, settings.max_ai_workers))
        self._stop_event = threading.Event()
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def shutdown(self) -> None:
        self._stop_event.set()
        self._executor.shutdown(wait=False, cancel_futures=True)

    # -- Job lifecycle -----------------------------------------------------

    def create_job(
        self,
        *,
        operation: Operation,
        file_bytes: bytes,
        scale: int | None = None,
    ) -> Job:
        if operation == Operation.UPSCALE:
            if self._upscaling_engine is None:
                raise JobError("Upscaling isn't available right now. Please try again later.")
            if scale not in (2, 4):
                raise JobError("Choose either 2x or 4x upscaling.")
        elif operation == Operation.COLORIZE:
            if self._colorization_engine is None:
                raise JobError("Colorization isn't available right now. Please try again later.")

        try:
            image = validate_and_normalize(
                file_bytes,
                self._settings.max_input_width,
                self._settings.max_input_height,
            )
        except ImageValidationError as exc:
            raise JobError(str(exc)) from exc

        if operation == Operation.UPSCALE and scale is not None:
            out_w, out_h = image.width * scale, image.height * scale
            if (
                out_w > self._settings.max_output_width
                or out_h > self._settings.max_output_height
                or out_w * out_h > self._settings.max_output_pixels
            ):
                raise JobError(
                    "This image is too large for that upscale factor. "
                    "Try a smaller image or a lower scale."
                )

        job = Job(
            operation=operation,
            scale=scale,
            ttl_seconds=self._settings.job_ttl_minutes * 60,
            input_width=image.width,
            input_height=image.height,
        )
        job.job_dir = storage.make_job_dir(self._settings.temp_root, job.id)
        job.input_path = job.job_dir / "input.png"
        image.save(job.input_path, format="PNG")

        with self._lock:
            self._jobs[job.id] = job

        self._executor.submit(self._process_job, job.id)
        return job

    def get_job(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel_job(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            job.cancel_requested = True
            if job.status == JobStatus.QUEUED:
                job.status = JobStatus.CANCELLED
                job.touch()
        storage.delete_job_dir(job.job_dir)
        return True

    # -- Worker --------------------------------------------------------

    def _process_job(self, job_id: str) -> None:
        job = self.get_job(job_id)
        if job is None or job.cancel_requested:
            return

        start = time.monotonic()
        with self._lock:
            job.status = JobStatus.PROCESSING
            job.touch()

        try:
            try:
                image = Image.open(job.input_path)
                image.load()
            except (FileNotFoundError, OSError):
                if job.cancel_requested:
                    self._mark_cancelled(job)
                    return
                raise

            if job.cancel_requested:
                self._mark_cancelled(job)
                return

            if job.operation == Operation.COLORIZE:
                result = self._colorization_engine.colorize(image)  # type: ignore[union-attr]
            else:
                result = self._upscaling_engine.upscale(  # type: ignore[union-attr]
                    image, job.scale or 2, cancel_check=lambda: job.cancel_requested
                )

            has_alpha = result.mode == "RGBA"
            out_format = "PNG" if has_alpha else "PNG"
            buffer = io.BytesIO()
            result.save(buffer, format=out_format)
            buffer.seek(0)

            output_path = job.job_dir / "output.png"  # type: ignore[operator]
            output_path.write_bytes(buffer.getvalue())

            with self._lock:
                job.output_path = output_path
                job.output_mime = "image/png"
                job.output_width = result.width
                job.output_height = result.height
                job.status = JobStatus.COMPLETED
                job.touch()

            duration = time.monotonic() - start
            logger.info(
                "job completed job_id=%s operation=%s scale=%s in=%dx%d out=%dx%d duration=%.2fs",
                job.id,
                job.operation.value,
                job.scale,
                job.input_width,
                job.input_height,
                job.output_width,
                job.output_height,
                duration,
            )
        except CancelledError:
            self._mark_cancelled(job)
        except Exception:
            logger.exception("job failed job_id=%s operation=%s", job.id, job.operation.value)
            with self._lock:
                job.status = JobStatus.FAILED
                job.error_message = "We couldn't process this image. Please try a smaller image or try again."
                job.touch()

    def _mark_cancelled(self, job: Job) -> None:
        with self._lock:
            job.status = JobStatus.CANCELLED
            job.touch()
        storage.delete_job_dir(job.job_dir)

    # -- Cleanup ---------------------------------------------------------

    def _cleanup_loop(self) -> None:
        while not self._stop_event.wait(30):
            self._cleanup_once()

    def _cleanup_once(self) -> None:
        now = time.time()
        expired_ids: list[str] = []
        with self._lock:
            for job_id, job in self._jobs.items():
                if job.is_expired(now) and job.status not in (JobStatus.EXPIRED,):
                    expired_ids.append(job_id)

        for job_id in expired_ids:
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    continue
                job.status = JobStatus.EXPIRED
                job.cancel_requested = True
                job.touch()
            storage.delete_job_dir(job.job_dir)
            logger.info("job expired job_id=%s", job_id)

        # Drop bookkeeping for very old expired jobs to bound memory use.
        cutoff = now - 24 * 3600
        with self._lock:
            stale = [jid for jid, j in self._jobs.items() if j.updated_at < cutoff]
            for jid in stale:
                del self._jobs[jid]
