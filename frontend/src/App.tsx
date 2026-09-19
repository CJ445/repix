import { useEffect, useRef, useState } from 'react'
import Dropzone from './components/Dropzone'
import { CropStage, CropPanel } from './components/CropTool'
import ResizeTool from './components/ResizeTool'
import ColorizeTool from './components/ColorizeTool'
import UpscaleTool from './components/UpscaleTool'
import DownloadDialog from './components/DownloadDialog'
import ConfirmDialog from './components/ConfirmDialog'
import CompareSlider from './components/CompareSlider'
import ProcessingStatus from './components/ProcessingStatus'
import ToolTabs from './components/ToolTabs'
import { TOOL_PANEL_ID, toolTabId } from './components/toolIds'
import Logo from './components/Logo'
import type { Tool } from './state/types'
import * as H from './state/history'
import { useCrop, type PixelCrop } from './state/useCrop'
import { loadEditorImage, cropImageBlob, resizeImageBlob, readImageSize } from './utils/image'
import {
  createColorizeJob,
  createUpscaleJob,
  deleteJob,
  pollJobUntilDone,
  ApiError,
} from './services/api'

const MAX_OUTPUT_PIXELS = 50_000_000
const POLL_INTERVAL_MS = 1500
const STAGE_IMG = 'max-h-[45vh] w-auto rounded-lg md:max-h-[62vh]'

type Phase = 'upload' | 'edit' | 'processing' | 'result' | 'failed'
type ResultOp = 'colorized' | 'upscaled-2x' | 'upscaled-4x'
interface AiResult {
  url: string
  blob: Blob
  op: ResultOp
  width: number
  height: number
}

