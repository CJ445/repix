from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import cv2
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.routes import register_limiter, router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.engines.colorization.ddcolor import DDColorEngine
from app.engines.upscaling.realesrgan import RealESRGANEngine
from app.jobs.manager import JobManager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)

    threads = settings.effective_ai_threads
    cv2.setNumThreads(threads)
    logger.info(
        "AI limits: threads=%d workers=%d queue=%d", threads, settings.max_ai_workers, settings.max_queue_size
    )

    models_dir = Path(settings.models_dir)
    ddcolor_path = models_dir / "ddcolor" / "ddcolor_large.onnx"
    x2_path = models_dir / "realesrgan" / "realesrgan_x2plus.onnx"
    x4_path = models_dir / "realesrgan" / "realesrgan_x4plus.onnx"

    colorization_engine = None
    upscaling_engine = None
    models_loaded = False

    try:
        if ddcolor_path.exists():
            colorization_engine = DDColorEngine(str(ddcolor_path), num_threads=threads)
        if x2_path.exists() and x4_path.exists():
            upscaling_engine = RealESRGANEngine(
                str(x2_path),
                str(x4_path),
                tile_size=settings.upscale_tile_size,
                tile_overlap=settings.upscale_tile_overlap,
                num_threads=threads,
            )
        models_loaded = colorization_engine is not None and upscaling_engine is not None
    except Exception:
        logger.exception("Failed to load one or more AI models")

    if not models_loaded:
        logger.warning(
            "Starting without all AI models loaded. Run models/download_models.sh "
            "and restart to enable colorize/upscale."
        )

    app.state.models_loaded = models_loaded
    app.state.job_manager = JobManager(settings, colorization_engine, upscaling_engine)

    yield

    app.state.job_manager.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(title="Repix API", lifespan=lifespan)

    register_limiter(app)
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    return app


app = create_app()
