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

export type ExportFormat = 'png' | 'jpeg' | 'webp'

export const EXPORT_FORMATS: { id: ExportFormat; label: string; mime: string; ext: string }[] = [
  { id: 'png', label: 'PNG', mime: 'image/png', ext: 'png' },
  { id: 'jpeg', label: 'JPG', mime: 'image/jpeg', ext: 'jpg' },
  { id: 'webp', label: 'WebP', mime: 'image/webp', ext: 'webp' },
]

export class UnsupportedFormatError extends Error {}

/**
 * Encode an image blob into the requested format at full resolution.
 * `quality` (0-1) only applies to JPEG and WebP. JPEG has no alpha channel, so
 * transparent areas are flattened onto white.
 */
export async function encodeImage(
  source: Blob,
  format: ExportFormat,
  quality = 0.92
): Promise<Blob> {
  const target = EXPORT_FORMATS.find((f) => f.id === format)!
  if (format === 'png' && source.type === 'image/png') return source

  const bitmap = await createImageBitmap(source)
  try {
    const canvas = document.createElement('canvas')
    canvas.width = bitmap.width
    canvas.height = bitmap.height
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('Canvas not supported')
    if (format === 'jpeg') {
      ctx.fillStyle = '#fff'
      ctx.fillRect(0, 0, canvas.width, canvas.height)
    }
    ctx.drawImage(bitmap, 0, 0)
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, target.mime, quality)
    )
    // Browsers silently fall back to PNG for formats they can't encode (e.g. WebP on Safari).
    if (!blob || blob.type !== target.mime) throw new UnsupportedFormatError(target.label)
    return blob
  } finally {
    bitmap.close()
  }
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(bytes < 10 * 1024 * 1024 ? 2 : 1)} MB`
}

export async function readImageSize(blob: Blob): Promise<{ width: number; height: number }> {
  const bitmap = await createImageBitmap(blob)
  const size = { width: bitmap.width, height: bitmap.height }
  bitmap.close()
  return size
}

/** Filename like `photo-colorized-cropped.png`; long edit chains collapse to `-edited`. */
export function buildDownloadFilename(
  baseName: string,
  operations: string | string[],
  extension: string
): string {
  const stem = baseName.replace(/\.[^./]+$/, '') || 'photo'
  const ops = (Array.isArray(operations) ? operations : [operations]).filter(Boolean)
  const suffix = ops.length === 0 ? 'edited' : ops.length > 3 ? 'edited' : ops.join('-')
  return `${stem}-${suffix}.${extension}`
}
