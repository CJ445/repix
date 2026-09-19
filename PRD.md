# MASTER PRD / SRS

## CPU-Hosted Image Processing Web Application

**Document Type:** Product Requirements Document + Software Requirements Specification + Technical Implementation Specification
**Status:** Implementation-ready
**Primary Goal:** Build a polished, fast-feeling, privacy-oriented web application for image editing and AI enhancement, designed to run entirely on CPU infrastructure and deployed as Docker containers.

---

# 1. PRODUCT DEFINITION

Build a modern web-based image editor that allows users to:

1. Upload an image.
2. Preview it immediately.
3. Crop it interactively.
4. Resize it.
5. Convert grayscale/black-and-white images to color using an AI colorization model.
6. Upscale images by exactly 2× or 4× using AI super-resolution.
7. Preview original vs processed output.
8. Download the processed image.
9. Start over and process another image.

The application must prioritize:

> **Smooth UX > feature count > implementation complexity.**

AI processing may be slow because the production environment is CPU-only. The UI must therefore remain responsive while AI jobs run asynchronously.

The application must not permanently store user images.

---

# 2. NON-GOALS

Do NOT implement:

* User accounts
* Login/signup
* Cloud image storage
* Persistent user galleries
* Social features
* Image sharing
* Public image URLs
* Payments
* Subscriptions
* Image history across browser sessions
* Database-backed image storage
* Video processing
* GIF processing
* AI image generation
* Face restoration
* Background removal
* Automatic object removal
* Collaborative editing
* Mobile native applications
* Admin dashboard in MVP

Do not add features merely because they seem useful.

---

# 3. CORE PRODUCT PRINCIPLE

The application must feel like a polished desktop-quality image utility rather than a traditional file-upload form.

The user should be able to:

```text
Open website
    ↓
Drop image
    ↓
Immediately see image
    ↓
Choose operation
    ↓
Process
    ↓
Compare result
    ↓
Download
```

The user should never need to understand the backend architecture.

---

# 4. FIXED TECHNOLOGY DECISIONS

Claude Code MUST NOT replace these technologies unless a blocking technical incompatibility is discovered.

## Frontend

* React
* TypeScript
* Vite
* Tailwind CSS
* Modern component architecture
* Responsive design

Use a high-quality image/canvas interaction library where appropriate rather than manually implementing complex image manipulation primitives unnecessarily.

## Backend

* Python
* FastAPI
* Pydantic
* Pillow
* OpenCV where required
* ONNX Runtime CPU

## AI Runtime

Production inference MUST use:

```text
onnxruntime
CPUExecutionProvider
FP32
```

Do not use CUDA in the production architecture.

Do not require PyTorch for runtime inference if the selected ONNX model can be executed directly through ONNX Runtime.

---

# 5. FIXED AI MODELS

These model decisions are FINAL for MVP.

## 5.1 Colorization

Model:

**DDColor-Tiny**

Purpose:

Convert grayscale/black-and-white images into plausible color images.

Runtime:

```text
ONNX Runtime
CPUExecutionProvider
FP32
```

The DDColor project provides a Tiny pretrained model and ONNX export support. The implementation must use the Tiny model rather than the larger model to keep CPU deployment practical.

Do NOT:

* Use DeOldify
* Add multiple colorization models
* Add a model selector
* Dynamically choose models
* Call an external colorization API
* Send images to a third-party inference service

The model must run locally inside the application infrastructure.

---

# 6. UPSCALING ENGINE

The application MUST expose two explicit upscale options.

## 6.1 2×

Model:

**RealESRGAN_x2plus**

Input:

```text
W × H
```

Output:

```text
2W × 2H
```

## 6.2 4×

Model:

**RealESRGAN_x4plus**

Input:

```text
W × H
```

Output:

```text
4W × 4H
```

The official Real-ESRGAN model zoo identifies these as general-image x2 and x4 models respectively.

Production inference:

```text
ONNX Runtime
CPUExecutionProvider
FP32
```

Real-ESRGAN's own documentation notes that FP16 inference can fail on CPU because some operators do not support half precision; CPU inference therefore must use FP32.

