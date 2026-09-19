import { useState } from 'react'
import ReactCrop, { type Crop, centerCrop, makeAspectCrop } from 'react-image-crop'
import 'react-image-crop/dist/ReactCrop.css'
import type { EditorImage } from '../state/types'

const ASPECTS: { label: string; value: number | undefined }[] = [
  { label: 'Free', value: undefined },
  { label: '1:1', value: 1 },
  { label: '4:3', value: 4 / 3 },
  { label: '3:2', value: 3 / 2 },
  { label: '16:9', value: 16 / 9 },
]

interface Props {
  image: EditorImage
  onApply: (pixelCrop: { x: number; y: number; width: number; height: number }) => void
  onCancel: () => void
}

export default function CropTool({ image, onApply, onCancel }: Props) {
  const [aspect, setAspect] = useState<number | undefined>(undefined)
  const [crop, setCrop] = useState<Crop>()
  const [imgEl, setImgEl] = useState<HTMLImageElement | null>(null)

  const applyAspect = (value: number | undefined, el: HTMLImageElement | null = imgEl) => {
    setAspect(value)
    if (!el) return
    if (value) {
      setCrop(
        centerCrop(
          makeAspectCrop({ unit: '%', width: 80 }, value, el.width, el.height),
          el.width,
          el.height
        )
      )
    } else {
      setCrop({ unit: '%', x: 10, y: 10, width: 80, height: 80 })
    }
  }

  const handleApply = () => {
    if (!crop || !imgEl) return
    const scaleX = image.width / imgEl.width
    const scaleY = image.height / imgEl.height
    const px =
      crop.unit === '%'
        ? {
            x: (crop.x / 100) * imgEl.width,
            y: (crop.y / 100) * imgEl.height,
            width: (crop.width / 100) * imgEl.width,
            height: (crop.height / 100) * imgEl.height,
          }
        : crop
    onApply({
      x: Math.round(px.x * scaleX),
      y: Math.round(px.y * scaleY),
      width: Math.round(px.width * scaleX),
      height: Math.round(px.height * scaleY),
    })
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2">
        {ASPECTS.map((a) => (
          <button
            key={a.label}
            onClick={() => applyAspect(a.value)}
            className={`rounded-md border px-3 py-1.5 text-sm transition ${
              aspect === a.value
                ? 'border-neutral-900 bg-neutral-900 text-white dark:border-neutral-100 dark:bg-neutral-100 dark:text-neutral-900'
                : 'border-neutral-300 text-neutral-700 hover:bg-neutral-100 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800'
            }`}
          >
            {a.label}
          </button>
        ))}
      </div>
      <ReactCrop crop={crop} onChange={(_, percentCrop) => setCrop(percentCrop)} aspect={aspect}>
        <img
          src={image.url}
          alt=""
          onLoad={(e) => {
            const el = e.currentTarget
            setImgEl(el)
            applyAspect(undefined, el)
          }}
          className="max-h-[60vh] w-auto"
        />
      </ReactCrop>
      <div className="flex gap-2">
        <button
          onClick={handleApply}
          className="rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700 dark:bg-neutral-100 dark:text-neutral-900"
        >
          Apply Crop
        </button>
        <button
          onClick={onCancel}
          className="rounded-lg border border-neutral-300 px-4 py-2 text-sm font-medium text-neutral-700 hover:bg-neutral-100 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
