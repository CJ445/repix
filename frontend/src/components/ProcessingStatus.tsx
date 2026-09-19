import { useEffect, useState } from 'react'

interface Props {
  label: string
  /** 0-1 when the backend can report real progress; omit for an indeterminate bar. */
  progress?: number | null
  onCancel: () => void
}

function formatElapsed(seconds: number) {
  const m = Math.floor(seconds / 60)
  return `${m}:${String(seconds % 60).padStart(2, '0')}`
}

/** Progress card with the Cancel button beside it, so the way out is where the wait is. */
export default function ProcessingStatus({ label, progress, onCancel }: Props) {
  const determinate = typeof progress === 'number'
  const percent = determinate ? Math.round(Math.min(1, Math.max(0, progress)) * 100) : undefined
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const started = Date.now()
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000)
    return () => clearInterval(t)
  }, [])

  return (
    <div className="flex w-full max-w-sm flex-col gap-4 rounded-xl border border-line bg-surface p-5 shadow-lg">
      <div role="status" aria-live="polite" className="font-medium">
        {label}
        {percent !== undefined && ` ${percent}%`}
      </div>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        className="h-2 w-full overflow-hidden rounded-full bg-sunken ring-1 ring-line ring-inset"
      >
        {determinate ? (
          <div className="h-full rounded-full bg-accent transition-[width] duration-500" style={{ width: `${percent}%` }} />
        ) : (
          <div className="h-full w-1/4 animate-[indeterminate-slide_1.4s_ease-in-out_infinite] rounded-full bg-accent" />
        )}
      </div>
      <p className="note">
        Running on CPU, this can take a minute or more for large images. Elapsed {formatElapsed(elapsed)}.
      </p>
      <button onClick={onCancel} className="btn btn-secondary w-fit">
        Cancel
      </button>
    </div>
  )
}