Do NOT implement 4× by running the 2× model twice.

Use the dedicated x4 model.

---

# 7. MODEL FILE MANAGEMENT

Model weights must be treated as application dependencies, not user data.

Expected conceptual structure:

```text
models/
    ddcolor/
        ddcolor_tiny.onnx

    realesrgan/
        realesrgan_x2plus.onnx
        realesrgan_x4plus.onnx
```

Model files must be:

* Downloaded during the image-processing container build or explicit model setup step.
* Version-pinned.
* Verified with checksums where practical.
* Loaded once and reused between jobs.

DO NOT load the model from disk for every request.

Use long-lived inference engine instances.

---

# 8. APPLICATION ARCHITECTURE

Use this architecture:

```text
                    ┌─────────────────────┐
                    │      Browser        │
                    │                     │
                    │ React + TypeScript  │
                    └──────────┬──────────┘
                               │
                               │ HTTP
                               ▼
                    ┌─────────────────────┐
                    │       FastAPI       │
                    │                     │
                    │ Upload / Jobs / API │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    Job Processor    │
                    │                     │
                    │ ONNX Runtime CPU    │
                    └──────────┬──────────┘
                               │
             ┌─────────────────┼──────────────────┐
             ▼                 ▼                  ▼
         Pillow/OpenCV      DDColor          Real-ESRGAN
                           Colorization       2× / 4×
```

The frontend must never block waiting synchronously for an AI inference request.

---

# 9. JOB PROCESSING MODEL

Basic operations:

* Crop
* Resize

should preferably happen client-side where doing so improves responsiveness and does not compromise output correctness.

AI operations:

* Colorization
* Upscaling

must run asynchronously on the backend.

Conceptual flow:

```text
POST /api/jobs
       ↓
Validate request
       ↓
Create job
       ↓
Return job_id immediately
       ↓
Worker processes image
       ↓
Update job status
       ↓
Frontend receives/polls status
       ↓
Result becomes available
       ↓
User downloads
       ↓
Temporary result deleted
```

---

# 10. JOB STATES

Every AI job must have a clearly defined state.

Allowed states:

```text
queued
processing
completed
failed
cancelled
expired
```

The frontend must render appropriate UI for each state.

---

# 11. JOB PROGRESS

Where actual model-level progress cannot be accurately measured, do NOT fabricate a percentage.

For example, do not claim:

```text
72%
```

when the model does not expose meaningful progress.

Instead use:

```text
Processing image…
```

with an animated progress indicator.

If processing consists of known stages, stage-based progress may be shown:

```text
Preparing image
      ↓
Running AI model
      ↓
Encoding result
      ↓
Ready
```

Only show numerical progress when it represents a real measurable value.

---

# 12. IMAGE UPLOAD

Supported input formats:

* JPEG
* PNG
* WebP

Reject unsupported formats.

Recommended initial limits:

```text
Maximum upload size: 20 MB
Maximum input dimension: 6000 × 6000 px
```

These must be configurable through environment variables.

Example:

```text
MAX_UPLOAD_MB=20
MAX_INPUT_WIDTH=6000
MAX_INPUT_HEIGHT=6000
```

Do not hard-code these values throughout the codebase.

---

# 13. IMAGE VALIDATION

Never trust:

* Filename extension
* MIME type supplied by browser
* Client-side metadata

Backend must validate the actual image content.

Validation pipeline:

```text
Upload
 ↓
Size check
 ↓
Decode
 ↓
Verify valid image
 ↓
Read dimensions
 ↓
Read format
 ↓
Normalize orientation
 ↓
Accept/reject
```

Reject malformed or unsupported images cleanly.

Never crash the worker because of malformed input.

---

# 14. EXIF / ORIENTATION

The backend must correctly handle EXIF orientation.

Images must be normalized before processing so that:

* Preview orientation is correct.
* Crop coordinates are correct.
* AI processing uses correctly oriented pixels.
* Downloaded output is correctly oriented.

Do not accidentally rotate images twice.

---

# 15. FRONTEND UX

The UI should be minimal and polished.

Avoid:

