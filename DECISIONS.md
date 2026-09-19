# DECISIONS.md

Fixed, non-negotiable technology and model decisions for this project (per PRD.md).
Claude Code must not silently replace these.

## Fixed decisions (from PRD)

- Colorization model: **DDColor-Tiny**, ONNX Runtime, CPUExecutionProvider, FP32.
- Upscaling models: **RealESRGAN_x2plus** and **RealESRGAN_x4plus** (dedicated 4x model,
  never 2x run twice), ONNX Runtime, CPUExecutionProvider, FP32.
- Backend: Python, FastAPI, Pydantic, Pillow, OpenCV, ONNX Runtime CPU.
- Frontend: React, TypeScript, Vite, Tailwind CSS.
- No persistent storage of user images. Ephemeral `/tmp` job directories only, with TTL cleanup.
- Asynchronous AI jobs with polling (no WebSockets).
- Single-VPS architecture: `frontend`, `backend` containers. No Redis/Celery/Kubernetes/DB.

## Implementation decisions (left open by the PRD, resolved here)

### Model source
The PRD specifies exact model architectures but not a download URL. Pinned ONNX exports used:

- `ddcolor_tiny.onnx` — from `edgetools/ddcolor` (Hugging Face), fp16 weights with float32
  I/O boundary — no special handling needed since ORT executes it as a standard FP32 graph
  under `CPUExecutionProvider`.
- `realesrgan_x2plus.onnx` / `realesrgan_x4plus.onnx` — from `SceneWorks/real-esrgan-onnx`
  (Hugging Face), 1:1 ONNX exports of the canonical `xinntao/Real-ESRGAN` RRDBNet weights,
  dynamic H/W input, FP32 I/O. Chosen because (unlike several alternative exports found) it
  supports arbitrary tile sizes rather than a fixed 64x64 input, which our tiling
  implementation (Section 40 of the PRD) requires.

SHA-256 checksums are pinned in `models/CHECKSUMS.sha256` and verified by
`models/download_models.sh`.

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
