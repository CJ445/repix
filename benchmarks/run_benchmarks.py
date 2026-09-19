"""Host-side orchestrator for the Repix benchmark, sized for the deployment target:
Hostinger KVM 2 = 2 vCPU + 8 GB RAM.

Every measurement runs in its own container that is capped to exactly that spec, has no
network, a read-only root filesystem and no capabilities, and runs strictly one at a time.

Emulating "a 2-vCPU VPS" on a 16-thread host:
  --cpus 2            CFS quota: at most 2 CPUs' worth of time
  --cpuset-cpus 0,1   pins to two distinct physical cores, so the app sees exactly 2 CPUs,
                      like it would inside the VPS (os.cpu_count() == 2)

Safety layers (any one of them is enough to keep the host alive):
  1. Container caps: cpus, memory == memory-swap (no swap), pids-limit.
  2. Hard ceiling in this script: never more than SPEC_CPUS / SPEC_MEM_GB.
  3. Pre-flight: refuses to start if host free RAM or load is not comfortable.
  4. Watchdog: kills the container if host MemAvailable falls below MEM_FLOOR_GB, or on timeout.
  5. --oom-score-adj so that, in the worst case, the kernel picks the benchmark first.

Usage: python run_benchmarks.py <stage> --work DIR
  stages: baseline | ablation | ablation_big | prep | candidates | quality
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
IMAGE = "image-editor-backend:latest"

SPEC_CPUS = 2  # Hostinger KVM 2
SPEC_MEM_GB = 8
SPEC_CPUSET = "0,1"  # two distinct physical cores on this host
MIN_HOST_AVAIL_GB = 6.0  # do not start unless this much RAM is free (largest measured job peaks < 4 GB)
MEM_FLOOR_GB = 2.0  # watchdog kills the run if host free RAM drops below this
MAX_LOAD1 = 8.0


def host_mem_avail_gb() -> float:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable"):
            return int(line.split()[1]) / 2**20
    return 0.0


def sh(*cmd: str, check=True, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, capture_output=True, text=True, **kw)


def preflight(cpus: float, mem_gb: int) -> None:
    if cpus > SPEC_CPUS or mem_gb > SPEC_MEM_GB:
        sys.exit(f"refusing: request ({cpus} cpus, {mem_gb}g) exceeds the spec ({SPEC_CPUS} cpus, {SPEC_MEM_GB}g)")
    if host_mem_avail_gb() < MIN_HOST_AVAIL_GB:
        sys.exit(f"refusing: only {host_mem_avail_gb():.1f} GB host RAM available")
    # The 1-minute load average includes the previous benchmark's own threads, so wait for it to settle.
    waited = 0
    while os.getloadavg()[0] > MAX_LOAD1:
        if waited >= 300:
            sys.exit(f"refusing: host load {os.getloadavg()[0]:.1f} > {MAX_LOAD1} for 5 min (something else is busy)")
        time.sleep(10)
        waited += 10


def run_container(
    name: str,
    work: Path,
    jobs: list[dict],
    *,
    variant: str = "prod",
    tile: int = 256,
    cpuset: str | None = SPEC_CPUSET,
    env: dict[str, str] | None = None,
    ort123: bool = False,
    x4_model: str | None = None,
    timeout_s: int = 1500,
) -> dict:
    cpus, mem_gb = SPEC_CPUS, SPEC_MEM_GB
    preflight(cpus, mem_gb)
    (work / "jobs").mkdir(parents=True, exist_ok=True)
    (work / "results").mkdir(parents=True, exist_ok=True)
    jobs_file, out_file = work / "jobs" / f"{name}.json", work / "results" / f"{name}.json"
    jobs_file.write_text(json.dumps(jobs))
    out_file.unlink(missing_ok=True)

    sh("docker", "rm", "-f", name, check=False)
    pythonpath = "/work/ort123:/app" if ort123 else "/app"
    cmd = [
        "docker", "run", "--name", name, "--no-healthcheck",
        f"--cpus={cpus}", f"--memory={mem_gb}g", f"--memory-swap={mem_gb}g",
        "--pids-limit=256", "--oom-score-adj=800",
        "--network=none", "--read-only", "--tmpfs=/tmp:size=256m",
        "--cap-drop=ALL", "--security-opt=no-new-privileges",
        f"--user={os.getuid()}:{os.getgid()}",
        "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", f"PYTHONPATH={pythonpath}",
        *(["--cpuset-cpus=" + cpuset] if cpuset else []),
        *sum((["-e", f"{k}={v}"] for k, v in (env or {}).items()), []),
        "-v", f"{REPO / 'backend/app'}:/app/app:ro",
        "-v", f"{REPO / 'models'}:/app/models:ro",
        "-v", f"{REPO / 'benchmarks'}:/bench:ro",
        "-v", f"{work}:/work",
        "--entrypoint", "python", "-w", "/app", IMAGE,
        "/bench/bench_worker.py",
        "--jobs", f"/work/jobs/{name}.json", "--out", f"/work/results/{name}.json",
        "--variant", variant, "--tile", str(tile),
        *(["--x4-model", x4_model] if x4_model else []),
    ]

    killed = {"why": None}

    def watchdog():
        while proc.poll() is None:
            if host_mem_avail_gb() < MEM_FLOOR_GB:
                killed["why"] = f"host MemAvailable < {MEM_FLOOR_GB} GB"
                sh("docker", "kill", name, check=False)
                return
            time.sleep(0.5)

    t0 = time.time()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    threading.Thread(target=watchdog, daemon=True).start()
    try:
        log, _ = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        killed["why"] = f"timeout {timeout_s}s"
        sh("docker", "kill", name, check=False)
        log, _ = proc.communicate()
    wall = time.time() - t0

    st = json.loads(sh("docker", "inspect", name, "--format", "{{json .State}}").stdout)
    sh("docker", "rm", "-f", name, check=False)

    res = {"name": name, "cpus_cap": cpus, "mem_cap_gb": mem_gb, "cpuset": cpuset, "variant": variant, "tile": tile,
           "ort123": ort123, "x4_model": x4_model, "container_wall_s": wall, "exit_code": st["ExitCode"],
           "oom_killed": st["OOMKilled"], "killed_by_harness": killed["why"], "log_tail": log[-1500:]}
    if out_file.exists():
        res.update(json.loads(out_file.read_text()))
    status = "OOM-KILLED" if st["OOMKilled"] else f"exit {st['ExitCode']}"
    print(f"[{name}] {status} in {wall:.0f}s", flush=True)
    if st["ExitCode"] and not st["OOMKilled"]:
        print(log[-800:], flush=True)
    return res


def save(work: Path, stage: str, data) -> None:
    (work / "results" / f"{stage}.json").write_text(json.dumps(data, indent=1))


SRC = "/work/imgs/astronaut.png"
COFFEE = "/work/imgs/coffee.png"  # 600x400: 3x2 tiles of *different* shapes, the case the arena/fixed-shape tweaks target


# --------------------------------------------------------------------------------------
def stage_baseline(work: Path):
    """Shipped configuration at the target spec."""
    g = {"gray": True}
    jobs = [
        {"id": "colorize_512", "task": "colorize", "input": SRC, "resize": [512, 512], "iters": 3, **g},
        {"id": "colorize_1024", "task": "colorize", "input": SRC, "resize": [1024, 1024], "iters": 2, **g},
        {"id": "x2_512", "task": "upscale2", "input": SRC, "resize": [512, 512], "iters": 2},
        {"id": "x4_256", "task": "upscale4", "input": SRC, "resize": [256, 256], "iters": 2},
        {"id": "x4_512", "task": "upscale4", "input": SRC, "resize": [512, 512], "iters": 2},
    ]
    out = [run_container("base_main", work, jobs, timeout_s=1500),
           run_container("base_big", work, [{"id": "x4_1024", "task": "upscale4", "input": SRC, "resize": [1024, 1024], "iters": 1}], timeout_s=1500),
           run_container("base_profile", work, [{"id": "profile", "task": "profile", "input": SRC, "tile": 288}], timeout_s=600)]
    save(work, "baseline", out)


ABL_ENV = {"OMP_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "2", "MKL_NUM_THREADS": "2"}


def stage_ablation(work: Path):
    """One optimisation at a time on a 600x400 image, x4."""
    (work / "abl_out").mkdir(exist_ok=True)

    def job(name, iters=1):
        return [{"id": "coffee_x4", "task": "upscale4", "input": COFFEE, "iters": iters, "save": f"/work/abl_out/{name}.png"}]

    plan = [
        ("prod", dict(variant="prod"), 3),
        ("ort_default", dict(variant="ort_default"), 1),
        ("ort_default_quota_only", dict(variant="ort_default", cpuset=None), 1),
        ("arena_on", dict(variant="arena_on"), 1),
        ("spin_on", dict(variant="spin_on"), 1),
        ("thread_env", dict(variant="thread_env", env=ABL_ENV), 1),
        ("opt_basic", dict(variant="opt_basic"), 1),
        ("fixed_tiles", dict(variant="fixed_tiles"), 1),
        ("fixed_arena", dict(variant="fixed_arena"), 1),
        ("fixed_arena_shrink", dict(variant="fixed_arena_shrink"), 1),
        ("prod_ort123", dict(variant="prod", ort123=True), 1),
        ("fixed_arena_ort123", dict(variant="fixed_arena", ort123=True), 1),
        ("tile128", dict(variant="prod", tile=128), 1),
        ("tile384", dict(variant="prod", tile=384), 1),
        ("tile512", dict(variant="prod", tile=512), 1),
    ]
    prev = work / "results" / "ablation.json"
    out = json.loads(prev.read_text()) if prev.exists() else []
    done = {r["name"] for r in out if r.get("jobs") or r.get("oom_killed")}
    for name, kw, iters in plan:
        if f"abl_{name}" in done:
            continue
        if kw.get("ort123") and not (work / "ort123").exists():
            print(f"[{name}] skipped: run the 'prep' stage first", flush=True)
            continue
        out.append(run_container(f"abl_{name}", work, job(name, iters), timeout_s=1200, **kw))
        save(work, "ablation", out)  # incremental, so a crash keeps earlier results


def stage_ablation_big(work: Path):
    """Does the arena's memory growth show up on a larger image? 1024x1024 -> 4096x4096, cold single runs
    (compare with 'base_big', the shipped configuration on the same job)."""
    big = lambda n: [{"id": "x4_1024", "task": "upscale4", "input": SRC, "resize": [1024, 1024], "iters": 1, "save": f"/work/abl_out/big_{n}.png"}]
    out = []
    for name in ("arena_on", "fixed_arena_shrink"):
        out.append(run_container(f"big_{name}", work, big(name), variant=name, timeout_s=1500))
        save(work, "ablation_big", out)


def stage_prep(work: Path):
    """Network-enabled, capped containers that only download/build candidate artefacts."""
    def pip(target: str, *pkgs: str, extra=()):
        preflight(2, 4)
        r = subprocess.run(["docker", "run", "--rm", "--cpus=2", "--memory=4g", "--memory-swap=4g", "--pids-limit=256",
                            "--cap-drop=ALL", "--security-opt=no-new-privileges", f"--user={os.getuid()}:{os.getgid()}",
                            "-e", "HOME=/tmp", "-v", f"{work}:/work", "--entrypoint", "python", IMAGE,
                            "-m", "pip", "install", "-q", "--no-cache-dir", "--target", f"/work/{target}", *extra, *pkgs],
                           capture_output=True, text=True)
        print(f"[pip {target}] exit {r.returncode}", r.stderr[-400:] if r.returncode else "", flush=True)
        return r.returncode == 0

    if not (work / "ort123").exists():
        pip("ort123", "onnxruntime==1.23.0", extra=["--no-deps"])
    if not (work / "pylibs").exists():
        pip("pylibs", "onnx")
    if not (work / "torchlibs").exists():
        pip("torchlibs", "torch", extra=["--index-url", "https://download.pytorch.org/whl/cpu"])


def stage_candidates(work: Path):
    """Speed/memory of candidate models (NOT part of the shipped stack): INT8-quantised x4plus, general-x4v3."""
    out = []
    cand = work / "candidates"
    jobs = lambda n, it=2: [{"id": "coffee_x4", "task": "upscale4", "input": COFFEE, "iters": it, "save": f"/work/abl_out/cand_{n}.png"}]
    for name, fname in (("int8", "realesrgan_x4plus_int8_qdq.onnx"), ("general_v3", "realesr_general_x4v3.onnx")):
        if (cand / fname).exists():
            out.append(run_container(f"cand_{name}", work, jobs(name), x4_model=f"/work/candidates/{fname}", timeout_s=1200))
            save(work, "candidates", out)
        else:
            print(f"[cand_{name}] skipped: {fname} not built", flush=True)


def stage_quality(work: Path):
    """Real output images (shipped config), plus the same x4 jobs through each candidate model."""
    manifest = json.loads((work / "quality_manifest.json").read_text())
    up = [j for j in manifest if j["task"].startswith("upscale")]
    col = [j for j in manifest if j["task"] == "colorize"]
    out = [run_container("quality_up", work, up, timeout_s=2400),
           run_container("quality_col", work, col, timeout_s=1200)]
    x4 = [j for j in up if j["task"] == "upscale4"]
    for name, fname in (("int8", "realesrgan_x4plus_int8_qdq.onnx"), ("general_v3", "realesr_general_x4v3.onnx")):
        if (work / "candidates" / fname).exists():
            cj = [{**j, "save": j["save"].replace("_sr_", f"_sr_{name}_").replace("showcase_", f"showcase_{name}_")} for j in x4]
            out.append(run_container(f"quality_{name}", work, cj, x4_model=f"/work/candidates/{fname}", timeout_s=2400))
    save(work, "quality", out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["baseline", "ablation", "ablation_big", "prep", "candidates", "quality"])
    ap.add_argument("--work", required=True, type=Path)
    a = ap.parse_args()
    globals()[f"stage_{a.stage}"](a.work.resolve())