* Excessive cards
* Excessive gradients
* Dashboard-style layouts
* Unnecessary navigation
* Dense technical controls
* Fake AI marketing language
* Excessive animations

The product should feel like a focused image utility.

---

# 16. MAIN SCREEN

Initial state:

```text
------------------------------------------------

                IMAGE LAB

       Drop an image here

              or

          [ Choose Image ]

       JPG • PNG • WebP

------------------------------------------------
```

Support:

* Drag and drop
* File picker
* Paste from clipboard where browser support allows

After upload, transition immediately to the editor.

---

# 17. EDITOR LAYOUT

Desktop:

```text
┌──────────────────────────────────────────────┐
│ IMAGE LAB                              Reset │
├───────────────────────┬──────────────────────┤
│                       │                      │
│                       │  Crop                │
│                       │  Resize              │
│      IMAGE            │  Colorize            │
│      CANVAS           │  Upscale             │
│                       │                      │
│                       │                      │
├───────────────────────┴──────────────────────┤
│             Download                         │
└──────────────────────────────────────────────┘
```

Mobile must use a stacked layout.

---

# 18. IMAGE PREVIEW

The uploaded image must appear immediately after upload.

Do not upload to the server first and wait for a server response before showing the preview.

Use the local browser file for immediate preview.

The application should feel responsive even if backend processing takes time.

---

# 19. CROP

Crop must provide:

* Free crop
* 1:1
* 4:3
* 3:2
* 16:9
* Custom aspect ratio

Requirements:

* Interactive crop box
* Drag
* Resize
* Preview
* Apply
* Cancel

Crop must not unexpectedly degrade image quality.

Where practical, retain the highest available resolution.

---

# 20. RESIZE

Resize controls:

```text
Width
Height
```

Provide:

```text
Lock aspect ratio
```

Default:

```text
Lock aspect ratio = ON
```

Provide common presets:

* 25%
* 50%
* 75%
* 100%
* Custom dimensions

Prevent invalid dimensions.

Do not upscale through the normal resize tool unless explicitly allowed by the product design.

AI Upscale is a separate operation.

---

# 21. COLORIZATION UX

The user selects:

```text
Colorize
```

UI should explain simply:

```text
Add realistic color to a grayscale image.
```

Button:

```text
[ Colorize Image ]
```

Once started:

```text
Preparing image…

Colorizing image…

Almost there…
```

When complete:

```text
Before | After
```

The original must remain available for comparison.

---

# 22. COLORIZATION INPUT

If the image is already grayscale:

Proceed normally.

If the image appears to be already color:

Do not prevent processing.

The user explicitly requested colorization, so the operation should still be executed.

Optional informational message:

```text
This image appears to contain color already.
```

Do not make this a blocking confirmation.

---

# 23. UPSCALE UX

The user must choose:

```text
Upscale

[ 2× ]   [ 4× ]
```

Display estimated output dimensions before processing.

Example:

```text
1920 × 1080

2× → 3840 × 2160
4× → 7680 × 4320
```

If the output would exceed configured limits, disable the option and explain why.

Do not start an impossible job and fail later.

---

# 24. BEFORE / AFTER COMPARISON

After an AI operation completes, provide an intuitive comparison.

Requirements:

* Original image
* Processed image
* Slider comparison OR equivalent high-quality comparison interaction
* Zoom
* Pan
* Fit-to-screen

The comparison should work smoothly on desktop and mobile.

Avoid loading the entire image repeatedly during slider movement.

---

# 25. DOWNLOAD

Primary action:

```text
[ Download Image ]
```

Downloaded filename should be deterministic and user-friendly.

Examples:

```text
photo-colorized.png
photo-upscaled-2x.png
photo-upscaled-4x.png
photo-edited.png
```

Do not expose internal job IDs in filenames.

---

# 26. OUTPUT FORMATS

For MVP:

* PNG
* JPEG
* WebP

The UI should provide output format selection where useful.

Default:

* Preserve PNG when transparency is relevant.
* Otherwise use a sensible lossless/high-quality format.

Do not unexpectedly convert transparent images to JPEG.

---

