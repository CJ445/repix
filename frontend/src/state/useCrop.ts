import { useCallback, useState } from 'react'
import { centerCrop, makeAspectCrop, type Crop } from 'react-image-crop'
import type { EditorImage } from './types'

export interface PixelCrop {
  x: number
  y: number
  width: number
  height: number
}

/**
 * Crop selection shared by the crop stage (image + handles) and the crop panel
 * (ratios + Apply), which live in different columns of the editor.
 */
export function useCrop(image: EditorImage | null) {
  const [aspect, setAspect] = useState<number | undefined>(undefined)
  const [crop, setCrop] = useState<Crop>()
  const [imgEl, setImgEl] = useState<HTMLImageElement | null>(null)

  const applyAspect = useCallback(
    (value: number | undefined, el: HTMLImageElement | null = imgEl) => {
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
    },
    [imgEl]
  )

  /** The selection in full-resolution image pixels, or null if there isn't one yet. */
  const toPixels = useCallback((): PixelCrop | null => {
    if (!crop || !imgEl || !image || !crop.width || !crop.height) return null
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
    return {
      x: Math.round(px.x * scaleX),
      y: Math.round(px.y * scaleY),
      width: Math.round(px.width * scaleX),
      height: Math.round(px.height * scaleY),
    }
  }, [crop, imgEl, image])

  return { aspect, crop, setCrop, setImgEl, applyAspect, toPixels }
}

export type CropController = ReturnType<typeof useCrop>
