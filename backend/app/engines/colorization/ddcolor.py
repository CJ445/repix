from __future__ import annotations

import logging

import cv2
import numpy as np
import onnxruntime as ort
from PIL import Image

from app.engines.ort_options import build_session_options
from app.engines.base import ColorizationEngine

logger = logging.getLogger(__name__)

INPUT_SIZE = 512


class DDColorEngine(ColorizationEngine):
    """DDColor-Tiny colorization backed by ONNX Runtime (CPUExecutionProvider, FP32)."""

    def __init__(self, model_path: str, num_threads: int = 0):
        options = build_session_options(num_threads)
        self._session = ort.InferenceSession(
            model_path, sess_options=options, providers=["CPUExecutionProvider"]
        )
        self._input_name = self._session.get_inputs()[0].name
        logger.info("DDColor-Tiny model loaded from %s", model_path)

    def colorize(self, image: Image.Image) -> Image.Image:
        rgb = np.array(image.convert("RGB"), dtype=np.float32) / 255.0
        height, width = rgb.shape[:2]

        orig_l = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)[:, :, :1]

        resized = cv2.resize(rgb, (INPUT_SIZE, INPUT_SIZE), interpolation=cv2.INTER_LINEAR)
        resized_l = cv2.cvtColor(resized, cv2.COLOR_RGB2LAB)[:, :, :1]
        gray_lab = np.concatenate(
            [resized_l, np.zeros_like(resized_l), np.zeros_like(resized_l)], axis=-1
        )
        gray_rgb = cv2.cvtColor(gray_lab, cv2.COLOR_LAB2RGB)

        tensor = gray_rgb.transpose(2, 0, 1)[np.newaxis].astype(np.float32)
        output_ab = self._session.run(None, {self._input_name: tensor})[0]

        output_ab = output_ab[0].transpose(1, 2, 0)
        output_ab_resized = cv2.resize(output_ab, (width, height), interpolation=cv2.INTER_LINEAR)

        output_lab = np.concatenate([orig_l, output_ab_resized], axis=-1).astype(np.float32)
        output_rgb = cv2.cvtColor(output_lab, cv2.COLOR_LAB2RGB)
        output_rgb = np.clip(output_rgb * 255.0, 0, 255).round().astype(np.uint8)

        return Image.fromarray(output_rgb, mode="RGB")
