import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import Dropzone from './Dropzone'

describe('Dropzone', () => {
  it('renders the initial upload state', () => {
    render(<Dropzone onFile={() => {}} />)
    expect(screen.getByText(/drop an image here/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /choose image/i })).toBeInTheDocument()
  })

  it('calls onFile with a supported file selected via the file input', async () => {
    const onFile = vi.fn()
    render(<Dropzone onFile={onFile} />)
    const file = new File(['x'], 'photo.png', { type: 'image/png' })
    const input = document.querySelector('input[type=file]') as HTMLInputElement

    await userEvent.upload(input, file)

    expect(onFile).toHaveBeenCalledWith(file)
  })

  it('shows an error and does not call onFile for unsupported types', async () => {
    const onFile = vi.fn()
    render(<Dropzone onFile={onFile} />)
    const file = new File(['x'], 'clip.gif', { type: 'image/gif' })
    const input = document.querySelector('input[type=file]') as HTMLInputElement

    fireEvent.change(input, { target: { files: [file] } })

    expect(onFile).not.toHaveBeenCalled()
    expect(await screen.findByRole('alert')).toHaveTextContent(/isn't a JPG, PNG or WebP/i)
  })

  it('shows a message when the file is a supported type but cannot be read', async () => {
    const onFile = vi.fn().mockRejectedValue(new Error('decode failed'))
    render(<Dropzone onFile={onFile} />)
    const file = new File(['x'], 'broken.png', { type: 'image/png' })
    const input = document.querySelector('input[type=file]') as HTMLInputElement

    await userEvent.upload(input, file)

    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn't read that image/i)
  })

  it('accepts an image pasted anywhere on the page', () => {
    const onFile = vi.fn()
    render(<Dropzone onFile={onFile} />)
    const file = new File(['x'], 'shot.png', { type: 'image/png' })
    const event = new Event('paste') as Event & { clipboardData: unknown }
    event.clipboardData = { items: [{ type: 'image/png', getAsFile: () => file }] }

    window.dispatchEvent(event)

    expect(onFile).toHaveBeenCalledWith(file)
  })

  it('says which steps leave the device', () => {
    render(<Dropzone onFile={() => {}} />)
    expect(screen.getByText(/crop and resize happen on your device/i)).toBeInTheDocument()
  })
})
