import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ResizeTool from './ResizeTool'
import type { EditorImage } from '../state/types'

const image: EditorImage = { url: 'u', blob: new Blob(), width: 800, height: 600, name: 'a.png', mimeType: 'image/png' }
const pressed = () => screen.getAllByRole('button', { pressed: true }).map((b) => b.textContent)

describe('ResizeTool presets', () => {
  it('starts with 100% highlighted', () => {
    render(<ResizeTool image={image} onApply={() => {}} />)
    expect(pressed()).toEqual(['100%'])
  })

  it('highlights the chosen preset and moves the highlight when another is chosen', async () => {
    render(<ResizeTool image={image} onApply={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: '50%' }))
    expect(pressed()).toEqual(['50%'])
    expect(screen.getByLabelText(/width/i)).toHaveValue(400)
    await userEvent.click(screen.getByRole('button', { name: '25%' }))
    expect(pressed()).toEqual(['25%'])
  })

  it('clears the highlight once the size no longer matches a preset', async () => {
    render(<ResizeTool image={image} onApply={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: '50%' }))
    await userEvent.clear(screen.getByLabelText(/width/i))
    await userEvent.type(screen.getByLabelText(/width/i), '431')
    expect(screen.queryAllByRole('button', { pressed: true })).toHaveLength(0)
  })
})

describe('ResizeTool units', () => {
  const pick = (name: RegExp) => userEvent.selectOptions(screen.getByLabelText('Unit'), screen.getByRole('option', { name }))

  it('defaults to pixels and shows no resolution field', () => {
    render(<ResizeTool image={image} onApply={() => {}} />)
    expect(screen.getByLabelText('Unit')).toHaveValue('px')
    expect(screen.queryByLabelText(/resolution/i)).toBeNull()
  })

  it('shows the same size in the chosen unit and keeps the pixel size', async () => {
    render(<ResizeTool image={image} onApply={() => {}} />)
    await pick(/centimeters/i)
    expect(screen.getByLabelText(/width \(cm\)/i)).toHaveValue(6.77)
    expect(screen.getByLabelText(/height \(cm\)/i)).toHaveValue(5.08)
    await pick(/inches/i)
    expect(screen.getByLabelText(/width \(in\)/i)).toHaveValue(2.667)
    await pick(/millimeters/i)
    expect(screen.getByLabelText(/width \(mm\)/i)).toHaveValue(67.7)
    await pick(/pixels/i)
    expect(screen.getByLabelText(/width \(px\)/i)).toHaveValue(800)
  })

  it('applies a size typed in cm as whole pixels, keeping the aspect ratio', async () => {
    const onApply = vi.fn()
    render(<ResizeTool image={image} onApply={onApply} />)
    await pick(/centimeters/i)
    await userEvent.clear(screen.getByLabelText(/width \(cm\)/i))
    await userEvent.type(screen.getByLabelText(/width \(cm\)/i), '5')
    expect(screen.getByText(/result: 591 × 443 px/i)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /apply resize/i }))
    expect(onApply).toHaveBeenCalledWith(591, 443)
  })

  it('keeps the pixel size when DPI changes and updates the displayed length', async () => {
    render(<ResizeTool image={image} onApply={() => {}} />)
    await pick(/inches/i)
    await userEvent.clear(screen.getByLabelText(/resolution/i))
    await userEvent.type(screen.getByLabelText(/resolution/i), '200')
    expect(screen.getByLabelText(/width \(in\)/i)).toHaveValue(4)
    expect(screen.getByLabelText(/height \(in\)/i)).toHaveValue(3)
  })

  it('rejects sizes larger than the image and blocks apply', async () => {
    render(<ResizeTool image={image} onApply={() => {}} />)
    await pick(/inches/i)
    await userEvent.clear(screen.getByLabelText(/width \(in\)/i))
    await userEvent.type(screen.getByLabelText(/width \(in\)/i), '10')
    expect(screen.getByRole('alert')).toHaveTextContent(/up to the current size/i)
    expect(screen.getByRole('button', { name: /apply resize/i })).toBeDisabled()
  })

  it('blocks apply on an invalid resolution', async () => {
    render(<ResizeTool image={image} onApply={() => {}} />)
    await pick(/centimeters/i)
    await userEvent.clear(screen.getByLabelText(/resolution/i))
    expect(screen.getByRole('button', { name: /apply resize/i })).toBeDisabled()
  })

  it('still highlights the preset after switching units', async () => {
    render(<ResizeTool image={image} onApply={() => {}} />)
    await pick(/millimeters/i)
    await userEvent.click(screen.getByRole('button', { name: '50%' }))
    expect(pressed()).toEqual(['50%'])
  })
})
