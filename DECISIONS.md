# DECISIONS.md

Fixed, non-negotiable technology and model decisions for this project (per PRD.md).
Claude Code must not silently replace these.

## Fixed decisions (from PRD)

- Colorization model: **DDColor-Large**, ONNX Runtime, CPUExecutionProvider, FP32.
  *Overrides the PRD, which specified DDColor-Tiny (PRD §5.1); changed at the project owner's
  explicit request. See "Colorization model change" below.*
- Upscaling models: **RealESRGAN_x2plus** and **RealESRGAN_x4plus** (dedicated 4x model,
  never 2x run twice), ONNX Runtime, CPUExecutionProvider, FP32.
- Backend: Python, FastAPI, Pydantic, Pillow, OpenCV, ONNX Runtime CPU.
- Frontend: React, TypeScript, Vite, Tailwind CSS.
- No persistent storage of user images. Ephemeral `/tmp` job directories only, with TTL cleanup.
- Asynchronous AI jobs with polling (no WebSockets).
- Single-VPS architecture: `frontend`, `backend` containers. No Redis/Celery/Kubernetes/DB.

## Implementation decisions (left open by the PRD, resolved here)

### Model source
The PRD specifies exact model architectures but not a download URL. Pinned ONNX exports used.
To survive upstream removals, the files are mirrored unchanged in
[`thecyriljacob/repix-dependency-models`](https://huggingface.co/thecyriljacob/repix-dependency-models)
(tag `v1`), which is what `models/download_models.sh` pulls from (override with `MODEL_BASE_URL`).
The original upstream sources, for provenance:

- `ddcolor_large.onnx` — from `Diogo122333/ddcolor-512-fp16` (Hugging Face), fp16 weights with
  float32 I/O boundary, fixed 512x512 input — no special handling needed since ORT executes it
  as a standard FP32 graph under `CPUExecutionProvider`. Third-party export with no model card
  or license; it has 227.9M parameters, matching DDColor-Large, and the same I/O contract as the
  Tiny export previously used, but it has not been checked against the official `piddnad`
  PyTorch checkpoints.
- `realesrgan_x2plus.onnx` / `realesrgan_x4plus.onnx` — from `SceneWorks/real-esrgan-onnx`
  (Hugging Face), 1:1 ONNX exports of the canonical `xinntao/Real-ESRGAN` RRDBNet weights,
  dynamic H/W input, FP32 I/O. Chosen because (unlike several alternative exports found) it
  supports arbitrary tile sizes rather than a fixed 64x64 input, which our tiling
  implementation (Section 40 of the PRD) requires.

SHA-256 checksums are pinned in `models/CHECKSUMS.sha256` and verified by
`models/download_models.sh`, so a wrong or altered mirror is rejected.

### Job security / capability token
Section 37 requires unguessable job IDs and a "secure per-session capability/token or
equivalent mechanism." We use the job ID itself: a UUID4 (122 bits of entropy) generated
server-side, never derived from user input. This satisfies "equivalent mechanism" without
introducing session/auth infrastructure, consistent with Section 71 (no overengineering) and
the explicit non-goal of user accounts/login.

### Output format
AI job outputs (colorize/upscale) are always encoded as PNG. This avoids repeated lossy
JPEG re-encoding (Section 27) and guarantees transparency is never accidentally destroyed
(Section 26). Client-side crop/resize preserve the original image's format.

### Basic edit operations (crop/resize)
Implemented entirely client-side via `<canvas>` (Section 9: "should preferably happen
client-side"). This keeps the UI instant and avoids a network round-trip for operations that
don't need a CPU-bound model.

### Concurrency model
`MAX_AI_WORKERS` is implemented as a `ThreadPoolExecutor` pool size inside a single backend
process (no Celery/queue broker), since ONNX Runtime releases the GIL during inference and a
single VPS process is sufficient per Section 71.

### Resource limits and queueing
The backend container has hard CPU/memory caps (`BACKEND_CPUS`, `BACKEND_MEMORY`) so inference can
never take over the host. ONNX Runtime threads default to the cgroup CPU quota (not the host core
count) with spinning disabled. Jobs beyond `MAX_AI_WORKERS` wait in the executor queue, bounded by
`MAX_QUEUE_SIZE`; past that, job creation returns 503 + `Retry-After`.

### Continuing after an AI step
An AI result can be kept as the new working image, so crop/resize/further AI steps build on it.
Downloads go through a dialog that really encodes PNG/JPG/WebP client-side, so the sizes shown are
exact. Note that re-submitting a large kept result (e.g. a 4x upscale) to the AI is still subject
to `MAX_UPLOAD_MB`.

### Colorization model change (Tiny → Large)
The PRD required DDColor-Tiny "to keep CPU deployment practical". DDColor-Large replaces it
because a smoke test on 2 pinned CPUs showed it fits the target comfortably: ~4.9 s per
colorization vs ~2.5 s for Tiny, ~2.3 GB peak RSS vs ~1.5 GB (host run, not the capped
container). Colorization always runs at a fixed 512x512, so cost does not grow with image size.

Verified after the switch: the backend rebuilt with Large loads it and colorizes through the API in
~4.6-4.9 s per job (512² and 1024² inputs) inside the default compose stack (2 CPUs, 4 GiB cap),
peaking at ~2.1 GiB sampled RSS with no OOM, so the default `BACKEND_MEMORY=4g` still has ~2x
headroom with `MAX_AI_WORKERS=1`. Backend tests pass (38) with the Large model.

Open items: the pinned-core benchmark harness has not been re-run with Large, so
`benchmarks/repix-model-comparison.pdf`, its `make_report.py` text and the colorization entries in
`benchmarks/results/` still describe DDColor-Tiny (flagged in `benchmarks/README.md`). Confirm the
export's license before distributing.

### Resize units (px, in, cm, mm)
Resize accepts pixels or physical units. Images carry no reliable physical size and the app never
writes DPI metadata (canvas encoding stores pixels only), so physical units need an explicit
resolution: it defaults to 300 DPI (print) and is editable. The pixel size is the single source of
truth; the unit and DPI only change how it is displayed and typed, and results are always whole
pixels. As before, sizes larger than the current image are rejected (use Upscale).
