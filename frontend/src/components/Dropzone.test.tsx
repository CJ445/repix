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
    expect(await screen.findByRole('alert')).toHaveTextContent(/unsupported/i)
  })
})
