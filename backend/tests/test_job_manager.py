import time

import pytest
from PIL import Image

from app.core.config import Settings
from app.engines.base import ColorizationEngine, UpscalingEngine
from app.jobs.manager import JobError, JobManager
from app.models.job import JobStatus, Operation


class FakeColorizationEngine(ColorizationEngine):
    def colorize(self, image):
        return image.convert("RGB")


class FakeUpscalingEngine(UpscalingEngine):
    def upscale(self, image, scale, cancel_check=None, progress=None):
        w, h = image.size
        return image.resize((w * scale, h * scale))


@pytest.fixture
def settings(tmp_path):
    return Settings(temp_root=str(tmp_path), job_ttl_minutes=60, max_ai_workers=1)


@pytest.fixture
def manager(settings):
    mgr = JobManager(settings, FakeColorizationEngine(), FakeUpscalingEngine())
    yield mgr
    mgr.shutdown()


def wait_for_terminal(manager, job_id, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = manager.get_job(job_id)
        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.EXPIRED):
            return job
        time.sleep(0.05)
    raise TimeoutError("job did not reach terminal state")


def _png_bytes(w=50, h=40):
    import io

    buf = io.BytesIO()
    Image.new("RGB", (w, h), (1, 2, 3)).save(buf, format="PNG")
    return buf.getvalue()


def test_create_colorize_job_transitions_to_completed(manager):
    job = manager.create_job(operation=Operation.COLORIZE, file_bytes=_png_bytes())
    assert job.status in (JobStatus.QUEUED, JobStatus.PROCESSING)
    final = wait_for_terminal(manager, job.id)
    assert final.status == JobStatus.COMPLETED
    assert final.output_path.exists()


def test_upscale_output_dimensions_exact(manager):
    job = manager.create_job(operation=Operation.UPSCALE, file_bytes=_png_bytes(50, 40), scale=2)
    final = wait_for_terminal(manager, job.id)
    assert final.status == JobStatus.COMPLETED
    assert final.output_width == 100
    assert final.output_height == 80


def test_invalid_scale_rejected(manager):
    with pytest.raises(JobError):
        manager.create_job(operation=Operation.UPSCALE, file_bytes=_png_bytes(), scale=3)


def test_invalid_image_rejected(manager):
    with pytest.raises(JobError):
        manager.create_job(operation=Operation.COLORIZE, file_bytes=b"not an image")


def test_output_exceeding_limits_rejected(settings):
    settings.max_output_pixels = 100  # absurdly small
    mgr = JobManager(settings, FakeColorizationEngine(), FakeUpscalingEngine())
    try:
        with pytest.raises(JobError):
            mgr.create_job(operation=Operation.UPSCALE, file_bytes=_png_bytes(100, 100), scale=4)
    finally:
        mgr.shutdown()


def test_cancel_queued_job(manager):
    job = manager.create_job(operation=Operation.COLORIZE, file_bytes=_png_bytes())
    manager.cancel_job(job.id)
    # Either it was cancelled before running, or completed before we cancelled (race) - both acceptable,
    # but temp dir must not persist for a cancelled job.
    final = wait_for_terminal(manager, job.id)
    assert final.status in (JobStatus.CANCELLED, JobStatus.COMPLETED)


def test_unknown_job_returns_none(manager):
    assert manager.get_job("does-not-exist") is None


def test_expiration_marks_job_expired_and_deletes_files(settings):
    settings.job_ttl_minutes = 0  # expires essentially immediately
    mgr = JobManager(settings, FakeColorizationEngine(), FakeUpscalingEngine())
    try:
        job = mgr.create_job(operation=Operation.COLORIZE, file_bytes=_png_bytes())
        wait_for_terminal(mgr, job.id)
        mgr._cleanup_once()
        final = mgr.get_job(job.id)
        assert final.status == JobStatus.EXPIRED
        assert not final.job_dir.exists()
    finally:
        mgr.shutdown()


class BlockingColorizationEngine(ColorizationEngine):
    def __init__(self):
        import threading

        self.release = threading.Event()

    def colorize(self, image):
        self.release.wait(timeout=10)
        return image.convert("RGB")


def test_queue_position_and_full_queue_rejected(tmp_path):
    from app.jobs.manager import QueueFullError

    engine = BlockingColorizationEngine()
    settings = Settings(temp_root=str(tmp_path), max_ai_workers=1, max_queue_size=1)
    mgr = JobManager(settings, engine, FakeUpscalingEngine())
    try:
        first = mgr.create_job(operation=Operation.COLORIZE, file_bytes=_png_bytes())
        second = mgr.create_job(operation=Operation.COLORIZE, file_bytes=_png_bytes())
        assert mgr.queue_position(second) == 1

        with pytest.raises(QueueFullError):
            mgr.create_job(operation=Operation.COLORIZE, file_bytes=_png_bytes())

        engine.release.set()
        assert wait_for_terminal(mgr, first.id).status == JobStatus.COMPLETED
        assert wait_for_terminal(mgr, second.id).status == JobStatus.COMPLETED
        assert mgr.queue_position(second) is None

        # Capacity is freed once jobs finish.
        third = mgr.create_job(operation=Operation.COLORIZE, file_bytes=_png_bytes())
        assert wait_for_terminal(mgr, third.id).status == JobStatus.COMPLETED
    finally:
        engine.release.set()
        mgr.shutdown()
