import { useState } from 'react'
import type { EditorImage } from '../state/types'
import {
  DEFAULT_DPI,
  MAX_DPI,
  MIN_DPI,
  UNITS,
  formatUnit,
  fromPx,
  isValidDpi,
  toPx,
  type Unit,
} from '../utils/units'

interface Props {
  image: EditorImage
  onApply: (width: number, height: number) => void
}

const PRESETS = [25, 50, 75, 100]

const presetSize = (image: EditorImage, pct: number) => ({
  width: Math.max(1, Math.round((image.width * pct) / 100)),
  height: Math.max(1, Math.round((image.height * pct) / 100)),
})

const parse = (s: string) => (s.trim() === '' ? NaN : Number(s))

/** Whole pixels for a typed length, or NaN if it (or the DPI it needs) isn't a usable number. */
function pxFrom(text: string, unit: Unit, dpi: number): number {
  const n = parse(text)
  if (!Number.isFinite(n) || (unit !== 'px' && !isValidDpi(dpi))) return NaN
  return Math.round(toPx(n, unit, dpi))
}

/** Text for a pixel length in `unit`; empty when it can't be shown. */
function show(px: number, unit: Unit, dpi: number): string {
  if (!Number.isFinite(px) || (unit !== 'px' && !isValidDpi(dpi))) return ''
  return formatUnit(fromPx(px, unit, dpi), unit)
}

