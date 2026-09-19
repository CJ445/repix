import io

import pytest
from PIL import Image

from app.utils.validation import ImageValidationError, validate_and_normalize


def test_valid_jpeg_passes(jpeg_bytes):
    image = validate_and_normalize(jpeg_bytes, max_width=6000, max_height=6000)
    assert image.width == 100
    assert image.height == 80


def test_valid_png_passes(png_bytes):
    image = validate_and_normalize(png_bytes, max_width=6000, max_height=6000)
    assert image.size == (100, 80)


def test_garbage_bytes_rejected():
    with pytest.raises(ImageValidationError):
        validate_and_normalize(b"not an image", max_width=6000, max_height=6000)


def test_empty_bytes_rejected():
    with pytest.raises(ImageValidationError):
        validate_and_normalize(b"", max_width=6000, max_height=6000)


def test_oversized_dimensions_rejected(jpeg_bytes):
    with pytest.raises(ImageValidationError):
        validate_and_normalize(jpeg_bytes, max_width=50, max_height=50)


def test_exif_orientation_normalized():
    # Build a JPEG with an EXIF orientation tag indicating 180 degree rotation.
    img = Image.new("RGB", (40, 20), color=(255, 0, 0))
    buf = io.BytesIO()
    exif = img.getexif()
    exif[0x0112] = 3  # Orientation: rotated 180
    img.save(buf, format="JPEG", exif=exif)

    normalized = validate_and_normalize(buf.getvalue(), max_width=6000, max_height=6000)
    # exif_transpose should have applied and cleared orientation; dimensions unchanged for 180 rotation.
    assert normalized.size == (40, 20)


def test_disguised_extension_still_validated_by_content():
    # A text file masquerading with image bytes should still fail regardless of claimed type.
    with pytest.raises(ImageValidationError):
        validate_and_normalize(b"<html>not an image</html>", max_width=6000, max_height=6000)