# 27. IMAGE QUALITY

Do not repeatedly JPEG encode/decode the image during a processing pipeline.

Pipeline should preserve image quality as much as practical.

For AI operations:

```text
Original
 ↓
Decode
 ↓
Normalize
 ↓
AI processing
 ↓
Encode once
 ↓
Download
```

Avoid unnecessary intermediate lossy conversions.

---

# 28. EPHEMERAL DATA POLICY

This is a critical requirement.

The application must NOT permanently store user images.

There must be:

**NO persistent `/data` volume for user files.**

Do not create:

```text
/data/uploads
/data/results
```

as persistent Docker volumes.

Temporary files may exist during processing.

They must be automatically removed.

---

# 29. TEMPORARY STORAGE

Use temporary filesystem storage.

Conceptually:

```text
/tmp/image-lab/
    job-123/
        input
        output
```

Each job must have an isolated temporary directory.

When the job finishes:

```text
output available
       ↓
user downloads
       ↓
delete temporary data
```

---

# 30. TTL CLEANUP

Download cleanup is not sufficient.

If a user:

```text
uploads
→ processes
→ closes browser
```

the files must still eventually disappear.

Implement automatic cleanup.

Recommended default:

```text
JOB_TTL_MINUTES=60
```

Any expired job data must be deleted.

Cleanup must run independently of user activity.

---

# 31. PAGE REFRESH / NEW SESSION

Refreshing the page must NOT restore previous user images.

A new browser session must not have access to old jobs.

Do not implement persistent frontend state containing image data.

Do not store uploaded images in:

* localStorage
* sessionStorage
* IndexedDB

unless specifically required for a temporary UI optimization and the data is guaranteed to be removed appropriately.

Default behavior:

```text
Refresh → clean new state
```

---

# 32. PRIVACY

The application must not:

* Train models on uploaded images
* Send images to external AI APIs
* Store images permanently
* Create public image URLs
* Create user profiles
* Log image contents

Logs may contain:

```text
job_id
operation
status
duration
error category
image dimensions
```

Do not log:

* image binary data
* image contents
* full sensitive filenames unnecessarily

---

# 33. API DESIGN

Use REST APIs.

## Upload / Job Creation

```http
POST /api/jobs
```

Multipart form data:

```text
file
operation
options
```

Possible operations:

```text
colorize
upscale
```

Response:

```json
{
  "job_id": "uuid",
  "status": "queued"
}
```

---

# 34. JOB STATUS

```http
GET /api/jobs/{job_id}
```

Response:

```json
{
  "job_id": "uuid",
  "status": "processing",
  "operation": "upscale",
  "scale": 2
}
```

When completed:

```json
{
  "job_id": "uuid",
  "status": "completed",
  "download_url": "/api/jobs/{job_id}/download"
}
```

Do not expose filesystem paths.

---

# 35. DOWNLOAD

```http
GET /api/jobs/{job_id}/download
```

The backend must verify that:

* Job exists
* Job belongs to a valid temporary session/token
* Job is completed
* Output still exists
* Job has not expired

Return the file as a download.

---

# 36. DELETE / CANCEL

Provide:

```http
DELETE /api/jobs/{job_id}
```

This must immediately attempt to delete all temporary job data.

If a job is processing, cancellation should be requested.

The worker must check cancellation where practical.

---

# 37. SESSION SECURITY

Do not use predictable sequential job IDs.

Use UUID/random identifiers.

Do not allow:

```text
GET /api/jobs/1
GET /api/jobs/2
```

to enumerate users' files.

Job access must require a secure per-session capability/token or equivalent mechanism.

A user must never be able to access another user's image merely by guessing a job ID.

---

# 38. WORKER CONCURRENCY

CPU inference is expensive.

Do NOT allow unlimited concurrent AI jobs.

Implement configurable concurrency:

```text
MAX_AI_WORKERS=1
```

Default to 1 for the initial VPS deployment.

Make it configurable.

Additional jobs remain queued.

This prevents several CPU-heavy Real-ESRGAN processes from exhausting the VPS.

---

# 39. MODEL LOADING

Load each model once per worker process.

