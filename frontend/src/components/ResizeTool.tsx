import { useState } from 'react'
import type { EditorImage } from '../state/types'

interface Props {
  image: EditorImage
  onApply: (width: number, height: number) => void
}

const PRESETS = [25, 50, 75, 100]

const parse = (s: string) => (s.trim() === '' ? NaN : Number(s))

export default function ResizeTool({ image, onApply }: Props) {
  // Held as strings so a field can be cleared while typing a new value.
  const [width, setWidth] = useState(String(image.width))
  const [height, setHeight] = useState(String(image.height))
  const [lockAspect, setLockAspect] = useState(true)
  const ratio = image.width / image.height

  const setW = (v: string) => {
    setWidth(v)
    const n = parse(v)
    if (lockAspect && Number.isFinite(n)) setHeight(String(Math.max(1, Math.round(n / ratio))))
  }
  const setH = (v: string) => {
    setHeight(v)
    const n = parse(v)
    if (lockAspect && Number.isFinite(n)) setWidth(String(Math.max(1, Math.round(n * ratio))))
  }

  const applyPreset = (pct: number) => {
    setWidth(String(Math.max(1, Math.round((image.width * pct) / 100))))
    setHeight(String(Math.max(1, Math.round((image.height * pct) / 100))))
  }

  const w = parse(width)
  const h = parse(height)
  const empty = Number.isNaN(w) || Number.isNaN(h)
  const outOfRange = !empty && (w < 1 || h < 1 || w > image.width || h > image.height)
  const unchanged = !empty && w === image.width && h === image.height

  return (
    <div className="flex flex-col gap-4">
      <div role="group" aria-label="Scale presets" className="flex flex-wrap gap-2">
        {PRESETS.map((p) => (
          <button key={p} type="button" onClick={() => applyPreset(p)} className="chip">
            {p}%
          </button>
        ))}
      </div>
      <div className="flex items-end gap-3">
        <label className="flex flex-col gap-1 text-ink-2">
          Width (px)
          <input
            type="number"
            inputMode="numeric"
            value={width}
            min={1}
            max={image.width}
            onChange={(e) => setW(e.target.value)}
            className="field w-28"
          />
        </label>
        <label className="flex flex-col gap-1 text-ink-2">
          Height (px)
          <input
            type="number"
            inputMode="numeric"
            value={height}
            min={1}
            max={image.height}
            onChange={(e) => setH(e.target.value)}
            className="field w-28"
          />
        </label>
      </div>
      <label className="-my-1 flex min-h-11 items-center gap-3 text-ink-2 md:min-h-8">
        <input
          type="checkbox"
          checked={lockAspect}
          onChange={(e) => setLockAspect(e.target.checked)}
          className="h-5 w-5 accent-[var(--ink)]"
        />
        Lock aspect ratio
      </label>
      {outOfRange && (
        <p role="alert" className="note text-danger">
          Enter sizes from 1 px up to the current size ({image.width} × {image.height} px). Use Upscale to go larger.
        </p>
      )}
      <button
        disabled={empty || outOfRange || unchanged}
        onClick={() => onApply(w, h)}
        className="btn btn-primary w-fit"
      >
        Apply Resize
      </button>
    </div>
  )
}
