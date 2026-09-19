import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ColorizeTool from './ColorizeTool'

describe('ColorizeTool', () => {
  it('shows Grayscale next to Colorize Image and fires the right handler', async () => {
    const onStart = vi.fn()
    const onGrayscale = vi.fn()
    render(<ColorizeTool onStart={onStart} onGrayscale={onGrayscale} disabled={false} />)
    const colorize = screen.getByRole('button', { name: 'Colorize Image' })
    const gray = screen.getByRole('button', { name: 'Grayscale' })
    expect(colorize.nextElementSibling).toBe(gray)
    await userEvent.click(gray)
    expect(onGrayscale).toHaveBeenCalledOnce()
    expect(onStart).not.toHaveBeenCalled()
  })

  it('disables both buttons while busy', () => {
    render(<ColorizeTool onStart={vi.fn()} onGrayscale={vi.fn()} disabled />)
    expect(screen.getByRole('button', { name: 'Grayscale' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Colorize Image' })).toBeDisabled()
  })
})
