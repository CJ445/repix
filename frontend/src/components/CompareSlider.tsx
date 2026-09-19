import { useRef, useState } from 'react'

interface Props {
  beforeUrl: string
  afterUrl: string
}

const STEP = 2
const BIG_STEP = 10

/**
 * Before/after comparison sized to the image's own aspect ratio (no letterboxing,
 * no layout jump when a result arrives). Pointer Events cover mouse, touch and pen;
 * `touch-action: pan-y` lets vertical swipes still scroll the page.
 */
export default function CompareSlider({ beforeUrl, afterUrl }: Props) {
  const [pos, setPos] = useState(50)
  const containerRef = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)

  const clamp = (v: number) => Math.min(100, Math.max(0, v))

  const updateFromClientX = (clientX: number) => {
    const el = containerRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    setPos(clamp(((clientX - rect.left) / rect.width) * 100))
  }

  function onKeyDown(e: React.KeyboardEvent) {
    const step = e.shiftKey ? BIG_STEP : STEP
    if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') setPos((p) => clamp(p - step))
    else if (e.key === 'ArrowRight' || e.key === 'ArrowUp') setPos((p) => clamp(p + step))
    else if (e.key === 'PageDown') setPos((p) => clamp(p - BIG_STEP))
    else if (e.key === 'PageUp') setPos((p) => clamp(p + BIG_STEP))
    else if (e.key === 'Home') setPos(0)
    else if (e.key === 'End') setPos(100)
    else return
    e.preventDefault()
  }

  return (
    <div
      ref={containerRef}
      className="relative inline-block max-w-full touch-pan-y select-none overflow-hidden rounded-lg"
      onPointerDown={(e) => {
        dragging.current = true
        e.currentTarget.setPointerCapture(e.pointerId)
        updateFromClientX(e.clientX)
      }}
      onPointerMove={(e) => dragging.current && updateFromClientX(e.clientX)}
      onPointerUp={() => (dragging.current = false)}
      onPointerCancel={() => (dragging.current = false)}
    >
      <img
        src={afterUrl}
        alt="Result"
        className="block h-auto max-h-[45vh] w-auto max-w-full md:max-h-[62vh]"
        draggable={false}
      />
      <img
        src={beforeUrl}
        alt="Original"
        className="absolute inset-0 h-full w-full"
        style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}
        draggable={false}
      />
      <div className="absolute inset-y-0 w-0.5 -translate-x-1/2 bg-white shadow-md" style={{ left: `${pos}%` }}>
        <div
          role="slider"
          aria-label="Compare original and result"
          aria-valuenow={Math.round(pos)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuetext={`${Math.round(pos)}% of the original showing`}
          tabIndex={0}
          onKeyDown={onKeyDown}
          className="absolute top-1/2 left-1/2 flex h-11 w-11 -translate-x-1/2 -translate-y-1/2 cursor-ew-resize items-center justify-center rounded-full bg-surface text-ink shadow-lg ring-2 ring-accent"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9 7 4 12l5 5M15 7l5 5-5 5" />
          </svg>
        </div>
      </div>
      <span className="pointer-events-none absolute top-2 left-2 rounded bg-black/70 px-2 py-0.5 text-[0.8125rem] text-white">
        Before
      </span>
      <span className="pointer-events-none absolute top-2 right-2 rounded bg-black/70 px-2 py-0.5 text-[0.8125rem] text-white">
        After
      </span>
    </div>
  )
}
