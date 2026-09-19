import { useEffect, useState } from 'react'
import Modal from './Modal'
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
    <Modal titleId="download-title" onClose={onClose}>
      <h2 id="download-title" className="text-lg font-semibold">
        Download Image
      </h2>
      <p className="mt-1 text-ink-2">
        {width} × {height} px. Sizes below are measured from the actual files.
      </p>

      <div role="radiogroup" aria-label="File format" className="mt-4 flex flex-col gap-2">
        {EXPORT_FORMATS.map((f) => {
          const state = encoded[f.id]
          const disabled = state.status === 'unavailable'
          return (
            <label
              key={f.id}
              className={`flex min-h-14 cursor-pointer items-center justify-between gap-3 rounded-lg border px-4 py-2 transition-colors has-[:checked]:border-ink has-[:checked]:bg-sunken ${
                disabled ? 'cursor-not-allowed border-line opacity-60' : 'border-edge hover:bg-sunken'
              }`}
            >
              <span className="flex items-center gap-3">
                <input
                  type="radio"
                  name="format"
                  value={f.id}
                  checked={format === f.id}
                  disabled={disabled}
                  onChange={() => setFormat(f.id)}
                  className="h-5 w-5 accent-[var(--ink)]"
                />
                <span className="font-medium">{f.label}</span>
              </span>
              <span className="text-right text-ink-2">
                {state.status === 'pending' && 'Measuring…'}
                {state.status === 'unavailable' && 'Not supported by this browser'}
                {state.status === 'ready' && <strong className="font-semibold text-ink">{formatFileSize(state.blob.size)}</strong>}
              </span>
            </label>
          )
        })}
      </div>

      {format !== 'png' && (
        <label className="mt-4 flex flex-col gap-1">
          <span className="flex justify-between text-ink-2">
            Quality <span>{quality}%</span>
          </span>
          <input
            type="range"
            min={50}
            max={100}
            value={quality}
            onChange={(e) => setQuality(Number(e.target.value))}
            className="h-11 w-full accent-[var(--ink)] md:h-7"
          />
        </label>
      )}

      <div className="mt-6 flex justify-end gap-2">
        <button data-autofocus onClick={onClose} className="btn btn-secondary">
          Cancel
        </button>
        <button onClick={handleDownload} disabled={selected.status !== 'ready'} className="btn btn-primary">
          Download {selectedMeta.label}
        </button>
      </div>
    </Modal>
  )
}
