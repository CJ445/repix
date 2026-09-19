"""Engine tests against the real pinned ONNX models.

Skipped automatically if model weights haven't been downloaded
(see models/download_models.sh) to keep the rest of the suite runnable
without a network fetch.
"""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

MODELS_DIR = Path(__file__).resolve().parents[2] / "models"
DDCOLOR_PATH = MODELS_DIR / "ddcolor" / "ddcolor_large.onnx"
X2_PATH = MODELS_DIR / "realesrgan" / "realesrgan_x2plus.onnx"
X4_PATH = MODELS_DIR / "realesrgan" / "realesrgan_x4plus.onnx"

pytestmark = pytest.mark.skipif(
    not (DDCOLOR_PATH.exists() and X2_PATH.exists() and X4_PATH.exists()),
    reason="ONNX model weights not present; run models/download_models.sh",
)


def _sample_image(w=180, h=140) -> Image.Image:
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[:, :, 0] = np.linspace(0, 255, w, dtype=np.uint8)[None, :]
    arr[:, :, 1] = np.linspace(0, 255, h, dtype=np.uint8)[:, None]
    return Image.fromarray(arr, mode="RGB")


def test_ddcolor_loads_and_colorizes():
    from app.engines.colorization.ddcolor import DDColorEngine

    engine = DDColorEngine(str(DDCOLOR_PATH))
    image = _sample_image()
    result = engine.colorize(image)

    assert result.size == image.size
    assert result.mode == "RGB"
    arr = np.array(result)
    assert not np.isnan(arr.astype(np.float32)).any()
    assert arr.dtype == np.uint8


def test_realesrgan_x2_exact_dimensions():
    from app.engines.upscaling.realesrgan import RealESRGANEngine

    engine = RealESRGANEngine(str(X2_PATH), str(X4_PATH), tile_size=512, tile_overlap=16)
    image = _sample_image(120, 90)
    result = engine.upscale(image, 2)

    assert result.size == (240, 180)
    arr = np.array(result)
    assert not np.isnan(arr.astype(np.float32)).any()


def test_realesrgan_x4_exact_dimensions():
    from app.engines.upscaling.realesrgan import RealESRGANEngine

    engine = RealESRGANEngine(str(X2_PATH), str(X4_PATH), tile_size=512, tile_overlap=16)
    image = _sample_image(120, 90)
    result = engine.upscale(image, 4)

    assert result.size == (480, 360)


def test_realesrgan_tiling_matches_untiled_dimensions():
    """A large image forces the tiled code path; output size must still be exact."""
    from app.engines.upscaling.realesrgan import RealESRGANEngine

    engine = RealESRGANEngine(str(X2_PATH), str(X4_PATH), tile_size=64, tile_overlap=8)
    image = _sample_image(200, 150)
    result = engine.upscale(image, 2)

    assert result.size == (400, 300)
    arr = np.array(result)
    assert not np.isnan(arr.astype(np.float32)).any()


def test_realesrgan_invalid_scale_rejected():
    from app.engines.upscaling.realesrgan import RealESRGANEngine

    engine = RealESRGANEngine(str(X2_PATH), str(X4_PATH))
    with pytest.raises(ValueError):
        engine.upscale(_sample_image(50, 50), 3)


def test_upscale_reports_tile_progress():
    from app.engines.upscaling.realesrgan import RealESRGANEngine

    engine = RealESRGANEngine(str(X2_PATH), str(X4_PATH), tile_size=64, tile_overlap=8)
    seen: list[float] = []
    engine.upscale(_sample_image(130, 70), 2, progress=seen.append)
    assert len(seen) == 3 * 2  # ceil(130/64) x ceil(70/64) tiles
    assert seen == sorted(seen) and seen[-1] == 1.0