export default function ResizeTool({ image, onApply }: Props) {
  // The pixel size is the source of truth (the saved file stores pixels only); the fields are the
  // same size shown in `unit`, held as strings so one can be cleared while typing a new value.
  const [px, setPx] = useState({ w: image.width, h: image.height })
  const [unit, setUnit] = useState<Unit>('px')
  const [dpiText, setDpiText] = useState(String(DEFAULT_DPI))
  const [width, setWidth] = useState(String(image.width))
  const [height, setHeight] = useState(String(image.height))
  const [lockAspect, setLockAspect] = useState(true)
  const ratio = image.width / image.height
  const dpi = parse(dpiText)
  const physical = unit !== 'px'

  const setW = (v: string) => {
    setWidth(v)
    const w = pxFrom(v, unit, dpi)
    if (lockAspect && Number.isFinite(w)) {
      const h = Math.max(1, Math.round(w / ratio))
      setHeight(show(h, unit, dpi))
      setPx({ w, h })
    } else {
      setPx((p) => ({ ...p, w }))
    }
  }
  const setH = (v: string) => {
    setHeight(v)
    const h = pxFrom(v, unit, dpi)
    if (lockAspect && Number.isFinite(h)) {
      const w = Math.max(1, Math.round(h * ratio))
      setWidth(show(w, unit, dpi))
      setPx({ w, h })
    } else {
      setPx((p) => ({ ...p, h }))
    }
  }

  const applyPreset = (pct: number) => {
    const size = presetSize(image, pct)
    setPx({ w: size.width, h: size.height })
    setWidth(show(size.width, unit, dpi))
    setHeight(show(size.height, unit, dpi))
  }

  /** Same pixel size, shown in the new unit. */
  const changeUnit = (next: Unit) => {
    setUnit(next)
    setWidth(show(px.w, next, dpi))
    setHeight(show(px.h, next, dpi))
  }

  /** DPI only converts units: the pixel size stays put and the displayed lengths follow. */
  const changeDpi = (text: string) => {
    setDpiText(text)
    const next = parse(text)
    if (!physical || !isValidDpi(next)) return
    const w = Number.isFinite(px.w) ? px.w : pxFrom(width, unit, next)
    const h = Number.isFinite(px.h) ? px.h : pxFrom(height, unit, next)
    setPx({ w, h })
    setWidth(Number.isFinite(px.w) ? show(w, unit, next) : width)
    setHeight(Number.isFinite(px.h) ? show(h, unit, next) : height)
  }

  const w = px.w
  const h = px.h
  const empty = Number.isNaN(w) || Number.isNaN(h)
  const outOfRange = !empty && (w < 1 || h < 1 || w > image.width || h > image.height)
  const unchanged = !empty && w === image.width && h === image.height
  const dpiInvalid = physical && !isValidDpi(dpi)
  // Derived from the size, so typing a custom value clears the highlight.
  const activePreset = PRESETS.find((p) => {
    const size = presetSize(image, p)
    return size.width === w && size.height === h
  })
  const fieldProps = physical
    ? ({ inputMode: 'decimal', step: 'any', min: 0 } as const)
    : ({ inputMode: 'numeric', min: 1 } as const)

  return (
    <div className="flex flex-col gap-4">
      <div role="group" aria-label="Scale presets" className="flex flex-wrap gap-2">
        {PRESETS.map((p) => (
          <button
            key={p}
            type="button"
            aria-pressed={activePreset === p}
            onClick={() => applyPreset(p)}
            className="chip"
          >
            {p}%
          </button>
        ))}
      </div>
      <div className="flex items-end gap-3">
        <label className="flex flex-col gap-1 text-ink-2">
          Unit
          <select value={unit} onChange={(e) => changeUnit(e.target.value as Unit)} className="field w-44">
            {UNITS.map((u) => (
              <option key={u.id} value={u.id}>
                {u.label}
              </option>
            ))}
          </select>
        </label>
        {physical && (
          <label className="flex flex-col gap-1 text-ink-2">
            Resolution (DPI)
            <input
              type="number"
              inputMode="numeric"
              value={dpiText}
              min={MIN_DPI}
              max={MAX_DPI}
              onChange={(e) => changeDpi(e.target.value)}
              className="field w-28"
            />
          </label>
        )}
      </div>
      <div className="flex items-end gap-3">
        <label className="flex flex-col gap-1 text-ink-2">
          Width ({unit})
          <input
            type="number"
            {...fieldProps}
            value={width}
            max={physical ? undefined : image.width}
            onChange={(e) => setW(e.target.value)}
            className="field w-28"
          />
        </label>
        <label className="flex flex-col gap-1 text-ink-2">
          Height ({unit})
          <input
            type="number"
            {...fieldProps}
            value={height}
            max={physical ? undefined : image.height}
            onChange={(e) => setH(e.target.value)}
            className="field w-28"
          />
        </label>
      </div>
      {physical && (
        <p className="note">
          {empty || dpiInvalid ? (
            'Enter a size and a resolution.'
          ) : (
            <>
              Result: {w} × {h} px. Units convert to pixels at this resolution; the saved file stores pixels, not DPI.
            </>
          )}
        </p>
      )}
      <label className="-my-1 flex min-h-11 items-center gap-3 text-ink-2 md:min-h-8">
        <input
          type="checkbox"
          checked={lockAspect}
          onChange={(e) => setLockAspect(e.target.checked)}
          className="h-5 w-5 accent-[var(--ink)]"
        />
        Lock aspect ratio
      </label>
      {dpiInvalid && (
        <p role="alert" className="note text-danger">
          Enter a resolution from {MIN_DPI} to {MAX_DPI} DPI.
        </p>
      )}
      {outOfRange && (
        <p role="alert" className="note text-danger">
          {physical && !dpiInvalid
            ? `Enter sizes up to the current size: ${show(image.width, unit, dpi)} × ${show(image.height, unit, dpi)} ${unit} at ${dpi} DPI (${image.width} × ${image.height} px). Use Upscale to go larger.`
            : `Enter sizes from 1 px up to the current size (${image.width} × ${image.height} px). Use Upscale to go larger.`}
        </p>
      )}
      <button
        disabled={empty || dpiInvalid || outOfRange || unchanged}
        onClick={() => onApply(w, h)}
        className="btn btn-primary w-fit"
      >
        Apply Resize
      </button>
    </div>
  )
}
