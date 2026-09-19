"""Build ground-truth test pairs for the quality comparison.

High-res image (HR) -> area-downsampled low-res input (LR). The model sees only LR and its
output is compared to the known HR. Two LR flavours: "clean" (pure downsample) and
"degraded" (light Gaussian noise + JPEG q=50, the kind of damage Real-ESRGAN targets).
Colorization inputs are luminance-only versions of colour photos, so the truth is known.

Sample images are scikit-image's bundled test set: astronaut (NASA, public domain) and
coffee / chelsea (CC0).
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

work = Path(sys.argv[1])
imgs = work / "imgs"
q = imgs / "q"
q.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(20260919)


def degrade(lr: np.ndarray) -> np.ndarray:
    noisy = np.clip(lr.astype(np.float32) + rng.normal(0, 2.0, lr.shape), 0, 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(noisy).save(buf, "JPEG", quality=50)
    return np.array(Image.open(buf).convert("RGB"))


manifest = []
for name in ("astronaut", "coffee", "chelsea"):
    hr = np.array(Image.open(imgs / f"{name}.png").convert("RGB"))
    h, w = (hr.shape[0] // 4) * 4, (hr.shape[1] // 4) * 4
    hr = hr[:h, :w]
    Image.fromarray(hr).save(q / f"{name}_hr.png")

    for s in (4, 2):
        lr = cv2.resize(hr, (w // s, h // s), interpolation=cv2.INTER_AREA)
        Image.fromarray(lr).save(q / f"{name}_lr_x{s}.png")
        manifest.append({"id": f"{name}_clean_x{s}", "task": f"upscale{s}", "input": f"/work/imgs/q/{name}_lr_x{s}.png",
                         "save": f"/work/imgs/q/{name}_sr_clean_x{s}.png"})
    lr = degrade(cv2.resize(hr, (w // 4, h // 4), interpolation=cv2.INTER_AREA))
    Image.fromarray(lr).save(q / f"{name}_lr_x4_degraded.png")
    manifest.append({"id": f"{name}_degraded_x4", "task": "upscale4", "input": f"/work/imgs/q/{name}_lr_x4_degraded.png",
                     "save": f"/work/imgs/q/{name}_sr_degraded_x4.png"})

    Image.fromarray(hr).convert("L").save(q / f"{name}_gray.png")
    manifest.append({"id": f"{name}_colorize", "task": "colorize", "input": f"/work/imgs/q/{name}_gray.png",
                     "save": f"/work/imgs/q/{name}_colorized.png"})

# Production-style showcase (no ground truth): the original is fed as-is, exactly like a user upload.
manifest.append({"id": "showcase_astronaut_x4", "task": "upscale4", "input": "/work/imgs/astronaut.png",
                 "save": "/work/imgs/q/showcase_astronaut_x4.png"})
manifest.append({"id": "showcase_coffee_x2", "task": "upscale2", "input": "/work/imgs/coffee.png",
                 "save": "/work/imgs/q/showcase_coffee_x2.png"})

# A real black-and-white photo already used as this project's manual test image (no ground truth).
flower = Path.home() / "Downloads" / "bw-flower.jpg"
if flower.exists():
    Image.open(flower).convert("RGB").save(q / "bw_flower.png")
    manifest.append({"id": "bw_flower_colorize", "task": "colorize", "input": "/work/imgs/q/bw_flower.png",
                     "save": "/work/imgs/q/bw_flower_colorized.png"})

(work / "quality_manifest.json").write_text(json.dumps(manifest, indent=1))
print(len(manifest), "quality jobs")
