import { describe, expect, it } from 'vitest'
import {
  MAX_UNDO_STEPS,
  commit,
  createHistory,
  describeOp,
  liveUrls,
  redo,
  revert,
  undo,
} from './history'
import type { EditorImage } from './types'

const img = (url: string): EditorImage => ({
  url,
  blob: new Blob(['x']),
  width: 10,
  height: 10,
  name: 'p.png',
  mimeType: 'image/png',
})

describe('history', () => {
  it('commits, undoes and redoes with the ops that produced each version', () => {
    let h = createHistory(img('a'))
    h = commit(h, img('b'), 'cropped')
    h = commit(h, img('c'), 'colorized')
    expect(h.present.ops).toEqual(['cropped', 'colorized'])

    h = undo(h)
    expect(h.present.image.url).toBe('b')
    expect(h.present.ops).toEqual(['cropped'])
    h = redo(h)
    expect(h.present.image.url).toBe('c')
  })

  it('clears redo when a new edit is committed', () => {
    let h = createHistory(img('a'))
    h = commit(h, img('b'), 'cropped')
    h = undo(h)
    h = commit(h, img('c'), 'resized')
    expect(h.future).toHaveLength(0)
  })

  it('does not repeat an op that is already last in the chain', () => {
    let h = createHistory(img('a'))
    h = commit(h, img('b'), 'resized')
    h = commit(h, img('c'), 'resized')
    expect(h.present.ops).toEqual(['resized'])
  })

  it('is a no-op to undo or redo at the ends', () => {
    const h = createHistory(img('a'))
    expect(undo(h)).toBe(h)
    expect(redo(h)).toBe(h)
  })

  it('reverts to the original and lets you undo the revert', () => {
    let h = createHistory(img('a'))
    h = commit(h, img('b'), 'cropped')
    h = commit(h, img('c'), 'colorized')
    h = revert(h)
    expect(h.present.image.url).toBe('a')
    expect(h.present.ops).toEqual([])
    h = undo(h)
    expect(h.present.image.url).toBe('c')
  })

  it('caps undo depth but always keeps the original', () => {
    let h = createHistory(img('orig'))
    for (let i = 0; i < MAX_UNDO_STEPS + 5; i++) h = commit(h, img(`v${i}`), `op${i}`)
    expect(h.past).toHaveLength(MAX_UNDO_STEPS)
    expect(liveUrls(h).has('orig')).toBe(true)
    expect(liveUrls(h).has('v0')).toBe(false)
  })

  it('names ops for undo and redo labels', () => {
    expect(describeOp('cropped')).toBe('Crop')
    expect(describeOp('upscaled-4x')).toBe('Upscale 4×')
    expect(describeOp('grayscaled')).toBe('Grayscale')
    expect(describeOp('mystery')).toBe('Edit')
  })
})
