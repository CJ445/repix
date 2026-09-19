import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.api.routes import register_limiter, router
from app.core.config import Settings
from app.engines.base import ColorizationEngine, UpscalingEngine
from app.jobs.manager import JobManager


class FakeColorizationEngine(ColorizationEngine):
    def colorize(self, image):
        return image.convert("RGB")


class FakeUpscalingEngine(UpscalingEngine):
    def upscale(self, image, scale, cancel_check=None, progress=None):
        w, h = image.size
        return image.resize((w * scale, h * scale))


def build_app(settings: Settings) -> FastAPI:
    app = FastAPI()
    register_limiter(app)
    app.include_router(router)
    app.state.models_loaded = True
    app.state.job_manager = JobManager(settings, FakeColorizationEngine(), FakeUpscalingEngine())
    return app


@pytest.fixture
def client(tmp_path):
    settings = Settings(temp_root=str(tmp_path), rate_limit_per_minute=1000)
    app = build_app(settings)
    with TestClient(app) as c:
        yield c
    app.state.job_manager.shutdown()


def _png_file(w=40, h=30):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (5, 6, 7)).save(buf, format="PNG")
    buf.seek(0)
    return buf


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_ready(client):
    res = client.get("/ready")
    assert res.status_code == 200


def test_create_job_and_poll_to_completion(client):
    res = client.post(
        "/api/jobs",
        files={"file": ("test.png", _png_file(), "image/png")},
        data={"operation": "colorize"},
    )
    assert res.status_code == 200
    job_id = res.json()["job_id"]

    import time

    for _ in range(50):
        status_res = client.get(f"/api/jobs/{job_id}")
        body = status_res.json()
        if body["status"] == "completed":
            break
        time.sleep(0.05)
    assert body["status"] == "completed"
    assert body["download_url"]


def test_upscale_job_dimensions(client):
    res = client.post(
        "/api/jobs",
        files={"file": ("test.png", _png_file(40, 30), "image/png")},
        data={"operation": "upscale", "options": '{"scale": 4}'},
    )
    job_id = res.json()["job_id"]

    import time

    for _ in range(50):
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["status"] == "completed":
            break
        time.sleep(0.05)
    assert body["status"] == "completed"

    download = client.get(f"/api/jobs/{job_id}/download")
    assert download.status_code == 200
    img = Image.open(io.BytesIO(download.content))
    assert img.size == (160, 120)


def test_invalid_operation_rejected(client):
    res = client.post(
        "/api/jobs",
        files={"file": ("test.png", _png_file(), "image/png")},
        data={"operation": "sharpen"},
    )
    assert res.status_code == 400


def test_invalid_scale_rejected(client):
    res = client.post(
        "/api/jobs",
        files={"file": ("test.png", _png_file(), "image/png")},
        data={"operation": "upscale", "options": '{"scale": 3}'},
    )
    assert res.status_code == 400


def test_malformed_image_rejected(client):
    res = client.post(
        "/api/jobs",
        files={"file": ("test.png", io.BytesIO(b"garbage"), "image/png")},
        data={"operation": "colorize"},
    )
    assert res.status_code == 400


def test_get_nonexistent_job_returns_404(client):
    res = client.get("/api/jobs/does-not-exist")
    assert res.status_code == 404


def test_download_nonexistent_job_returns_404(client):
    res = client.get("/api/jobs/does-not-exist/download")
    assert res.status_code == 404


def test_cannot_download_before_completion(client):
    res = client.post(
        "/api/jobs",
        files={"file": ("test.png", _png_file(200, 200), "image/png")},
        data={"operation": "upscale", "options": '{"scale": 4}'},
    )
    job_id = res.json()["job_id"]
    download = client.get(f"/api/jobs/{job_id}/download")
    assert download.status_code in (404, 409)


def test_delete_job_removes_it(client):
    res = client.post(
        "/api/jobs",
        files={"file": ("test.png", _png_file(), "image/png")},
        data={"operation": "colorize"},
    )
    job_id = res.json()["job_id"]
    del_res = client.delete(f"/api/jobs/{job_id}")
    assert del_res.status_code == 200


def test_job_ids_are_not_sequential(client):
    ids = []
    for _ in range(3):
        res = client.post(
            "/api/jobs",
            files={"file": ("test.png", _png_file(), "image/png")},
            data={"operation": "colorize"},
        )
        ids.append(res.json()["job_id"])
    assert len(set(ids)) == 3
    for job_id in ids:
        assert len(job_id) >= 32


def test_busy_server_returns_503_with_retry_after(tmp_path):
    import threading

    from app.api.routes import limiter

    limiter.reset()  # the module-level limiter is shared across tests
    release = threading.Event()

    class SlowColorizer(ColorizationEngine):
        def colorize(self, image):
            release.wait(timeout=10)
            return image.convert("RGB")

    settings = Settings(
        temp_root=str(tmp_path), rate_limit_per_minute=1000, max_ai_workers=1, max_queue_size=0
    )
    app = build_app(settings)
    app.state.job_manager.shutdown()
    app.state.job_manager = JobManager(settings, SlowColorizer(), FakeUpscalingEngine())
    buf = io.BytesIO()
    Image.new("RGB", (20, 20)).save(buf, format="PNG")
    try:
        with TestClient(app) as c:
            files = {"file": ("a.png", buf.getvalue(), "image/png")}
            first = c.post("/api/jobs", files=files, data={"operation": "colorize"})
            assert first.status_code == 200
            busy = c.post("/api/jobs", files=files, data={"operation": "colorize"})
            assert busy.status_code == 503
            assert busy.headers["retry-after"]
    finally:
        release.set()
        app.state.job_manager.shutdown()
