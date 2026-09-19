"""Build the two CANDIDATE upscalers used in the optimisation comparison (not part of the shipped stack).

  int8        Real-ESRGAN x4plus, static INT8 QDQ quantisation (ONNX Runtime), per-channel weights,
              calibrated on held-out images (not the evaluation photos). conv_first and the whole
              upsampling head stay FP32, as recommended for SR networks.
  general_v3  realesr-general-x4v3 (SRVGGNetCompact, PReLU, PixelShuffle-free nearest residual),
              exported from the official checkpoint to ONNX with dynamic H/W.

Host:      python build_candidates.py --work DIR      (launches capped, network-less containers)
Container: python build_candidates.py --inside int8|general
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

SKIP_NODES = ["/conv_first/Conv", "/conv_up1/Conv", "/conv_up2/Conv", "/conv_hr/Conv", "/conv_last/Conv"]


def inside_int8():
    import numpy as np
    from onnxruntime.quantization import CalibrationDataReader, CalibrationMethod, QuantFormat, QuantType, quantize_static
    from PIL import Image

    import shutil

    # quantize_static writes a shape-inferred temp file next to its input; /app/models is read-only, so copy first.
    src = "/work/candidates/realesrgan_x4plus_src.onnx"
    shutil.copy("/app/models/realesrgan/realesrgan_x4plus.onnx", src)
    dst = "/work/candidates/realesrgan_x4plus_int8_qdq.onnx"
    # Few, small images: ORT's calibrator memory grows with (images x calibrated tensors x pixels).
    files = [Path(f"/work/imgs/calib/{n}.png") for n in ("brick_clean", "grass_degraded", "gravel_clean", "rocket_degraded")]
    assert files, "no calibration images"

    class Reader(CalibrationDataReader):
        def __init__(self):
            self.it = iter([np.array(Image.open(f).convert("RGB"), dtype=np.float32)[:96, :96].transpose(2, 0, 1)[None] / 255.0 for f in files])

        def get_next(self):
            x = next(self.it, None)
            return None if x is None else {"input": x}

    import onnxruntime as ort
    name = ort.InferenceSession(src, providers=["CPUExecutionProvider"]).get_inputs()[0].name
    Reader.get_next = lambda self, _n=name: (lambda x: None if x is None else {_n: x})(next(self.it, None))
    quantize_static(src, dst, Reader(), quant_format=QuantFormat.QDQ, per_channel=True,
                    activation_type=QuantType.QUInt8, weight_type=QuantType.QInt8,
                    calibrate_method=CalibrationMethod.MinMax, nodes_to_exclude=SKIP_NODES, op_types_to_quantize=["Conv"],
                    extra_options={"ActivationSymmetric": False, "WeightSymmetric": True})
    print("int8 model:", dst, Path(dst).stat().st_size // 2**20, "MiB from", len(files), "calibration images")


def inside_general():
    import numpy as np
    import onnxruntime as ort
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    class SRVGGNetCompact(nn.Module):
        def __init__(self, num_in_ch=3, num_out_ch=3, num_feat=64, num_conv=32, upscale=4):
            super().__init__()
            self.upscale = upscale
            self.body = nn.ModuleList([nn.Conv2d(num_in_ch, num_feat, 3, 1, 1), nn.PReLU(num_parameters=num_feat)])
            for _ in range(num_conv):
                self.body.append(nn.Conv2d(num_feat, num_feat, 3, 1, 1))
                self.body.append(nn.PReLU(num_parameters=num_feat))
            self.body.append(nn.Conv2d(num_feat, num_out_ch * upscale * upscale, 3, 1, 1))
            self.upsampler = nn.PixelShuffle(upscale)

        def forward(self, x):
            out = x
            for layer in self.body:
                out = layer(out)
            return self.upsampler(out) + F.interpolate(x, scale_factor=self.upscale, mode="nearest")

    model = SRVGGNetCompact()
    ck = torch.load("/work/candidates/realesr-general-x4v3.pth", map_location="cpu", weights_only=True)
    model.load_state_dict(ck["params"] if "params" in ck else ck, strict=True)
    model.eval()
    dst = "/work/candidates/realesr_general_x4v3.onnx"
    dummy = torch.rand(1, 3, 64, 64)
    torch.onnx.export(model, dummy, dst, input_names=["input"], output_names=["output"], opset_version=17, dynamo=False,
                      dynamic_axes={"input": {2: "h", 3: "w"}, "output": {2: "H", 3: "W"}})
    # Verify the export against PyTorch on a non-square, non-64 size.
    x = torch.rand(1, 3, 50, 70)
    with torch.no_grad():
        ref = model(x).numpy()
    sess = ort.InferenceSession(dst, providers=["CPUExecutionProvider"])
    got = sess.run(None, {"input": x.numpy()})[0]
    print("general_v3 export max|onnx - torch| =", float(np.abs(ref - got).max()), "shape", got.shape,
          "params", sum(p.numel() for p in model.parameters()))


def launch(work: Path, which: str):
    from run_benchmarks import IMAGE, REPO, SPEC_CPUSET, preflight

    preflight(2, 4)
    pp = {"int8": "/work/pylibs:/app", "general": "/work/pylibs:/work/torchlibs:/app"}[which]
    cmd = ["docker", "run", "--rm", "--name", f"build_{which}", "--no-healthcheck", "--cpus=2", "--memory=4g", "--memory-swap=4g",
           "--pids-limit=256", "--network=none", "--cap-drop=ALL", "--security-opt=no-new-privileges", f"--cpuset-cpus={SPEC_CPUSET}",
           f"--user={os.getuid()}:{os.getgid()}", "-e", "HOME=/tmp", "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", f"PYTHONPATH={pp}",
           "-v", f"{REPO / 'models'}:/app/models:ro", "-v", f"{REPO / 'benchmarks'}:/bench:ro", "-v", f"{work}:/work",
           "--entrypoint", "python", "-w", "/app", IMAGE, "/bench/build_candidates.py", "--inside", which]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    print(f"[build {which}] exit {r.returncode}\n{r.stdout[-600:]}{r.stderr[-900:] if r.returncode else ''}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path)
    ap.add_argument("--inside", choices=["int8", "general"])
    a = ap.parse_args()
    if a.inside:
        {"int8": inside_int8, "general": inside_general}[a.inside]()
    else:
        sys.path.insert(0, str(Path(__file__).parent))
        for w in ("general", "int8"):
            launch(a.work.resolve(), w)
