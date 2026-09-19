interface Props {
  onStart: () => void
  disabled: boolean
}

export default function ColorizeTool({ onStart, disabled }: Props) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-neutral-600 dark:text-neutral-400">
        Add realistic color to a grayscale image.
      </p>
      <button
        disabled={disabled}
        onClick={onStart}
        className="w-fit rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-40 dark:bg-neutral-100 dark:text-neutral-900"
      >
        Colorize Image
      </button>
    </div>
  )
}
