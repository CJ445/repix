import { describe, expect, it } from 'vitest'
import { formatUnit, fromPx, isValidDpi, toPx } from './units'

describe('units', () => {
  it('converts physical lengths to pixels at a given DPI', () => {
    expect(toPx(1, 'in', 300)).toBe(300)
    expect(toPx(2.54, 'cm', 300)).toBeCloseTo(300)
    expect(toPx(25.4, 'mm', 300)).toBeCloseTo(300)
    expect(toPx(640, 'px', 300)).toBe(640)
  })

  it('round-trips through pixels', () => {
    for (const unit of ['in', 'cm', 'mm'] as const) {
      expect(fromPx(toPx(7.5, unit, 240), unit, 240)).toBeCloseTo(7.5)
    }
  })

  it('formats with per-unit precision and no trailing zeros', () => {
    expect(formatUnit(6.77291, 'cm')).toBe('6.77')
    expect(formatUnit(8, 'cm')).toBe('8')
    expect(formatUnit(2.6666, 'in')).toBe('2.667')
    expect(formatUnit(67.7291, 'mm')).toBe('67.7')
    expect(formatUnit(799.6, 'px')).toBe('800')
  })

  it('validates DPI', () => {
    expect(isValidDpi(300)).toBe(true)
    expect(isValidDpi(0)).toBe(false)
    expect(isValidDpi(NaN)).toBe(false)
    expect(isValidDpi(100000)).toBe(false)
  })
})
