# Benchmarks

Reproducible CPU benchmarks for Repix, sized for a **2 vCPU / 8 GB** deployment target. Every
measurement runs in a capped, network-less, read-only container, one at a time, so the benchmark
cannot take the host down. The finished write-up is
[`repix-model-comparison.pdf`](./repix-model-comparison.pdf); raw numbers are in [`results/`](./results).

> **Note:** the PDF report, `results/baseline.json`, `results/quality.json` and `results/onnx_macs.json`
> were produced when colorization used DDColor-Tiny, and `make_report.py` still refers to it (its
> `ddcolor_tiny` MAC-count key and model path). The upscaling results are unaffected. `bench_worker.py`
> already loads DDColor-Large, so re-running the stages measures Large; the report needs a fresh
> `onnx_macs.json` with a `ddcolor_large@512x512` entry and the `make_report.py` text updated to match.

| File | Purpose |
| ---- | ------- |
| `run_benchmarks.py` | Host-side orchestrator: container caps, pre-flight checks, watchdog. Stages: `baseline`, `ablation`, `ablation_big`, `prep`, `candidates`, `quality` |
| `bench_worker.py` | Runs *inside* the container against the app's real engine classes; records time, per-job peak RAM and cgroup CPU accounting; implements the one-at-a-time optimisation variants and the ONNX Runtime per-layer profiler |
| `make_quality_inputs.py` | Ground-truth test pairs (downsampled / degraded inputs, grayscale colour photos) |
| `build_candidates.py` | Builds the optional INT8 and `realesr-general-x4v3` candidate models |
| `make_report.py` | Computes PSNR/SSIM/ΔE, draws the figures and equations, writes the PDF |
| `results/` | Raw JSON results (`onnx_macs.json` holds MAC counts derived from the ONNX graphs) |

## Reproduce

Requires Docker, the `image-editor-backend` image (`./start.sh` builds it), and a Python venv with
`reportlab matplotlib scikit-image onnx numpy pillow opencv-python-headless` for the host-side scripts.

```bash
WORK=/path/to/scratch                      # needs WORK/imgs/{astronaut,coffee,chelsea}.png (skimage.data)
python benchmarks/make_quality_inputs.py $WORK
python benchmarks/run_benchmarks.py baseline     --work $WORK
python benchmarks/run_benchmarks.py ablation     --work $WORK
python benchmarks/run_benchmarks.py ablation_big --work $WORK
python benchmarks/run_benchmarks.py prep         --work $WORK   # network: ORT 1.23, onnx, torch (for candidates)
python benchmarks/build_candidates.py            --work $WORK
python benchmarks/run_benchmarks.py candidates   --work $WORK
python benchmarks/run_benchmarks.py quality      --work $WORK
python benchmarks/make_report.py --work $WORK --macs benchmarks/results/onnx_macs.json --out report.pdf
```

Adjust `SPEC_CPUS`, `SPEC_MEM_GB` and `SPEC_CPUSET` at the top of `run_benchmarks.py` to model a
different plan. Absolute times depend on the host CPU; the MAC counts, memory model and relative
effects are the portable part.
