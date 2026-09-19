import ServerNote from './ServerNote'

interface Props {
  onStart: () => void
  disabled: boolean
}

export default function ColorizeTool({ onStart, disabled }: Props) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-ink-2">
        Predicts plausible colors for a black-and-white photo. The result is the model&rsquo;s best guess, not
        the true original, so compare before you keep it.
      </p>
      <ServerNote />
      <button disabled={disabled} onClick={onStart} className="btn btn-primary w-fit">
        Colorize Image
      </button>
    </div>
  )
}
