import { describe, expect, it } from 'vitest'
import { isSupportedImage, buildDownloadFilename, formatFileSize } from './image'

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

describe('buildDownloadFilename with multiple edits', () => {
  it('joins the applied operations in order', () => {
    expect(buildDownloadFilename('a.jpg', ['colorized', 'cropped'], 'webp')).toBe(
      'a-colorized-cropped.webp'
    )
  })

  it('collapses long edit chains and empty lists to "edited"', () => {
    expect(buildDownloadFilename('a.jpg', ['a', 'b', 'c', 'd'], 'png')).toBe('a-edited.png')
    expect(buildDownloadFilename('a.jpg', [], 'png')).toBe('a-edited.png')
  })
})

describe('formatFileSize', () => {
  it('uses human-friendly units', () => {
    expect(formatFileSize(512)).toBe('512 B')
    expect(formatFileSize(2048)).toBe('2.0 KB')
    expect(formatFileSize(500 * 1024)).toBe('500 KB')
    expect(formatFileSize(3 * 1024 * 1024)).toBe('3.00 MB')
    expect(formatFileSize(25 * 1024 * 1024)).toBe('25.0 MB')
  })
})
