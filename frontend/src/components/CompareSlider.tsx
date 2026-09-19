import { useRef, useState } from 'react'

interface Props {
  beforeUrl: string
  afterUrl: string
}

export default function CompareSlider({ beforeUrl, afterUrl }: Props) {
  const [pos, setPos] = useState(50)
  const containerRef = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)

  const updateFromClientX = (clientX: number) => {
    const el = containerRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    const ratio = ((clientX - rect.left) / rect.width) * 100
    setPos(Math.min(100, Math.max(0, ratio)))
  }

  return (
    <div
      ref={containerRef}
      className="relative aspect-video w-full select-none overflow-hidden rounded-xl bg-neutral-100 dark:bg-neutral-900"
      onMouseDown={(e) => {
        dragging.current = true
        updateFromClientX(e.clientX)
      }}
      onMouseMove={(e) => dragging.current && updateFromClientX(e.clientX)}
      onMouseUp={() => (dragging.current = false)}
      onMouseLeave={() => (dragging.current = false)}
      onTouchStart={(e) => updateFromClientX(e.touches[0].clientX)}
      onTouchMove={(e) => updateFromClientX(e.touches[0].clientX)}
    >
      <img src={afterUrl} alt="Processed result" className="absolute inset-0 h-full w-full object-contain" draggable={false} />
      <img
        src={beforeUrl}
        alt="Original image"
        className="absolute inset-0 h-full w-full object-contain"
        style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}
        draggable={false}
      />
      <div
        className="absolute inset-y-0 w-0.5 bg-white shadow-md"
        style={{ left: `${pos}%` }}
      >
        <div
          role="slider"
          aria-label="Comparison position"
          aria-valuenow={Math.round(pos)}
          aria-valuemin={0}
          aria-valuemax={100}
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === 'ArrowLeft') setPos((p) => Math.max(0, p - 2))
            if (e.key === 'ArrowRight') setPos((p) => Math.min(100, p + 2))
          }}
          className="absolute top-1/2 flex h-9 w-9 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-white text-neutral-700 shadow-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-900"
        >
          ⇔
        </div>
      </div>
      <span className="absolute left-2 top-2 rounded bg-black/60 px-2 py-0.5 text-xs text-white">Before</span>
      <span className="absolute right-2 top-2 rounded bg-black/60 px-2 py-0.5 text-xs text-white">After</span>
    </div>
  )
}
