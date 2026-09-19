interface Props {
  label: string
}

export default function ProcessingStatus({ label }: Props) {
  return (
    <div role="status" aria-live="polite" className="flex flex-col items-center gap-4 py-16">
      <div className="h-10 w-10 animate-spin rounded-full border-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-700 dark:border-t-neutral-100" />
      <p className="text-sm text-neutral-600 dark:text-neutral-400">{label}</p>
    </div>
  )
}