Conceptually:

```python
class ColorizationEngine:
    def __init__(self):
        self.session = load_ddcolor_onnx()

class UpscalingEngine:
    def __init__(self):
        self.x2_session = load_realesrgan_x2()
        self.x4_session = load_realesrgan_x4()
```

Do NOT:

```text
job arrives
→ load model
→ inference
→ unload model
```

That would create unnecessary latency.

---

# 40. UPSCALING MEMORY MANAGEMENT

Large images can create very large output tensors.

The implementation must:

* Validate dimensions before starting.
* Calculate expected output dimensions.
* Enforce maximum output dimensions.
* Use tiling if required by the ONNX implementation to prevent excessive memory consumption.
* Reassemble tiles correctly.
* Avoid visible seams.

If tiling is used, make tile size configurable.

Example:

```text
UPSCALE_TILE_SIZE=512
UPSCALE_TILE_OVERLAP=16
```

Do not expose these technical controls to normal users.

---

# 41. OUTPUT LIMITS

Make output limits configurable.

Example:

```text
MAX_OUTPUT_WIDTH=10000
MAX_OUTPUT_HEIGHT=10000
MAX_OUTPUT_PIXELS=50000000
```

Before starting 4×:

```text
input dimensions
      ↓
calculate 4× dimensions
      ↓
validate limits
      ↓
accept/reject
```

---

# 42. ERROR HANDLING

Errors must be user-friendly.

Never expose:

* Python stack traces
* Internal paths
* Model implementation details
* Docker errors
* SQL errors
* ONNX exception dumps

Example:

Instead of:

```text
onnxruntime.capi.onnxruntime_pybind11_state...
```

show:

```text
We couldn't process this image.
Please try a smaller image or try again.
```

Developer logs should retain the technical error.

---

# 43. FRONTEND ERROR STATES

Implement explicit UI states:

```text
Idle
Uploading
Ready
Processing
Completed
Failed
Expired
```

Each state must have a clear visual representation.

---

# 44. RESPONSIVENESS

The UI must remain responsive during:

* Upload
* Image manipulation
* Polling
* AI processing
* Download

AI computation must never execute on the browser's main UI thread.

---

# 45. POLLING / REAL-TIME STATUS

For MVP, use simple HTTP polling.

Example:

```text
GET /api/jobs/{id}
```

every 1–2 seconds while processing.

Do not introduce WebSockets unless there is a concrete need.

The goal is reliability and simplicity.

---

# 46. FRONTEND STATE

Maintain application state in memory.

Conceptual state:

```text
currentImage
originalImage
editedImage
selectedTool
job
processingState
error
```

Do not persist user images between sessions.

---

# 47. CLIENT-SIDE IMAGE OPERATIONS

Where appropriate, perform these locally:

* Preview
* Crop interaction
* Resize preview
* Canvas manipulation

But the final exported image must use the appropriate full-resolution source rather than a low-resolution preview.

---

# 48. UI PERFORMANCE

Do not render huge source images unnecessarily at native resolution inside the browser UI.

Use:

* object URLs
* appropriately sized preview representations
* canvas scaling
* lazy resource handling

Revoke object URLs when no longer required.

---

# 49. DRAG AND DROP

Drop zone must provide clear states:

```text
Default:
Drop image here

Hover:
Release to upload

Invalid:
Unsupported image type
```

Do not silently ignore invalid files.

---

# 50. RESPONSIVE DESIGN

Desktop:

* Large image workspace
* Side tool panel

Tablet:

* Adaptive workspace
* Collapsible controls

Mobile:

* Image first
* Controls below image
* Large touch targets
* Sticky primary action where appropriate

Do not simply shrink the desktop interface.

---

# 51. ACCESSIBILITY

Implement:

* Keyboard navigation
* Visible focus states
* Semantic buttons
* Labels for controls
* Appropriate ARIA where needed
* Sufficient contrast
* Screen-reader meaningful status messages

Processing status should be announced appropriately.

---

# 52. VISUAL DESIGN

Design language:

* Minimal
* Premium
* Modern
* Neutral
* Utility-focused

Avoid:

