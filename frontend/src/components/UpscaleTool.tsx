import type { EditorImage } from '../state/types'

interface Props {
  image: EditorImage
  onStart: (scale: 2 | 4) => void
  disabled: boolean
  maxOutputPixels: number
}

export default function UpscaleTool({ image, onStart, disabled, maxOutputPixels }: Props) {
  const options: { scale: 2 | 4 }[] = [{ scale: 2 }, { scale: 4 }]

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-neutral-600 dark:text-neutral-400">
        {image.width} × {image.height} px original
      </p>
      <div className="flex gap-3">
        {options.map(({ scale }) => {
          const outW = image.width * scale
          const outH = image.height * scale
          const exceeds = outW * outH > maxOutputPixels
          return (
            <button
              key={scale}
              disabled={disabled || exceeds}
              onClick={() => onStart(scale)}
              title={exceeds ? 'Output would exceed the maximum supported size' : undefined}
              className="flex flex-col items-center gap-1 rounded-lg border border-neutral-300 px-4 py-3 text-sm hover:bg-neutral-100 disabled:cursor-not-allowed disabled:opacity-40 dark:border-neutral-700 dark:hover:bg-neutral-800"
            >
              <span className="text-base font-semibold">{scale}×</span>
              <span className="text-xs text-neutral-500">
                {outW} × {outH}
              </span>
              {exceeds && <span className="text-xs text-red-500">Too large</span>}
            </button>
          )
        })}
      </div>
    </div>
  )
}
