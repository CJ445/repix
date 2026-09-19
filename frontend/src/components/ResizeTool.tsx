import { useState } from 'react'
import type { EditorImage } from '../state/types'

interface Props {
  image: EditorImage
  onApply: (width: number, height: number) => void
}

const PRESETS = [25, 50, 75, 100]

export default function ResizeTool({ image, onApply }: Props) {
  const [width, setWidth] = useState(image.width)
  const [height, setHeight] = useState(image.height)
  const [lockAspect, setLockAspect] = useState(true)
  const ratio = image.width / image.height

  const setW = (w: number) => {
    setWidth(w)
    if (lockAspect) setHeight(Math.round(w / ratio))
  }
  const setH = (h: number) => {
    setHeight(h)
    if (lockAspect) setWidth(Math.round(h * ratio))
  }

  const applyPreset = (pct: number) => {
    const w = Math.max(1, Math.round((image.width * pct) / 100))
    const h = Math.max(1, Math.round((image.height * pct) / 100))
    setWidth(w)
    setHeight(h)
  }

  const invalid = width < 1 || height < 1 || width > image.width || height > image.height

  return (
    <div className="flex flex-col gap-4">
      <div className="flex gap-2">
        {PRESETS.map((p) => (
          <button
            key={p}
            onClick={() => applyPreset(p)}
            className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm text-neutral-700 hover:bg-neutral-100 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
          >
            {p}%
          </button>
        ))}
      </div>
      <div className="flex items-end gap-3">
        <label className="flex flex-col gap-1 text-sm text-neutral-600 dark:text-neutral-400">
          Width
          <input
            type="number"
            value={width}
            min={1}
            max={image.width}
            onChange={(e) => setW(Number(e.target.value))}
            className="w-28 rounded-md border border-neutral-300 px-2 py-1.5 dark:border-neutral-700 dark:bg-neutral-900"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-neutral-600 dark:text-neutral-400">
          Height
          <input
            type="number"
            value={height}
            min={1}
            max={image.height}
            onChange={(e) => setH(Number(e.target.value))}
            className="w-28 rounded-md border border-neutral-300 px-2 py-1.5 dark:border-neutral-700 dark:bg-neutral-900"
          />
        </label>
      </div>
      <label className="flex items-center gap-2 text-sm text-neutral-600 dark:text-neutral-400">
        <input
          type="checkbox"
          checked={lockAspect}
          onChange={(e) => setLockAspect(e.target.checked)}
        />
        Lock aspect ratio
      </label>
      {invalid && (
        <p className="text-xs text-red-600 dark:text-red-400">
          Dimensions must be between 1 and the original size ({image.width}×{image.height}).
        </p>
      )}
      <button
        disabled={invalid}
        onClick={() => onApply(width, height)}
        className="w-fit rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-40 dark:bg-neutral-100 dark:text-neutral-900"
      >
        Apply Resize
      </button>
    </div>
  )
}