* Excessive gradients
* Excessive glassmorphism
* Generic "AI" neon aesthetics
* Huge marketing headlines
* Excessive shadows
* Dashboard clutter

The image should be the visual focus.

---

# 53. ANIMATIONS

Use subtle animations only.

Examples:

* Upload transition
* Tool selection
* Processing indicator
* Before/after slider
* Download confirmation

Do not animate the entire application unnecessarily.

Respect:

```text
prefers-reduced-motion
```

---

# 54. DOCKER ARCHITECTURE

Use Docker.

Recommended services:

```text
frontend
backend
worker
```

Redis should only be introduced if required by the selected job implementation.

Do not introduce unnecessary infrastructure.

---

# 55. LOCAL DEVELOPMENT

The application MUST run locally using Docker Compose.

Required command:

```bash
docker compose up --build
```

This should start the application.

The developer should not need to manually install:

* Python
* Node
* ONNX Runtime
* OpenCV
* Pillow
* model dependencies

outside the containers.

---

# 56. PRODUCTION DEPLOYMENT

The same container architecture must work on a CPU-only Linux VPS.

Production must NOT require:

* NVIDIA drivers
* CUDA
* GPU
* cloud AI APIs

The only inference provider should be:

```text
CPUExecutionProvider
```

---

# 57. PERSISTENT STORAGE

Persistent storage is prohibited for user data.

Allowed persistent storage:

* Docker image layers
* application code
* model weights
* configuration
* system logs according to deployment environment

Not allowed:

```text
persistent user uploads
persistent processed images
persistent user galleries
```

---

# 58. ENVIRONMENT CONFIGURATION

Use environment variables for:

```text
APP_ENV
MAX_UPLOAD_MB
MAX_INPUT_WIDTH
MAX_INPUT_HEIGHT
MAX_OUTPUT_WIDTH
MAX_OUTPUT_HEIGHT
MAX_OUTPUT_PIXELS
JOB_TTL_MINUTES
MAX_AI_WORKERS
POLL_INTERVAL_MS
UPSCALE_TILE_SIZE
UPSCALE_TILE_OVERLAP
LOG_LEVEL
```

Do not scatter configuration constants throughout source files.

---

# 59. HEALTH CHECKS

Backend:

```http
GET /health
```

Returns:

```json
{
  "status": "ok"
}
```

Also implement a readiness check that verifies required model files are available and loadable.

Example:

```http
GET /ready
```

---

# 60. OBSERVABILITY

Logs should provide enough information to diagnose:

* Upload failures
* Job failures
* Model loading failures
* Processing duration
* Cleanup failures
* Resource-related failures

Log:

```text
timestamp
job_id
operation
input dimensions
output dimensions
duration
status
error category
```

Do not log image binary data.

---

# 61. SECURITY

Implement:

* File size validation
* MIME/content validation
* Dimension validation
* Safe temporary filenames
* Random job IDs
* Path traversal protection
* Output path isolation
* Request size limits
* Cleanup
* No arbitrary filesystem access through API parameters

Never use the original filename directly as a filesystem path.

---

# 62. RATE LIMITING

Implement basic per-client/IP rate limiting for expensive AI endpoints.

Make limits configurable.

The exact rate limit should be conservative enough to prevent accidental CPU exhaustion.

Do not require authentication for MVP.

---

# 63. TESTING REQUIREMENTS

The project is not complete when the UI merely works manually.

Implement automated tests.

## Backend unit tests

Test:

* Image validation
* File size validation
* Dimension validation
* Orientation normalization
* Job creation
* Job state transitions
* Expiration
* Cleanup
* Output dimension calculations
* Invalid operations
* Invalid scale
* Security around job IDs

---

# 64. AI ENGINE TESTS

For each model:

Test that:

```text
valid input
→ inference
→ valid output
```

Verify:

* Correct dimensions
* Valid image encoding
* No NaN/invalid output
* Correct color channels
* Model loads successfully
* Model can process representative image

Upscaling:

```text
input W×H
2× → 2W×2H
4× → 4W×4H
```

must be explicitly tested.

---

# 65. API TESTS

