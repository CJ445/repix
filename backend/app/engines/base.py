from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from PIL import Image

CancelCheck = Callable[[], bool]


class ColorizationEngine(ABC):
    @abstractmethod
    def colorize(self, image: Image.Image) -> Image.Image:
        """Return a new color image derived from the input image."""


class UpscalingEngine(ABC):
    @abstractmethod
    def upscale(
        self,
        image: Image.Image,
        scale: int,
        cancel_check: CancelCheck | None = None,
    ) -> Image.Image:
        """Return an image scaled by exactly `scale`x (2 or 4)."""
