import type { EditorImage } from '../state/types'
import ServerNote from './ServerNote'

interface Props {
  image: EditorImage
  onStart: (scale: 2 | 4) => void
  disabled: boolean
  maxOutputPixels: number
}

export default function UpscaleTool({ image, onStart, disabled, maxOutputPixels }: Props) {
  const options: { scale: 2 | 4 }[] = [{ scale: 2 }, { scale: 4 }]
  const maxMegapixels = Math.round(maxOutputPixels / 1_000_000)

  return (
    <div className="flex flex-col gap-3">
      <p className="text-ink-2">
        {image.width} × {image.height} px now. Upscaling adds detail with a model, so fine texture in the result
        may be invented rather than recovered.
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
              className="flex min-h-16 min-w-32 flex-col items-center justify-center gap-0.5 rounded-lg border border-edge px-4 py-2 enabled:hover:bg-sunken disabled:cursor-not-allowed disabled:opacity-50"
            >
              <span className="text-lg font-semibold">{scale}×</span>
              <span className="note">
                {outW} × {outH} px
              </span>
              {exceeds && <span className="note text-danger">Over {maxMegapixels} MP limit</span>}
            </button>
          )
        })}
      </div>
      <ServerNote />
    </div>
  )
}
