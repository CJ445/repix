import { useEffect, useRef, useState } from 'react'
import Dropzone from './components/Dropzone'
import CropTool from './components/CropTool'
import ResizeTool from './components/ResizeTool'
import ColorizeTool from './components/ColorizeTool'
import UpscaleTool from './components/UpscaleTool'
import CompareSlider from './components/CompareSlider'
import ProcessingStatus from './components/ProcessingStatus'
import type { EditorImage, Tool } from './state/types'
import {
  loadEditorImage,
  revokeEditorImage,
  cropImageBlob,
  resizeImageBlob,
  triggerDownload,
  buildDownloadFilename,
} from './utils/image'
import {
  createColorizeJob,
  createUpscaleJob,
  deleteJob,
  pollJobUntilDone,
  ApiError,
} from './services/api'

const MAX_OUTPUT_PIXELS = 50_000_000
const POLL_INTERVAL_MS = 1500

type Phase = 'upload' | 'edit' | 'processing' | 'result' | 'failed'

export default function App() {
  const [phase, setPhase] = useState<Phase>('upload')
  const [image, setImage] = useState<EditorImage | null>(null)
  const [tool, setTool] = useState<Tool>('crop')
  const [resultUrl, setResultUrl] = useState<string | null>(null)
  const [resultBlob, setResultBlob] = useState<Blob | null>(null)
  const [resultOp, setResultOp] = useState<'colorized' | 'upscaled-2x' | 'upscaled-4x' | null>(null)
  const [statusLabel, setStatusLabel] = useState('Preparing image…')
  const [error, setError] = useState<string | null>(null)
  const activeJobId = useRef<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    return () => {
      revokeEditorImage(image)
      if (resultUrl) URL.revokeObjectURL(resultUrl)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function handleFile(file: File) {
    try {
      const editorImage = await loadEditorImage(file)
      setImage(editorImage)
      setPhase('edit')
      setTool('crop')
    } catch {
      setError('Unable to read that image. Please try a different file.')
    }
  }

  function replaceImage(blob: Blob) {
    if (!image) return
    const url = URL.createObjectURL(blob)
    revokeEditorImage(image)
    const el = new window.Image()
    el.onload = () => {
      setImage({
        url,
        blob,
        width: el.naturalWidth,
        height: el.naturalHeight,
        name: image.name,
        mimeType: blob.type || image.mimeType,
      })
    }
    el.src = url
  }

  async function handleCropApply(px: { x: number; y: number; width: number; height: number }) {
    if (!image) return
    const blob = await cropImageBlob(image, px)
    replaceImage(blob)
  }

  async function handleResizeApply(w: number, h: number) {
    if (!image) return
    const blob = await resizeImageBlob(image, w, h)
    replaceImage(blob)
  }

  async function runAiJob(kind: 'colorize' | 'upscale', scale?: 2 | 4) {
    if (!image) return
    setError(null)
    setPhase('processing')
    setStatusLabel('Preparing image…')
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const job =
        kind === 'colorize'
          ? await createColorizeJob(image.blob, image.name)
          : await createUpscaleJob(image.blob, image.name, scale!)
      activeJobId.current = job.job_id
      setStatusLabel('Processing image…')
      const finalJob = await pollJobUntilDone(
        job.job_id,
        POLL_INTERVAL_MS,
        (j) => {
          if (j.status === 'processing') setStatusLabel('Running AI model…')
        },
        controller.signal
      )
      if (finalJob.status === 'completed' && finalJob.download_url) {
        setStatusLabel('Encoding result…')
        const res = await fetch(finalJob.download_url)
        const blob = await res.blob()
        const url = URL.createObjectURL(blob)
        setResultUrl(url)
        setResultBlob(blob)
        setResultOp(kind === 'colorize' ? 'colorized' : scale === 4 ? 'upscaled-4x' : 'upscaled-2x')
        setPhase('result')
      } else {
        setError(finalJob.error_message ?? "We couldn't process this image. Please try again.")
        setPhase('failed')
      }
    } catch (err) {
      if (!(err instanceof Error && err.message === 'cancelled')) {
        setError(err instanceof ApiError ? err.message : "We couldn't process this image. Please try a smaller image or try again.")
        setPhase('failed')
      }
    } finally {
      activeJobId.current = null
    }
  }

  function cancelJob() {
    abortRef.current?.abort()
    if (activeJobId.current) deleteJob(activeJobId.current)
    setPhase('edit')
  }

  function handleDownload() {
    if (!resultBlob || !image || !resultOp) return
    const ext = resultBlob.type === 'image/jpeg' ? 'jpg' : resultBlob.type === 'image/webp' ? 'webp' : 'png'
    triggerDownload(resultBlob, buildDownloadFilename(image.name, resultOp, ext))
  }

  function handleDownloadEdited() {
    if (!image) return
    const ext = image.mimeType === 'image/jpeg' ? 'jpg' : image.mimeType === 'image/webp' ? 'webp' : 'png'
    triggerDownload(image.blob, buildDownloadFilename(image.name, 'edited', ext))
  }

  function reset() {
    if (activeJobId.current) deleteJob(activeJobId.current)
    revokeEditorImage(image)
    if (resultUrl) URL.revokeObjectURL(resultUrl)
    setImage(null)
    setResultUrl(null)
    setResultBlob(null)
    setResultOp(null)
    setError(null)
    setPhase('upload')
  }

  if (phase === 'upload' || !image) {
    return (
      <div className="mx-auto flex min-h-screen max-w-5xl flex-col">
        <Dropzone onFile={handleFile} />
      </div>
    )
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col">
      <header className="flex items-center justify-between border-b border-neutral-200 px-6 py-4 dark:border-neutral-800">
        <h1 className="text-lg font-semibold">Image Lab</h1>
        <button onClick={reset} className="text-sm text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100">
          Reset
        </button>
      </header>

      <main className="flex flex-1 flex-col gap-6 px-6 py-6 md:flex-row">
        <section className="flex flex-1 items-center justify-center rounded-xl bg-neutral-50 p-4 dark:bg-neutral-900">
          {phase === 'processing' && <ProcessingStatus label={statusLabel} />}
          {phase === 'result' && resultUrl && <CompareSlider beforeUrl={image.url} afterUrl={resultUrl} />}
          {(phase === 'edit' || phase === 'failed') && tool !== 'crop' && (
            <img src={image.url} alt={image.name} className="max-h-[65vh] w-auto rounded-lg" />
          )}
          {phase === 'edit' && tool === 'crop' && (
            <CropTool image={image} onApply={handleCropApply} onCancel={() => setTool('resize')} />
          )}
        </section>

        <aside className="flex w-full flex-col gap-6 md:w-80">
          {phase === 'failed' && (
            <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
              {error}
              <button onClick={() => setPhase('edit')} className="mt-2 block font-medium underline">
                Try Again
              </button>
            </div>
          )}

          {(phase === 'edit' || phase === 'failed') && (
            <>
              <nav className="flex gap-1 rounded-lg bg-neutral-100 p-1 dark:bg-neutral-900">
                {(['crop', 'resize', 'colorize', 'upscale'] as Tool[]).map((t) => (
                  <button
                    key={t}
                    onClick={() => setTool(t)}
                    className={`flex-1 rounded-md px-2 py-1.5 text-xs font-medium capitalize transition ${
                      tool === t
                        ? 'bg-white shadow-sm dark:bg-neutral-700'
                        : 'text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200'
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </nav>

              {tool === 'resize' && <ResizeTool image={image} onApply={handleResizeApply} />}
              {tool === 'colorize' && (
                <ColorizeTool onStart={() => runAiJob('colorize')} disabled={false} />
              )}
              {tool === 'upscale' && (
                <UpscaleTool
                  image={image}
                  onStart={(scale) => runAiJob('upscale', scale)}
                  disabled={false}
                  maxOutputPixels={MAX_OUTPUT_PIXELS}
                />
              )}
            </>
          )}

          {phase === 'processing' && (
            <button
              onClick={cancelJob}
              className="rounded-lg border border-neutral-300 px-4 py-2 text-sm font-medium text-neutral-700 hover:bg-neutral-100 dark:border-neutral-700 dark:text-neutral-300"
            >
              Cancel
            </button>
          )}

          {phase === 'result' && (
            <button onClick={() => setPhase('edit')} className="text-sm text-neutral-500 underline">
              Back to editing
            </button>
          )}
        </aside>
      </main>

      <footer className="border-t border-neutral-200 px-6 py-4 dark:border-neutral-800">
        <button
          onClick={phase === 'result' ? handleDownload : handleDownloadEdited}
          className="w-full rounded-lg bg-neutral-900 py-3 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-40 dark:bg-neutral-100 dark:text-neutral-900 md:w-auto md:px-8"
        >
          Download Image
        </button>
      </footer>
    </div>
  )
}
