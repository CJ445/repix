from __future__ import annotations

import io

from PIL import Image, ImageOps, UnidentifiedImageError

SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP"}


class ImageValidationError(Exception):
    """Raised when uploaded content fails validation. Message is user-safe."""


def validate_and_normalize(
    data: bytes,
    max_width: int,
    max_height: int,
) -> Image.Image:
    """Decode, validate, and orientation-normalize an uploaded image.

    Never trusts filename or client-supplied MIME type; inspects actual
    decoded content.
    """
    try:
        image = Image.open(io.BytesIO(data))
        image.verify()
    except (UnidentifiedImageError, OSError, ValueError):
        raise ImageValidationError("This file isn't a valid image.")

    # Pillow requires re-opening after verify() before it can be used.
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError, ValueError):
        raise ImageValidationError("This file isn't a valid image.")

    fmt = (image.format or "").upper()
    if fmt not in SUPPORTED_FORMATS:
        raise ImageValidationError("Unsupported image format. Please use JPEG, PNG, or WebP.")

    # Normalize EXIF orientation exactly once so all downstream consumers
    # (preview, crop, AI processing, output) agree on pixel orientation.
    image = ImageOps.exif_transpose(image)
    if image is None:
        raise ImageValidationError("This file isn't a valid image.")

    if image.width > max_width or image.height > max_height:
        raise ImageValidationError(
            f"Image dimensions exceed the maximum of {max_width}x{max_height} px."
        )
    if image.width < 1 or image.height < 1:
        raise ImageValidationError("This file isn't a valid image.")

    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "A" in image.getbands() else "RGB")

    return image
