import { useCallback, useEffect, useRef, useState } from 'react'
import { isSupportedImage } from '../utils/image'
import Logo from './Logo'

interface Props {
  /** May throw or reject if the file can't be read; the message is shown here. */
  onFile: (file: File) => void | Promise<void>
}

export default function Dropzone({ onFile }: Props) {
  const [isOver, setIsOver] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const accept = useCallback(
    async (file: File | undefined) => {
      if (!file) return
      if (!isSupportedImage(file)) {
        setError("That file isn't a JPG, PNG or WebP. Choose another image.")
        return
      }
      setError(null)
      try {
        await onFile(file)
      } catch {
        setError("Repix couldn't read that image. It may be damaged. Try another file.")
      }
    },
    [onFile]
  )

  // Pasting works anywhere on the page, not only when the drop area has focus.
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const item = Array.from(e.clipboardData?.items ?? []).find((i) => i.type.startsWith('image/'))
      const file = item?.getAsFile()
      if (file) void accept(file)
    }
    window.addEventListener('paste', onPaste)
    return () => window.removeEventListener('paste', onPaste)
  }, [accept])

  return (
    <main className="flex min-h-dvh flex-1 flex-col items-center justify-center px-4 py-10 md:px-6">
      <div className="mb-3 flex items-center gap-3">
        <Logo className="h-9 w-9" />
        <h1 className="text-3xl font-semibold tracking-tight">Repix</h1>
      </div>
      <p className="mb-8 text-center text-ink-2">Crop, resize, colorize and upscale your photos.</p>

      <div
        onDragOver={(e) => {
          e.preventDefault()
          setIsOver(true)
        }}
        onDragLeave={() => setIsOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setIsOver(false)
          void accept(e.dataTransfer.files?.[0])
        }}
        className={`flex w-full max-w-xl flex-col items-center gap-4 rounded-2xl border-2 border-dashed px-6 py-14 text-center transition-colors md:px-10 md:py-16 ${
          isOver ? 'border-ink bg-sunken' : 'border-edge'
        }`}
      >
        <p className="text-lg font-medium">{isOver ? 'Release to upload' : 'Drop an image here'}</p>
        <button type="button" onClick={() => inputRef.current?.click()} className="btn btn-primary px-6">
          Choose Image
        </button>
        <p className="note">JPG, PNG or WebP. You can also paste an image from the clipboard.</p>
        <input
          ref={inputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="hidden"
          aria-label="Choose an image file"
          onChange={(e) => {
            void accept(e.target.files?.[0])
            e.target.value = ''
          }}
        />
      </div>

      {error && (
        <p role="alert" className="mt-4 max-w-xl text-center text-danger">
          {error}
        </p>
      )}

      <p className="note mt-8 max-w-md text-center">
        Crop and resize happen on your device. Colorize and upscale send the image to this Repix server, which
        deletes it after you download the result or when it expires. Nothing is kept in an account or gallery.
      </p>
    </main>
  )
}
