"""Benchmark worker: runs INSIDE a resource-capped container (see run_benchmarks.py).

It drives the app's real engine classes (app.engines.*) so the numbers describe the
production code path. Alongside wall-clock time it records what the kernel's cgroup says
the container actually consumed, which is the evidence that the caps held.

Variants (--variant) switch ONE optimisation at a time, without touching app code:
  prod                shipped configuration
  ort_default         stock ONNX Runtime options (arena, mem-pattern, spinning, auto threads)
  arena_on            shipped, but CPU memory arena + mem-pattern ON
  spin_on             shipped, but thread spinning ON
  opt_basic           shipped, but graph optimisation level BASIC (no NCHWc layout transform)
  thread_env          shipped + cv2/OpenMP/BLAS thread counts pinned to the CPU quota
  fixed_tiles         shipped ORT options, but every tile has the SAME shape (edge tiles are
                      shifted inward instead of shrunk) + uint8 output canvas
  fixed_arena         fixed_tiles + arena/mem-pattern ON (constant shapes make the arena safe)
  fixed_arena_shrink  fixed_arena + per-run arena shrinkage (returns memory to the OS)
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import os
import platform
import re
import resource
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
from PIL import Image

from app.core.config import available_cpus
from app.engines import ort_options

CG = Path("/sys/fs/cgroup")

VARIANTS = {
    "prod": dict(ort="prod"),
    "ort_default": dict(ort="default"),
    "arena_on": dict(ort="arena"),
    "spin_on": dict(ort="spin"),
    "thread_env": dict(ort="prod", cv2_threads=True),
    "opt_basic": dict(ort="basic"),
    "fixed_tiles": dict(ort="prod", fixed=True),
    "fixed_arena": dict(ort="arena", fixed=True),
    "fixed_arena_shrink": dict(ort="arena", fixed=True, shrink=True),
}


def _read(name: str) -> str:
    try:
        return (CG / name).read_text().strip()
    except OSError:
        return ""


def cpu_stat() -> dict[str, int]:
    out = {}
    for line in _read("cpu.stat").splitlines():
        k, v = line.split()
        out[k] = int(v)
    return out


class MemSampler(threading.Thread):
    """Samples cgroup memory.current so each job gets its own peak (memory.peak is per-container)."""

    def __init__(self, interval: float = 0.02):
        super().__init__(daemon=True)
        self.interval, self.peak, self._halt = interval, 0, threading.Event()

    def run(self):
        while not self._halt.is_set():
            try:
                self.peak = max(self.peak, int(_read("memory.current") or 0))
            except ValueError:
                pass
            time.sleep(self.interval)

    def stop(self) -> int:
        self._halt.set()
        self.join()
        return self.peak


def make_options_factory(kind: str, threads: int):
    def factory(num_threads: int = 0) -> ort.SessionOptions:
        n = num_threads or threads
        o = ort.SessionOptions()
        if kind == "default":  # stock ORT
            return o
        o.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        o.inter_op_num_threads = 1
        o.intra_op_num_threads = n
        if kind == "arena":  # arena + mem-pattern stay at their defaults (ON), spinning off
            o.add_session_config_entry("session.intra_op.allow_spinning", "0")
        elif kind == "basic":  # shipped settings, but graph optimisation BASIC (skips the NCHWc layout transform)
            o.add_session_config_entry("session.intra_op.allow_spinning", "0")
            o.enable_cpu_mem_arena = False
            o.enable_mem_pattern = False
            o.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
        elif kind == "spin":  # spinning left at its default (ON), arena/mem-pattern off
            o.enable_cpu_mem_arena = False
            o.enable_mem_pattern = False
        else:
            raise ValueError(kind)
        return o

    return factory


def patch_options(kind: str, threads: int) -> None:
    if kind == "prod":
        return
    factory = make_options_factory(kind, threads)
    import app.engines.colorization.ddcolor as dd
    import app.engines.upscaling.realesrgan as re_

    ort_options.build_session_options = dd.build_session_options = re_.build_session_options = factory


def build_engine_class(fixed: bool, shrink: bool):
    from app.engines.upscaling.realesrgan import RealESRGANEngine

    if not fixed:
        return RealESRGANEngine

    class FixedTileEngine(RealESRGANEngine):
        """Every tile has the same (T+2o)^2 input shape, so ORT never re-plans or re-allocates;
        edge tiles are shifted inward (some pixels recomputed) instead of shrunk."""

        def _run_tile(self, session, input_name, tile_rgb):
            tensor = tile_rgb.transpose(2, 0, 1)[np.newaxis].astype(np.float32)
            if shrink:
                ro = ort.RunOptions()
                ro.add_run_config_entry("memory.enable_memory_arena_shrinkage", "cpu:0")
                out = session.run(None, {input_name: tensor}, ro)[0]
            else:
                out = session.run(None, {input_name: tensor})[0]
            return out[0].transpose(1, 2, 0)

        def upscale(self, image, scale, cancel_check=None, progress=None):
            rgb = np.array(image.convert("RGB"), dtype=np.float32) / 255.0
            H, W = rgb.shape[:2]
            session, name = self._sessions[scale], self._input_names[scale]
            if max(H, W) <= self.tile_size:
                out = self._run_tile(session, name, rgb)
                return Image.fromarray(np.clip(out * 255.0, 0, 255).round().astype(np.uint8), mode="RGB")
            T, o = self.tile_size, self.tile_overlap
            S = T + 2 * o
            canvas = np.zeros((H * scale, W * scale, 3), dtype=np.uint8)
            nx, ny = math.ceil(W / T), math.ceil(H / T)
            for ty in range(ny):
                for tx in range(nx):
                    x0, y0 = tx * T, ty * T
                    x1, y1 = min(x0 + T, W), min(y0 + T, H)
                    wx0, wy0 = min(max(x0 - o, 0), max(W - S, 0)), min(max(y0 - o, 0), max(H - S, 0))
                    wx1, wy1 = min(wx0 + S, W), min(wy0 + S, H)
                    t_out = self._run_tile(session, name, rgb[wy0:wy1, wx0:wx1])
                    crop = t_out[(y0 - wy0) * scale:(y1 - wy0) * scale, (x0 - wx0) * scale:(x1 - wx0) * scale]
                    canvas[y0 * scale:y1 * scale, x0 * scale:x1 * scale] = np.clip(crop * 255.0, 0, 255).round().astype(np.uint8)
            return Image.fromarray(canvas, mode="RGB")

    return FixedTileEngine


def load_image(job: dict) -> Image.Image:
    img = Image.open(job["input"]).convert("RGB")
    if job.get("resize"):
        img = img.resize(tuple(job["resize"]), Image.LANCZOS)
    if job.get("gray"):
        img = img.convert("L").convert("RGB")
    return img


def profile_tile(model_path: str, threads: int, tile: int, src: str, out_dir: Path) -> dict:
    """Per-op time for ONE tile of the x4 model (ONNX Runtime's own profiler)."""
    out_dir.mkdir(exist_ok=True)
    o = ort_options.build_session_options(threads)
    o.enable_profiling = True
    o.profile_file_prefix = str(out_dir / "prof")
    sess = ort.InferenceSession(model_path, sess_options=o, providers=["CPUExecutionProvider"])
    img = np.array(Image.open(src).convert("RGB").resize((tile, tile), Image.LANCZOS), dtype=np.float32) / 255.0
    x = img.transpose(2, 0, 1)[np.newaxis]
    name = sess.get_inputs()[0].name
    sess.run(None, {name: x})  # warm-up (not profiled separately; included in file, so profile 2nd run only)
    t0 = time.perf_counter()
    sess.run(None, {name: x})
    wall = time.perf_counter() - t0
    events = json.loads(Path(sess.end_profiling()).read_text())
    kernel = [e for e in events if e.get("cat") == "Node" and e["name"].endswith("_kernel_time")]
    # Two runs are in the file; keep the second half of every node's events.
    per_node = collections.defaultdict(list)
    for e in kernel:
        per_node[e["name"]].append(e)
    rows = []
    for nm, evs in per_node.items():
        e = evs[-1]
        rows.append((nm.replace("_kernel_time", ""), e["args"].get("op_name", "?"), e["dur"] / 1e6))
    total = sum(r[2] for r in rows)
    by_op = collections.defaultdict(float)
    # ORT fuses Conv+LeakyReLU and renames nodes after the fused output, so classify by name pattern:
    # tail = the x2/x4 upsampling head (lrelu, lrelu_1, lrelu_2 = after conv_up1/conv_up2/conv_hr, Resize, final conv).
    tail_re = re.compile(r"^/(lrelu(_\d+)?/|Resize|conv_(up\d|hr|last)/)|^output")
    reorder = tail = trunk = 0.0
    for nm, op, d in rows:
        by_op[op] += d
        if op.startswith("Reorder"):
            reorder += d
        elif tail_re.match(nm):
            tail += d
        else:
            trunk += d
    tail_conv, trunk_conv = tail, trunk
    return {
        "tile": tile, "wall_s": wall, "sum_kernel_s": total, "by_op_s": dict(sorted(by_op.items(), key=lambda kv: -kv[1])[:8]),
        "trunk_s": trunk_conv, "tail_s": tail_conv, "layout_reorder_s": reorder,
        "top_nodes": [(n, d) for n, _, d in sorted(rows, key=lambda r: -r[2])[:6]],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--variant", default="prod", choices=sorted(VARIANTS))
    ap.add_argument("--tile", type=int, default=256)
    ap.add_argument("--overlap", type=int, default=16)
    ap.add_argument("--models", default="/app/models")
    ap.add_argument("--x4-model")
    ap.add_argument("--x2-model")
    args = ap.parse_args()

    v = VARIANTS[args.variant]
    jobs = json.loads(Path(args.jobs).read_text())
    threads = available_cpus()  # what the app itself would pick (honours cgroup quota and cpuset)
    patch_options(v["ort"], threads)
    if v.get("cv2_threads"):
        cv2.setNumThreads(threads)

    from app.engines.colorization.ddcolor import DDColorEngine

    m = Path(args.models)
    x2 = args.x2_model or str(m / "realesrgan/realesrgan_x2plus.onnx")
    x4 = args.x4_model or str(m / "realesrgan/realesrgan_x4plus.onnx")
    tasks = {j["task"] for j in jobs}
    engines: dict[str, object] = {}
    load_s: dict[str, float] = {}
    if "colorize" in tasks:
        t = time.perf_counter()
        engines["colorize"] = DDColorEngine(str(m / "ddcolor/ddcolor_tiny.onnx"), num_threads=threads)
        load_s["colorize"] = time.perf_counter() - t
    if tasks & {"upscale2", "upscale4"}:
        t = time.perf_counter()
        eng = build_engine_class(v.get("fixed", False), v.get("shrink", False))(
            x2, x4, tile_size=args.tile, tile_overlap=args.overlap, num_threads=threads)
        engines["upscale2"] = engines["upscale4"] = eng
        load_s["upscale"] = time.perf_counter() - t

    result = {
        "env": {
            "cpus_seen_by_app": threads,
            "os_cpu_count": os.cpu_count(),
            "affinity": sorted(os.sched_getaffinity(0)),
            "cpu.max": _read("cpu.max"),
            "cpuset.cpus.effective": _read("cpuset.cpus.effective"),
            "memory.max": _read("memory.max"),
            "memory.swap.max": _read("memory.swap.max"),
            "pids.max": _read("pids.max"),
            "onnxruntime": ort.__version__,
            "python": platform.python_version(),
            "numpy": np.__version__,
            "variant": args.variant,
            "tile": args.tile,
            "overlap": args.overlap,
            "x4_model": Path(x4).name,
        },
        "model_load_s": load_s,
        "jobs": [],
    }

    for job in jobs:
        if job["task"] == "profile":
            result["jobs"].append({"id": job["id"], "task": "profile",
                                   "profile": profile_tile(x4, threads, job.get("tile", 288), job["input"], Path("/work/profiles"))})
            continue
        img = load_image(job)
        rec = {"id": job["id"], "task": job["task"], "input_size": list(img.size), "iters": []}
        for _ in range(job.get("iters", 1)):
            sampler = MemSampler()
            sampler.start()
            c0, t0 = cpu_stat(), time.perf_counter()
            if job["task"] == "colorize":
                out = engines["colorize"].colorize(img)
            else:
                out = engines[job["task"]].upscale(img, 2 if job["task"] == "upscale2" else 4)
            wall = time.perf_counter() - t0
            c1 = cpu_stat()
            rec["iters"].append(
                {
                    "wall_s": wall,
                    "cpu_s": (c1["usage_usec"] - c0["usage_usec"]) / 1e6,
                    "throttled_periods": c1.get("nr_throttled", 0) - c0.get("nr_throttled", 0),
                    "throttled_s": (c1.get("throttled_usec", 0) - c0.get("throttled_usec", 0)) / 1e6,
                    "mem_peak_mb": sampler.stop() / 2**20,
                }
            )
        rec["output_size"] = list(out.size)
        if job.get("save"):
            out.save(job["save"])
        result["jobs"].append(rec)

    result["container_memory_peak_mb"] = int(_read("memory.peak") or 0) / 2**20
    result["maxrss_mb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    Path(args.out).write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
