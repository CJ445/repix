import { useCallback, useRef, useState } from 'react'
import { isSupportedImage } from '../utils/image'

interface Props {
  onFile: (file: File) => void
}

export default function Dropzone({ onFile }: Props) {
  const [isOver, setIsOver] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const accept = useCallback(
    (file: File | undefined) => {
      if (!file) return
      if (!isSupportedImage(file)) {
        setError('Unsupported image type')
        return
      }
      setError(null)
      onFile(file)
    },
    [onFile]
  )

  return (
    <div className="flex min-h-[70vh] flex-1 flex-col items-center justify-center px-6">
      <h1 className="mb-2 text-3xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-50">
        Image Lab
      </h1>
      <p className="mb-8 text-sm text-neutral-500 dark:text-neutral-400">
        Crop, resize, colorize and upscale — right in your browser.
      </p>
      <div
        role="button"
        tabIndex={0}
        aria-label="Drop an image here or choose a file"
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click()
        }}
        onDragOver={(e) => {
          e.preventDefault()
          setIsOver(true)
        }}
        onDragLeave={() => setIsOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setIsOver(false)
          accept(e.dataTransfer.files?.[0])
        }}
        onPaste={(e) => {
          const item = Array.from(e.clipboardData.items).find((i) => i.type.startsWith('image/'))
          const file = item?.getAsFile()
          if (file) accept(file)
        }}
        className={`flex w-full max-w-xl cursor-pointer flex-col items-center gap-4 rounded-2xl border-2 border-dashed px-10 py-16 text-center transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-900 dark:focus-visible:ring-neutral-100 ${
          isOver
            ? 'border-neutral-900 bg-neutral-50 dark:border-neutral-100 dark:bg-neutral-900'
            : 'border-neutral-300 dark:border-neutral-700'
        }`}
      >
        <p className="text-lg font-medium text-neutral-800 dark:text-neutral-100">
          {isOver ? 'Release to upload' : 'Drop an image here'}
        </p>
        <p className="text-sm text-neutral-500">or</p>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            inputRef.current?.click()
          }}
          className="rounded-lg bg-neutral-900 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-neutral-700 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-300"
        >
          Choose Image
        </button>
        <p className="text-xs uppercase tracking-wide text-neutral-400">JPG · PNG · WebP</p>
        <input
          ref={inputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="hidden"
          onChange={(e) => accept(e.target.files?.[0])}
        />
      </div>
      {error && (
        <p role="alert" className="mt-4 text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      )}
    </div>
  )
}
