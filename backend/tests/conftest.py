import io
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def make_jpeg_bytes(width: int = 100, height: int = 80) -> bytes:
    img = Image.new("RGB", (width, height), color=(120, 80, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def make_png_bytes(width: int = 100, height: int = 80, mode: str = "RGB") -> bytes:
    img = Image.new(mode, (width, height), color=(10, 20, 30) if mode == "RGB" else (10, 20, 30, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def jpeg_bytes():
    return make_jpeg_bytes()


@pytest.fixture
def png_bytes():
    return make_png_bytes()
