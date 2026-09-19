import type { EditorImage } from '../state/types'

export const ACCEPTED_MIME_TYPES = ['image/jpeg', 'image/png', 'image/webp']

export function isSupportedImage(file: File): boolean {
  return ACCEPTED_MIME_TYPES.includes(file.type)
}

export function loadEditorImage(file: File): Promise<EditorImage> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => {
      resolve({
        url,
        blob: file,
        width: img.naturalWidth,
        height: img.naturalHeight,
        name: file.name,
        mimeType: file.type,
      })
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('Unable to read image'))
    }
    img.src = url
  })
}

export function revokeEditorImage(image: EditorImage | null | undefined) {
  if (image) URL.revokeObjectURL(image.url)
}

/** Crop a source blob using pixel coordinates (relative to full-res image) and return a new blob. */
export async function cropImageBlob(
  source: EditorImage,
  crop: { x: number; y: number; width: number; height: number },
  mimeType = source.mimeType
): Promise<Blob> {
  const bitmap = await createImageBitmap(source.blob)
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(crop.width))
  canvas.height = Math.max(1, Math.round(crop.height))
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Canvas not supported')
  ctx.drawImage(
    bitmap,
    crop.x,
    crop.y,
    crop.width,
    crop.height,
    0,
    0,
    canvas.width,
    canvas.height
  )
  return await canvasToBlob(canvas, mimeType)
}

export async function resizeImageBlob(
  source: EditorImage,
  width: number,
  height: number,
  mimeType = source.mimeType
): Promise<Blob> {
  const bitmap = await createImageBitmap(source.blob)
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(width))
  canvas.height = Math.max(1, Math.round(height))
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Canvas not supported')
  ctx.imageSmoothingEnabled = true
  ctx.imageSmoothingQuality = 'high'
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  return await canvasToBlob(canvas, mimeType)
}

function canvasToBlob(canvas: HTMLCanvasElement, mimeType: string): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error('Failed to encode image'))),
      mimeType,
      0.95
    )
  })
}

export function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export function buildDownloadFilename(
  baseName: string,
  operation: 'colorized' | 'upscaled-2x' | 'upscaled-4x' | 'edited',
  extension: string
): string {
  const stem = baseName.replace(/\.[^./]+$/, '') || 'photo'
  return `${stem}-${operation}.${extension}`
}
