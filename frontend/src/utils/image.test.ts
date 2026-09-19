import { describe, expect, it } from 'vitest'
import { isSupportedImage, buildDownloadFilename } from './image'

function makeFile(type: string, name = 'photo.png'): File {
  return new File([new Uint8Array([1, 2, 3])], name, { type })
}

describe('isSupportedImage', () => {
  it('accepts jpeg, png, webp', () => {
    expect(isSupportedImage(makeFile('image/jpeg'))).toBe(true)
    expect(isSupportedImage(makeFile('image/png'))).toBe(true)
    expect(isSupportedImage(makeFile('image/webp'))).toBe(true)
  })

  it('rejects unsupported types', () => {
    expect(isSupportedImage(makeFile('image/gif'))).toBe(false)
    expect(isSupportedImage(makeFile('application/pdf'))).toBe(false)
    expect(isSupportedImage(makeFile('text/plain'))).toBe(false)
  })

  it('does not trust the filename, only the MIME type', () => {
    // Extension says .png but MIME type says otherwise - MIME type wins.
    expect(isSupportedImage(makeFile('image/gif', 'sneaky.png'))).toBe(false)
  })
})

describe('buildDownloadFilename', () => {
  it('builds a deterministic, user-friendly filename', () => {
    expect(buildDownloadFilename('vacation.jpg', 'colorized', 'png')).toBe(
      'vacation-colorized.png'
    )
    expect(buildDownloadFilename('vacation.jpg', 'upscaled-2x', 'png')).toBe(
      'vacation-upscaled-2x.png'
    )
    expect(buildDownloadFilename('vacation.jpg', 'upscaled-4x', 'png')).toBe(
      'vacation-upscaled-4x.png'
    )
  })

  it('never leaks internal identifiers', () => {
    const result = buildDownloadFilename('photo.png', 'edited', 'png')
    expect(result).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}/)
  })

  it('falls back gracefully when the name has no extension', () => {
    expect(buildDownloadFilename('noext', 'edited', 'jpg')).toBe('noext-edited.jpg')
  })
})
