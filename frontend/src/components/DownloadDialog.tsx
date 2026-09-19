import { useEffect, useRef, useState } from 'react'
import {
  EXPORT_FORMATS,
  encodeImage,
  formatFileSize,
  triggerDownload,
  buildDownloadFilename,
  type ExportFormat,
} from '../utils/image'

interface Props {
  blob: Blob
  width: number
  height: number
  name: string
  operations: string[]
  onClose: () => void
}

type Encoded = { status: 'pending' } | { status: 'ready'; blob: Blob } | { status: 'unavailable' }
// Results are tagged with the quality they were encoded at, so stale ones read as pending.
type Tagged = Encoded & { quality: number }

export default function DownloadDialog({ blob, width, height, name, operations, onClose }: Props) {
  const [format, setFormat] = useState<ExportFormat>('png')
  const [quality, setQuality] = useState(90)
  const [debouncedQuality, setDebouncedQuality] = useState(90)
  const [results, setResults] = useState<Partial<Record<ExportFormat, Tagged>>>({})
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuality(quality), 300)
    return () => clearTimeout(t)
  }, [quality])

  // Encode each format for real so the sizes shown are exactly what will be downloaded.
  // Formats are encoded one at a time to keep peak memory low on large images.
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      for (const f of EXPORT_FORMATS) {
        let result: Encoded
        try {
          result = { status: 'ready', blob: await encodeImage(blob, f.id, debouncedQuality / 100) }
        } catch {
          result = { status: 'unavailable' }
        }
        if (cancelled) return
        setResults((prev) => ({ ...prev, [f.id]: { ...result, quality: debouncedQuality } }))
      }
    })()
    return () => {
      cancelled = true
    }
  }, [blob, debouncedQuality])

  const encoded = Object.fromEntries(
    EXPORT_FORMATS.map((f) => {
      const r = results[f.id]
      return [f.id, r && r.quality === debouncedQuality ? r : { status: 'pending' }]
    })
  ) as Record<ExportFormat, Encoded>
  const selected = encoded[format]
  const selectedMeta = EXPORT_FORMATS.find((f) => f.id === format)!

  function handleDownload() {
    if (selected.status !== 'ready') return
    triggerDownload(selected.blob, buildDownloadFilename(name, operations, selectedMeta.ext))
    onClose()
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="download-title"
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl dark:bg-neutral-900"
      >
        <h2 id="download-title" className="text-base font-semibold">
          Download image
        </h2>
        <p className="mt-1 text-sm text-neutral-500">
          {width} × {height} px
        </p>

        <div role="radiogroup" aria-label="File format" className="mt-4 flex flex-col gap-2">
          {EXPORT_FORMATS.map((f) => {
            const state = encoded[f.id]
            const disabled = state.status === 'unavailable'
            return (
              <label
                key={f.id}
                className={`flex cursor-pointer items-center justify-between rounded-lg border px-4 py-3 text-sm transition ${
                  format === f.id
                    ? 'border-neutral-900 bg-neutral-50 dark:border-neutral-100 dark:bg-neutral-800'
                    : 'border-neutral-200 dark:border-neutral-700'
                } ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
              >
                <span className="flex items-center gap-3">
                  <input
                    type="radio"
                    name="format"
                    value={f.id}
                    checked={format === f.id}
                    disabled={disabled}
                    onChange={() => setFormat(f.id)}
                  />
                  <span className="font-medium">{f.label}</span>
                </span>
                <span className="text-right text-neutral-500">
                  {state.status === 'pending' && 'Calculating…'}
                  {state.status === 'unavailable' && 'Not supported by this browser'}
                  {state.status === 'ready' && (
                    <>
                      {width} × {height} · <strong>{formatFileSize(state.blob.size)}</strong>
                    </>
                  )}
                </span>
              </label>
            )
          })}
        </div>

        {format !== 'png' && (
          <label className="mt-4 flex flex-col gap-1 text-sm">
            <span className="flex justify-between text-neutral-500">
              Quality <span>{quality}%</span>
            </span>
            <input
              type="range"
              min={50}
              max={100}
              value={quality}
              onChange={(e) => setQuality(Number(e.target.value))}
            />
          </label>
        )}

        <div className="mt-6 flex justify-end gap-2">
          <button
            ref={closeRef}
            onClick={onClose}
            className="rounded-lg border border-neutral-300 px-4 py-2 text-sm font-medium dark:border-neutral-700"
          >
            Cancel
          </button>
          <button
            onClick={handleDownload}
            disabled={selected.status !== 'ready'}
            className="rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-40 dark:bg-neutral-100 dark:text-neutral-900"
          >
            Download {selectedMeta.label}
          </button>
        </div>
      </div>
    </div>
  )
}