Test:

```text
POST /api/jobs
GET /api/jobs/{id}
GET /api/jobs/{id}/download
DELETE /api/jobs/{id}
```

Test successful and failure paths.

---

# 66. FRONTEND TESTS

Test:

* Upload flow
* Invalid upload
* Crop
* Resize
* Colorization initiation
* Upscaling selection
* Processing state
* Error state
* Download
* Reset
* Refresh behavior

---

# 67. END-TO-END TEST

At minimum:

```text
Open application
 ↓
Upload image
 ↓
Preview appears
 ↓
Select 2× upscale
 ↓
Job starts
 ↓
Processing state appears
 ↓
Job completes
 ↓
Before/after available
 ↓
Download works
 ↓
Reset
 ↓
No previous image remains
```

Repeat for:

* Colorization
* 4× upscale

---

# 68. QUALITY GATES

Claude Code MUST NOT declare implementation complete until:

### Gate 1 — Build

Frontend builds successfully.

Backend starts successfully.

Docker Compose starts successfully.

### Gate 2 — Model

All three ONNX models load:

```text
DDColor-Tiny
RealESRGAN_x2plus
RealESRGAN_x4plus
```

### Gate 3 — Functional

All core operations work.

### Gate 4 — Cleanup

Temporary files are actually removed.

### Gate 5 — Security

A user cannot access another job by changing its identifier.

### Gate 6 — UX

No blocking UI during AI processing.

### Gate 7 — Tests

Automated tests pass.

---

# 69. PROJECT STRUCTURE

Use a clean separation similar to:

```text
image-lab/
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── features/
│   │   ├── hooks/
│   │   ├── services/
│   │   ├── state/
│   │   └── utils/
│   └── ...
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── engines/
│   │   │   ├── colorization/
│   │   │   └── upscaling/
│   │   ├── jobs/
│   │   └── utils/
│   └── tests/
│
├── models/
│   ├── ddcolor/
│   └── realesrgan/
│
├── docker/
│
├── docker-compose.yml
├── .env.example
├── README.md
├── PRD.md
└── DECISIONS.md
```

The exact structure can be adjusted if there is a strong implementation reason, but the separation of frontend, API, job system, and AI engines must remain.

---

# 70. ENGINE ABSTRACTIONS

Implement explicit engine interfaces.

Conceptually:

```python
class ColorizationEngine:
    def colorize(self, image):
        ...

class UpscalingEngine:
    def upscale(self, image, scale):
        ...
```

The application layer should not directly contain ONNX-specific inference code.

This allows clean separation between:

```text
API
 ↓
Job
 ↓
Engine
 ↓
ONNX Runtime
```

---

# 71. NO OVERENGINEERING

Do not introduce:

* Kubernetes
* Celery unless actually required
* Kafka
* Microservices
* PostgreSQL
* S3
* Redis merely because it is popular
* GraphQL
* WebSockets without need

This is a single-product CPU VPS application.

Keep the architecture simple.

---

# 72. ERROR RECOVERY

If an AI job fails:

```text
processing
   ↓
failed
```

Temporary data must be cleaned.

The frontend must allow:

```text
Try Again
```

without requiring a page reload.

---

# 73. RESET

Provide a clear:

```text
New Image
```

or:

```text
Reset
```

action.

Reset must:

* Clear current image
* Clear current result
* Cancel active job where possible
* Delete temporary server job
* Return UI to upload state

---

# 74. DOWNLOAD LIFECYCLE

Preferred sequence:

```text
Job complete
 ↓
Result available
 ↓
User clicks Download
 ↓
Server streams result
 ↓
Server schedules/deletes result
```

Even if deletion after download fails, TTL cleanup must eventually remove the file.

---

# 75. NO PERMANENT USER HISTORY

After:

```text
refresh
```

or:

```text
new browser session
```

the application should show the empty upload state.

No previous user image should be restored.

---

# 76. README REQUIREMENTS

README must explain:

1. What the application does
2. Architecture
3. Local setup
4. Docker setup
5. Model setup
6. Environment variables
7. Testing
8. Production deployment
9. CPU requirements
10. Privacy/data lifecycle
11. Troubleshooting

