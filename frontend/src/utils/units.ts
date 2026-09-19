export type Unit = 'px' | 'in' | 'cm' | 'mm'

export const UNITS: { id: Unit; label: string }[] = [
  { id: 'px', label: 'Pixels (px)' },
  { id: 'in', label: 'Inches (in)' },
  { id: 'cm', label: 'Centimeters (cm)' },
  { id: 'mm', label: 'Millimeters (mm)' },
]

/** Print resolution used to convert physical units to pixels until the person changes it. */
export const DEFAULT_DPI = 300
export const MIN_DPI = 1
export const MAX_DPI = 9600

const MM_PER_INCH = 25.4
const MM_PER_UNIT: Record<Exclude<Unit, 'px'>, number> = { mm: 1, cm: 10, in: MM_PER_INCH }
const DECIMALS: Record<Unit, number> = { px: 0, in: 3, cm: 2, mm: 1 }

export function isValidDpi(dpi: number): boolean {
  return Number.isFinite(dpi) && dpi >= MIN_DPI && dpi <= MAX_DPI
}

/** Unrounded pixel length of `value` in `unit` at `dpi`. */
export function toPx(value: number, unit: Unit, dpi: number): number {
  return unit === 'px' ? value : (value * MM_PER_UNIT[unit] * dpi) / MM_PER_INCH
}

export function fromPx(px: number, unit: Unit, dpi: number): number {
  return unit === 'px' ? px : (px * MM_PER_INCH) / (MM_PER_UNIT[unit] * dpi)
}

/** Display text for a length: fixed precision per unit, no trailing zeros. */
export function formatUnit(value: number, unit: Unit): string {
  return String(Number(value.toFixed(DECIMALS[unit])))
}
