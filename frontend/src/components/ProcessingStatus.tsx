interface Props {
  label: string
  /** 0-1 when the backend can report real progress; omit for an indeterminate bar. */
  progress?: number | null
}

export default function ProcessingStatus({ label, progress }: Props) {
  const determinate = typeof progress === 'number'
  const percent = determinate ? Math.round(Math.min(1, Math.max(0, progress)) * 100) : undefined

  return (
    <div role="status" aria-live="polite" className="flex w-full max-w-sm flex-col items-center gap-4 py-16">
      <div
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        className="h-2 w-full overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-800"
      >
        {determinate ? (
          <div
            className="h-full rounded-full bg-neutral-900 transition-[width] duration-500 dark:bg-neutral-100"
            style={{ width: `${percent}%` }}
          />
        ) : (
          <div className="h-full w-1/4 animate-[indeterminate-slide_1.4s_ease-in-out_infinite] rounded-full bg-neutral-900 dark:bg-neutral-100" />
        )}
      </div>
      <p className="text-sm text-neutral-600 dark:text-neutral-400">
        {label}
        {percent !== undefined && ` ${percent}%`}
      </p>
    </div>
  )
}