Include exact commands.

---

# 77. DECISIONS DOCUMENT

Create:

```text
DECISIONS.md
```

Record fixed decisions:

```text
DDColor-Tiny
RealESRGAN_x2plus
RealESRGAN_x4plus
ONNX Runtime CPU
FastAPI
React + TypeScript
Docker
Ephemeral filesystem
No persistent user image storage
Asynchronous AI jobs
```

Claude Code must not silently replace these decisions.

---

# 78. IMPLEMENTATION WORKFLOW

Implement in this order:

## Phase 1

Project scaffolding.

* Repository structure
* Docker
* Frontend
* Backend
* Health endpoint

## Phase 2

Basic image functionality.

* Upload
* Preview
* Crop
* Resize
* Download
* Reset

## Phase 3

Job infrastructure.

* Job model
* Temporary storage
* Job states
* Cleanup
* Polling

## Phase 4

Colorization.

* DDColor-Tiny
* ONNX inference
* CPU execution
* API
* UI

## Phase 5

Upscaling.

* RealESRGAN x2plus
* RealESRGAN x4plus
* CPU inference
* Memory protection
* UI

## Phase 6

Before/after viewer.

## Phase 7

Security and rate limiting.

## Phase 8

Testing.

## Phase 9

UX polish.

## Phase 10

Production Docker validation.

---

# 79. IMPLEMENTATION RULE

Do not jump directly into writing large amounts of code.

For each phase:

```text
Implement
 ↓
Run tests
 ↓
Run application
 ↓
Verify behavior
 ↓
Fix issues
 ↓
Proceed
```

Do not accumulate untested functionality across phases.

---

# 80. ACCEPTANCE CRITERIA

The application is considered complete only when a user can perform:

### Flow A — Basic editing

```text
Upload JPEG
→ Crop
→ Resize
→ Download
```

### Flow B — Colorization

```text
Upload grayscale image
→ Colorize
→ Wait asynchronously
→ View before/after
→ Download
```

### Flow C — 2×

```text
Upload image
→ Select 2×
→ Process
→ Output dimensions exactly 2×
→ Download
```

### Flow D — 4×

```text
Upload image
→ Select 4×
→ Process
→ Output dimensions exactly 4×
→ Download
```

### Flow E — Abandoned job

```text
Upload
→ Start processing
→ Close browser
→ Wait for TTL
→ Temporary files removed
```

### Flow F — Refresh

```text
Upload
→ Refresh
→ Empty upload state
```

No previous image should appear.

---

# 81. FINAL PRODUCT REQUIREMENT

The final application should feel like:

> **A fast, polished, privacy-conscious image utility that happens to run expensive AI processing on a CPU server.**

The user should NOT feel:

> "I'm waiting for a Python backend."

The asynchronous architecture, immediate previews, clear progress states, responsive UI, and clean before/after experience must hide the underlying CPU limitations as much as realistically possible.

---

# 82. CLAUDE CODE EXECUTION INSTRUCTION

You are the implementation engineer.

Treat this document as the authoritative product and technical specification.

Do not:

* Re-open already-set technology decisions.
* Replace the selected AI models.
* Add unnecessary features.
* Introduce unnecessary infrastructure.
* Store user images permanently.
* Ask the user to make routine architectural decisions.
* Leave TODO placeholders for core functionality.
* Claim functionality is complete without testing it.

You MAY make minor implementation decisions where this specification intentionally leaves details open, provided they:

1. Preserve the requirements.
2. Prefer simplicity.
3. Preserve security.
4. Preserve UX quality.
5. Do not introduce unnecessary dependencies.

When an implementation detail is genuinely ambiguous and materially affects the architecture, document the decision in `DECISIONS.md` before implementing it.

At the end of every implementation phase:

```text
1. Run tests.
2. Run lint/type checks.
3. Build containers.
4. Start the application.
5. Verify the relevant user flow.
6. Fix discovered issues.
7. Update documentation.
8. Only then continue.
```

The final output must be a fully runnable Dockerized application, not a prototype mockup.