export default function App() {
  const [phase, setPhase] = useState<Phase>('upload')
  const [history, setHistory] = useState<H.History | null>(null)
  const [tool, setTool] = useState<Tool>('crop')
  const [result, setResult] = useState<AiResult | null>(null)
  const [showDownload, setShowDownload] = useState(false)
  const [confirmNew, setConfirmNew] = useState(false)
  const [statusLabel, setStatusLabel] = useState('Uploading image…')
  const [progress, setProgress] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const activeJobId = useRef<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const lastJob = useRef<{ kind: 'colorize' | 'upscale'; scale?: 2 | 4 } | null>(null)
  const trackedUrls = useRef(new Set<string>())

  const image = history?.present.image ?? null
  const crop = useCrop(image)

  // Object URLs live exactly as long as some undo step or the pending result needs them.
  useEffect(() => {
    const live = history ? H.liveUrls(history) : new Set<string>()
    if (result) live.add(result.url)
    for (const url of trackedUrls.current) {
      if (!live.has(url)) {
        URL.revokeObjectURL(url)
        trackedUrls.current.delete(url)
      }
    }
    for (const url of live) trackedUrls.current.add(url)
  }, [history, result])

  useEffect(() => {
    const tracked = trackedUrls.current
    return () => {
      for (const url of tracked) URL.revokeObjectURL(url)
      tracked.clear()
    }
  }, [])

  const editable = phase === 'edit' || phase === 'failed'
  const canUndo = editable && !!history && history.past.length > 0
  const canRedo = editable && !!history && history.future.length > 0
  const canRevert = editable && !!history && history.present !== history.original

  const undo = () => setHistory((h) => (h ? H.undo(h) : h))
  const redo = () => setHistory((h) => (h ? H.redo(h) : h))
  const revert = () => setHistory((h) => (h ? H.revert(h) : h))

  // Cmd/Ctrl+Z, Shift+Cmd/Ctrl+Z and Ctrl+Y, except inside form fields (which have their own undo).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || showDownload || confirmNew) return
      const target = e.target as HTMLElement | null
      if (target && (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable)) return
      const key = e.key.toLowerCase()
      if (key === 'z' && !e.shiftKey && canUndo) {
        e.preventDefault()
        undo()
      } else if (((key === 'z' && e.shiftKey) || key === 'y') && canRedo) {
        e.preventDefault()
        redo()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [canUndo, canRedo, showDownload, confirmNew])

  /** Throws if the file can't be decoded; the dropzone shows the message. */
  async function handleFile(file: File) {
    const editorImage = await loadEditorImage(file)
    setHistory(H.createHistory(editorImage))
    setPhase('edit')
    setTool('crop')
  }

  /** Make `blob` the current working image so later edits build on it (and can be undone). */
  async function commitBlob(blob: Blob, op: string, knownUrl?: string, knownSize?: { width: number; height: number }) {
    if (!history) return
    const { width, height } = knownSize ?? (await readImageSize(blob))
    const url = knownUrl ?? URL.createObjectURL(blob)
    setHistory((h) =>
      h
        ? H.commit(h, { url, blob, width, height, name: h.present.image.name, mimeType: blob.type || h.present.image.mimeType }, op)
        : h
    )
  }

  async function handleCropApply(px: PixelCrop) {
    if (!image) return
    await commitBlob(await cropImageBlob(image, px), 'cropped')
  }

  async function handleResizeApply(w: number, h: number) {
    if (!image) return
    await commitBlob(await resizeImageBlob(image, w, h), 'resized')
  }

  async function runAiJob(kind: 'colorize' | 'upscale', scale?: 2 | 4) {
    if (!image) return
    lastJob.current = { kind, scale }
    setError(null)
    setPhase('processing')
    setStatusLabel('Uploading image…')
    setProgress(null)
    const controller = new AbortController()
    abortRef.current = controller
    const runningLabel =
      kind === 'colorize'
        ? 'Colorizing…'
        : `Upscaling to ${scale}× (${image.width * scale!} × ${image.height * scale!} px)…`
    try {
      const job =
        kind === 'colorize'
          ? await createColorizeJob(image.blob, image.name)
          : await createUpscaleJob(image.blob, image.name, scale!)
      if (controller.signal.aborted) {
        void deleteJob(job.job_id)
        return
      }
      activeJobId.current = job.job_id
      setStatusLabel(runningLabel)
      const finalJob = await pollJobUntilDone(
        job.job_id,
        POLL_INTERVAL_MS,
        (j) => {
          if (controller.signal.aborted) return
          setProgress(j.status === 'processing' ? (j.progress ?? null) : null)
          if (j.status === 'queued') {
            const ahead = (j.queue_position ?? 1) - 1
            setStatusLabel(
              ahead > 0
                ? `Waiting in the queue: ${ahead} ${ahead === 1 ? 'job' : 'jobs'} ahead of yours…`
                : 'Waiting for a free worker…'
            )
          } else if (j.status === 'processing') {
            setStatusLabel(runningLabel)
          }
        },
        controller.signal
      )
      if (finalJob.status === 'completed' && finalJob.download_url) {
        setStatusLabel('Receiving result…')
        const res = await fetch(finalJob.download_url)
        const blob = await res.blob()
        const url = URL.createObjectURL(blob)
        const size = await readImageSize(blob)
        if (controller.signal.aborted) {
          URL.revokeObjectURL(url)
          return
        }
        setResult({
          url,
          blob,
          ...size,
          op: kind === 'colorize' ? 'colorized' : scale === 4 ? 'upscaled-4x' : 'upscaled-2x',
        })
        setPhase('result')
      } else {
        setError(finalJob.error_message ?? "We couldn't process this image. Try again, or try a smaller image.")
        setPhase('failed')
      }
    } catch (err) {
      if (controller.signal.aborted) return
      setError(
        err instanceof ApiError
          ? err.message
          : "We couldn't process this image. Try a smaller image, or try again."
      )
      setPhase('failed')
    } finally {
      activeJobId.current = null
    }
  }

  function cancelJob() {
    abortRef.current?.abort()
    if (activeJobId.current) void deleteJob(activeJobId.current)
    setPhase('edit')
  }

  /** Adopt the AI result as the working image so it can be cropped, resized or processed again. */
  async function keepResult() {
    if (!result) return
    const { url, blob, op, width, height } = result
    await commitBlob(blob, op, url, { width, height })
    setResult(null)
    setTool('crop')
    setPhase('edit')
  }

  function discardResult() {
    setResult(null)
    setPhase('edit')
  }

  function reset() {
    abortRef.current?.abort()
    if (activeJobId.current) void deleteJob(activeJobId.current)
    setResult(null)
    setHistory(null)
    setError(null)
    setShowDownload(false)
    setConfirmNew(false)
    setPhase('upload')
  }

  const hasWork =
    !!history && (history.past.length > 0 || history.future.length > 0 || phase === 'result' || phase === 'processing')

  if (phase === 'upload' || !history || !image) {
    return <Dropzone onFile={handleFile} />
  }

  const downloadSource =
    phase === 'result' && result
      ? { blob: result.blob, width: result.width, height: result.height, operations: [...history.present.ops, result.op] }
      : { blob: image.blob, width: image.width, height: image.height, operations: history.present.ops }

  const shown = phase === 'result' && result ? result : image
  const resultTitle =
    result?.op === 'colorized' ? 'Colorized' : `Upscaled to ${result?.width} × ${result?.height} px`

  return (
    <div className="mx-auto flex min-h-dvh max-w-6xl flex-col">
      <header className="sticky top-0 z-10 flex items-center gap-3 border-b border-line bg-canvas px-4 py-2 md:px-6">
        <Logo />
        <h1 className="text-lg font-semibold">Repix</h1>
        <div className="ml-auto flex items-center gap-2">
          <button onClick={() => (hasWork ? setConfirmNew(true) : reset())} className="btn btn-quiet">
            New Image
          </button>
          <button onClick={() => setShowDownload(true)} disabled={phase === 'processing'} className="btn btn-primary">
            Download…
          </button>
        </div>
      </header>

      <main className="flex flex-1 flex-col gap-4 px-4 py-4 md:flex-row md:gap-6 md:px-6 md:py-6">
        <section className="flex min-w-0 flex-1 flex-col gap-3" aria-label="Image">
          <div className="flex flex-wrap items-center gap-1">
            <button
              onClick={undo}
              disabled={!canUndo}
              title={canUndo ? `Undo ${H.describeOp(history.present.op)} (Ctrl+Z)` : undefined}
              className="btn btn-quiet"
            >
              {canUndo ? `Undo ${H.describeOp(history.present.op)}` : 'Undo'}
            </button>
            <button
              onClick={redo}
              disabled={!canRedo}
              title={canRedo ? `Redo ${H.describeOp(history.future[0].op)} (Shift+Ctrl+Z)` : undefined}
              className="btn btn-quiet"
            >
              {canRedo ? `Redo ${H.describeOp(history.future[0].op)}` : 'Redo'}
            </button>
            {canRevert && (
              <button onClick={revert} className="btn btn-quiet">
                Revert to Original
              </button>
            )}
            <span className="note ml-auto pr-1">
              {shown.width} × {shown.height} px
            </span>
          </div>

          <div className="relative flex min-h-72 flex-1 items-center justify-center rounded-xl border border-line bg-surface p-3 md:p-4">
            {phase === 'processing' && (
              <>
                <img src={image.url} alt="" className={`${STAGE_IMG} opacity-30`} />
                <div className="absolute inset-0 flex items-center justify-center p-4">
                  <ProcessingStatus label={statusLabel} progress={progress} onCancel={cancelJob} />
                </div>
              </>
            )}
            {phase === 'result' && result && <CompareSlider beforeUrl={image.url} afterUrl={result.url} />}
            {editable && tool !== 'crop' && <img src={image.url} alt={image.name} className={STAGE_IMG} />}
            {editable && tool === 'crop' && <CropStage image={image} crop={crop} />}
          </div>
        </section>

        <aside className="flex w-full flex-col gap-4 md:w-80 md:shrink-0">
          {phase === 'failed' && (
            <div role="alert" className="rounded-lg border border-danger bg-danger-soft p-4">
              <p className="font-semibold text-danger">Couldn&rsquo;t process this image</p>
              <p className="mt-1">{error}</p>
              <div className="mt-3 flex gap-2">
                <button
                  onClick={() => lastJob.current && runAiJob(lastJob.current.kind, lastJob.current.scale)}
                  className="btn btn-secondary"
                >
                  Try Again
                </button>
                <button onClick={() => setPhase('edit')} className="btn btn-quiet">
                  Dismiss
                </button>
              </div>
            </div>
          )}

          {(editable || phase === 'processing') && (
            <fieldset
              disabled={phase === 'processing'}
              className="m-0 flex min-w-0 flex-col gap-4 border-0 p-0 disabled:opacity-60"
            >
              <ToolTabs tool={tool} onChange={setTool} />
              <div role="tabpanel" id={TOOL_PANEL_ID} aria-labelledby={toolTabId(tool)}>
                {tool === 'crop' && <CropPanel crop={crop} onApply={handleCropApply} />}
                {tool === 'resize' && <ResizeTool key={`${image.url}`} image={image} onApply={handleResizeApply} />}
                {tool === 'colorize' && <ColorizeTool onStart={() => runAiJob('colorize')} disabled={phase === 'processing'} />}
                {tool === 'upscale' && (
                  <UpscaleTool
                    image={image}
                    onStart={(scale) => runAiJob('upscale', scale)}
                    disabled={phase === 'processing'}
                    maxOutputPixels={MAX_OUTPUT_PIXELS}
                  />
                )}
              </div>
            </fieldset>
          )}

          {phase === 'result' && result && (
            <div className="flex flex-col gap-3">
              <h2 className="text-lg font-semibold text-accent">{resultTitle}</h2>
              <p className="text-ink-2">
                Drag the handle to compare with the original.
                {result.op === 'colorized' && ' The colors are the model’s guess, not the true original.'} Keep it
                to continue editing from this version, or save it as it is with Download.
              </p>
              <button onClick={keepResult} className="btn btn-accent">
                Keep Result
              </button>
              <button onClick={discardResult} className="btn btn-secondary">
                Discard Result
              </button>
            </div>
          )}
        </aside>
      </main>

      {showDownload && downloadSource.blob && (
        <DownloadDialog
          blob={downloadSource.blob}
          width={downloadSource.width}
          height={downloadSource.height}
          name={image.name}
          operations={downloadSource.operations}
          onClose={() => setShowDownload(false)}
        />
      )}

      {confirmNew && (
        <ConfirmDialog
          title="Start with a new image?"
          message="This clears the current image, its undo history and any result you haven't downloaded."
          confirmLabel="Discard and Start Over"
          onConfirm={reset}
          onCancel={() => setConfirmNew(false)}
        />
      )}
    </div>
  )
}
