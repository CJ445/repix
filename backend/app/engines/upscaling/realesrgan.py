from __future__ import annotations

import logging
import math

import numpy as np
import onnxruntime as ort
from PIL import Image

from app.engines.ort_options import build_session_options
from app.engines.base import CancelCheck, ProgressCallback, UpscalingEngine

logger = logging.getLogger(__name__)


class CancelledError(Exception):
    pass


class RealESRGANEngine(UpscalingEngine):
    """Real-ESRGAN 2x/4x upscaling backed by ONNX Runtime (CPUExecutionProvider, FP32).

    Large images are processed in overlapping tiles to bound peak memory
    usage; each output tile is cropped back to its non-overlapping region
    before being pasted into the final canvas, which avoids visible seams
    without needing feather blending.
    """

    def __init__(
        self,
        x2_model_path: str,
        x4_model_path: str,
        tile_size: int = 512,
        tile_overlap: int = 16,
        num_threads: int = 0,
    ):
        options = build_session_options(num_threads)
        self._sessions: dict[int, ort.InferenceSession] = {
            2: ort.InferenceSession(x2_model_path, sess_options=options, providers=["CPUExecutionProvider"]),
            4: ort.InferenceSession(x4_model_path, sess_options=options, providers=["CPUExecutionProvider"]),
        }
        self._input_names = {
            scale: session.get_inputs()[0].name for scale, session in self._sessions.items()
        }
        self.tile_size = tile_size
        self.tile_overlap = tile_overlap
        logger.info("Real-ESRGAN x2/x4 models loaded (tile=%d overlap=%d)", tile_size, tile_overlap)

    def upscale(
        self,
        image: Image.Image,
        scale: int,
        cancel_check: CancelCheck | None = None,
        progress: ProgressCallback | None = None,
    ) -> Image.Image:
        if scale not in (2, 4):
            raise ValueError("scale must be 2 or 4")

        rgb = np.array(image.convert("RGB"), dtype=np.float32) / 255.0
        height, width = rgb.shape[:2]
        session = self._sessions[scale]
        input_name = self._input_names[scale]

        if max(height, width) <= self.tile_size:
            output = self._run_tile(session, input_name, rgb)
        else:
            output = self._tiled_inference(session, input_name, rgb, scale, cancel_check, progress)

        output = np.clip(output * 255.0, 0, 255).round().astype(np.uint8)
        result = Image.fromarray(output, mode="RGB")

        expected_w, expected_h = width * scale, height * scale
        if result.size != (expected_w, expected_h):
            result = result.resize((expected_w, expected_h), Image.LANCZOS)
        return result

    def _run_tile(self, session: ort.InferenceSession, input_name: str, tile_rgb: np.ndarray) -> np.ndarray:
        tensor = tile_rgb.transpose(2, 0, 1)[np.newaxis].astype(np.float32)
        output = session.run(None, {input_name: tensor})[0]
        return output[0].transpose(1, 2, 0)

    def _tiled_inference(
        self,
        session: ort.InferenceSession,
        input_name: str,
        rgb: np.ndarray,
        scale: int,
        cancel_check: CancelCheck | None,
        progress: ProgressCallback | None = None,
    ) -> np.ndarray:
        height, width = rgb.shape[:2]
        overlap = self.tile_overlap
        step = self.tile_size

        out_h, out_w = height * scale, width * scale
        output = np.zeros((out_h, out_w, 3), dtype=np.float32)

        tiles_x = math.ceil(width / step)
        tiles_y = math.ceil(height / step)
        total_tiles = tiles_x * tiles_y
        done_tiles = 0

        for ty in range(tiles_y):
            for tx in range(tiles_x):
                if cancel_check and cancel_check():
                    raise CancelledError()

                x0 = tx * step
                y0 = ty * step
                x1 = min(x0 + step, width)
                y1 = min(y0 + step, height)

                px0 = max(x0 - overlap, 0)
                py0 = max(y0 - overlap, 0)
                px1 = min(x1 + overlap, width)
                py1 = min(y1 + overlap, height)

                tile = rgb[py0:py1, px0:px1, :]
                tile_out = self._run_tile(session, input_name, tile)

                # Offset of the requested (non-overlapping) region within the padded tile.
                left_pad = (x0 - px0) * scale
                top_pad = (y0 - py0) * scale
                region_w = (x1 - x0) * scale
                region_h = (y1 - y0) * scale

                cropped = tile_out[top_pad : top_pad + region_h, left_pad : left_pad + region_w, :]
                output[y0 * scale : y1 * scale, x0 * scale : x1 * scale, :] = cropped

                done_tiles += 1
                if progress:
                    progress(done_tiles / total_tiles)

        return output
