import type { EditorImage } from './types'

/** One version of the working image, plus the edits baked into it (used to name downloads). */
export interface Snapshot {
  image: EditorImage
  ops: string[]
  /** The edit that produced this snapshot, e.g. "cropped". Empty for the original. */
  op: string
}

export interface History {
  original: Snapshot
  past: Snapshot[]
  present: Snapshot
  future: Snapshot[]
}

/** Oldest undo steps are dropped past this; the original is always kept for Revert. */
export const MAX_UNDO_STEPS = 10

const VERBS: Record<string, string> = {
  cropped: 'Crop',
  resized: 'Resize',
  colorized: 'Colorize',
  'upscaled-2x': 'Upscale 2×',
  'upscaled-4x': 'Upscale 4×',
}

export function describeOp(op: string): string {
  return VERBS[op] ?? 'Edit'
}

export function createHistory(image: EditorImage): History {
  const original: Snapshot = { image, ops: [], op: '' }
  return { original, past: [], present: original, future: [] }
}

export function commit(h: History, image: EditorImage, op: string): History {
  const ops = h.present.ops[h.present.ops.length - 1] === op ? h.present.ops : [...h.present.ops, op]
  const past = [...h.past, h.present].slice(-MAX_UNDO_STEPS)
  return { ...h, past, present: { image, ops, op }, future: [] }
}

export function undo(h: History): History {
  if (h.past.length === 0) return h
  return {
    ...h,
    past: h.past.slice(0, -1),
    present: h.past[h.past.length - 1],
    future: [h.present, ...h.future],
  }
}

export function redo(h: History): History {
  if (h.future.length === 0) return h
  return {
    ...h,
    past: [...h.past, h.present],
    present: h.future[0],
    future: h.future.slice(1),
  }
}

/** Go back to the original image. This is itself undoable. */
export function revert(h: History): History {
  if (h.present === h.original) return h
  return {
    ...h,
    past: [...h.past, h.present].slice(-MAX_UNDO_STEPS),
    present: h.original,
    future: [],
  }
}

export function snapshots(h: History): Snapshot[] {
  return [h.original, ...h.past, h.present, ...h.future]
}

/** Object URLs still needed by some version; anything else can be revoked. */
export function liveUrls(h: History): Set<string> {
  return new Set(snapshots(h).map((s) => s.image.url))
}
