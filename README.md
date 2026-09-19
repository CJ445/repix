# Image Lab

A privacy-oriented, CPU-hosted image editor: crop, resize, AI colorization, and
AI upscaling (2x/4x), running entirely on CPU infrastructure. See `PRD.md` for
the full product/technical specification and `DECISIONS.md` for fixed and
resolved implementation decisions.

## What it does

1. Drop an image (JPEG/PNG/WebP) — preview appears instantly, client-side.
2. Crop and resize locally in the browser (no round-trip).
3. Colorize a grayscale image using **DDColor-Tiny**, or upscale 2x/4x using
   **RealESRGAN_x2plus/x4plus** — both run asynchronously on the backend via
   ONNX Runtime (CPU, FP32).
4. Compare before/after with a slider, then download the result.
5. Nothing is stored permanently: temp files live under `/tmp/image-lab/<job>`
   and are deleted after download or TTL expiry (`JOB_TTL_MINUTES`).

## Architecture

```
Browser (React + TS + Vite + Tailwind)
        │ HTTP (upload, poll)
        ▼
FastAPI backend  ──►  JobManager (thread pool, MAX_AI_WORKERS)
        │
        ├─ Pillow/OpenCV  (validation, EXIF, Lab conversion)
        ├─ DDColorEngine    (ONNX Runtime, CPUExecutionProvider)
        └─ RealESRGANEngine (ONNX Runtime, CPUExecutionProvider, tiled)
```

Crop/resize run client-side on `<canvas>`. Colorize/upscale are asynchronous
jobs: `POST /api/jobs` returns a `job_id` immediately, the frontend polls
`GET /api/jobs/{id}` every ~1.5s, then downloads via
`GET /api/jobs/{id}/download`.

## Local development (without Docker)

Backend:

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
bash ../models/download_models.sh   # downloads pinned ONNX weights, ~270MB
MODELS_DIR=../models uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev   # proxies /api to http://localhost:8000
```

Open http://localhost:5173.

## Docker (recommended)

```bash
cp .env.example .env
docker compose up --build
```

This builds and starts `backend` (FastAPI + ONNX Runtime, port 8000) and
`frontend` (static build served by nginx, port 5173, proxying `/api` to
`backend`). Model weights are downloaded during the backend image build.
No Python/Node/ONNX/OpenCV installation is required on the host.

Open http://localhost:5173.

## Model setup

Model weights are pinned dependencies, not user data — see `models/`:

```
models/
  ddcolor/ddcolor_tiny.onnx
  realesrgan/realesrgan_x2plus.onnx
  realesrgan/realesrgan_x4plus.onnx
  CHECKSUMS.sha256
  download_models.sh
```

Run `bash models/download_models.sh` to fetch and checksum-verify them (also
run automatically inside `docker/backend.Dockerfile`). Sources and rationale
for the exact exports used are documented in `DECISIONS.md`.

## Environment variables

See `.env.example`. All limits (upload size, input/output dimensions, job
TTL, worker concurrency, tiling) are configurable — nothing is hard-coded.

| Variable | Default | Purpose |
|---|---|---|
| `MAX_UPLOAD_MB` | 20 | Max upload size |
| `MAX_INPUT_WIDTH` / `MAX_INPUT_HEIGHT` | 6000 | Max input image dimensions |
| `MAX_OUTPUT_WIDTH` / `MAX_OUTPUT_HEIGHT` / `MAX_OUTPUT_PIXELS` | 10000 / 10000 / 50000000 | Max AI output size, enforced before starting a job |
| `JOB_TTL_MINUTES` | 60 | How long job data survives before forced cleanup |
| `MAX_AI_WORKERS` | 1 | Concurrent AI inference jobs (CPU-bound; keep low on small VPS) |
| `UPSCALE_TILE_SIZE` / `UPSCALE_TILE_OVERLAP` | 512 / 16 | Tiling for large-image upscale to bound memory |
| `RATE_LIMIT_PER_MINUTE` | 10 | Per-IP limit on `POST /api/jobs` |

## Testing

Backend:

```bash
cd backend && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest                 # unit + API tests (fast, no model weights needed)
# tests/test_engines.py runs against real ONNX models and is skipped
# automatically if models/download_models.sh hasn't been run
```

Frontend:

```bash
cd frontend
npm test
```

## Production deployment

The same containers run on any CPU-only Linux VPS — no NVIDIA drivers, CUDA,
GPU, or external AI APIs required. Only `CPUExecutionProvider` is used.
Set `.env` (especially `MAX_AI_WORKERS=1` on small VPS instances), then:

```bash
docker compose up --build -d
```

## Privacy / data lifecycle

- No accounts, no database, no persistent image storage.
- Uploaded images and AI results live only in `/tmp/image-lab/<job_id>` for
  the duration of processing plus `JOB_TTL_MINUTES`, then are deleted.
- Refreshing the page or opening a new session never restores a previous
  image — the frontend keeps no image data in `localStorage`/`sessionStorage`.
- Job IDs are random UUIDs, not sequential — a job cannot be enumerated or
  guessed by another client.
- Logs contain job id, operation, dimensions, duration, and error category
  only — never image bytes or content.

## Troubleshooting

- **`/ready` returns 503`**: model weights aren't present. Run
  `bash models/download_models.sh` (or rebuild the backend image).
- **Upscale/colorize jobs stay `queued` for a long time**: `MAX_AI_WORKERS`
  limits concurrency; on a 1-vCPU VPS, keep it at `1` and expect processing
  (not queueing) to simply take longer for large images.
- **"We couldn't process this image" error**: check backend logs — the
  technical exception is logged server-side but never shown to the user.
- **Large image upscale rejected before starting**: the requested output
  would exceed `MAX_OUTPUT_WIDTH`/`HEIGHT`/`PIXELS`; pick a smaller image or
  a lower scale factor, or raise the limits in `.env` if your VPS has the RAM.
