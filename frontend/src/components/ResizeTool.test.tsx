import { describe, expect, it } from 'vitest'
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
