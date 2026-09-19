import ServerNote from './ServerNote'

interface Props {
  onStart: () => void
  onGrayscale: () => void
  disabled: boolean
}

export default function ColorizeTool({ onStart, onGrayscale, disabled }: Props) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-ink-2">
        Predicts plausible colors for a black-and-white photo. The result is the model&rsquo;s best guess, not
        the true original, so compare before you keep it.
      </p>
      <ServerNote />
      <div className="flex flex-wrap gap-2">
        <button disabled={disabled} onClick={onStart} className="btn btn-primary w-fit">
          Colorize Image
        </button>
        <button disabled={disabled} onClick={onGrayscale} className="btn btn-secondary w-fit">
          Grayscale
        </button>
      </div>
      <p className="note">Grayscale is applied right here in your browser and can be undone.</p>
    </div>
  )
}
