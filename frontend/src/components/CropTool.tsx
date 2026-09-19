import ReactCrop from 'react-image-crop'
import 'react-image-crop/dist/ReactCrop.css'
import type { EditorImage } from '../state/types'
import type { CropController, PixelCrop } from '../state/useCrop'

const ASPECTS: { label: string; value: number | undefined }[] = [
  { label: 'Free', value: undefined },
  { label: '1:1', value: 1 },
  { label: '4:3', value: 4 / 3 },
  { label: '3:2', value: 3 / 2 },
  { label: '16:9', value: 16 / 9 },
]

/** The image with crop handles: lives in the editor's stage. */
export function CropStage({ image, crop }: { image: EditorImage; crop: CropController }) {
  return (
    <ReactCrop crop={crop.crop} onChange={(_, percentCrop) => crop.setCrop(percentCrop)} aspect={crop.aspect}>
      <img
        src={image.url}
        alt={image.name}
        onLoad={(e) => {
          const el = e.currentTarget
          crop.setImgEl(el)
          crop.applyAspect(undefined, el)
        }}
        className="max-h-[45vh] w-auto md:max-h-[62vh]"
      />
    </ReactCrop>
  )
}

/** Ratio chips and actions: lives in the editor's side panel, like every other tool. */
export function CropPanel({
  crop,
  onApply,
}: {
  crop: CropController
  onApply: (px: PixelCrop) => void
}) {
  const px = crop.toPixels()
  return (
    <div className="flex flex-col gap-4">
      <div role="group" aria-label="Aspect ratio" className="flex flex-wrap gap-2">
        {ASPECTS.map((a) => (
          <button
            key={a.label}
            type="button"
            aria-pressed={crop.aspect === a.value}
            onClick={() => crop.applyAspect(a.value)}
            className="chip"
          >
            {a.label}
          </button>
        ))}
      </div>
      {px && (
        <p className="note">
          Selection: {px.width} × {px.height} px
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <button disabled={!px} onClick={() => px && onApply(px)} className="btn btn-primary">
          Apply Crop
        </button>
        <button onClick={() => crop.applyAspect(undefined)} className="btn btn-secondary">
          Reset Selection
        </button>
      </div>
    </div>
  )
}
