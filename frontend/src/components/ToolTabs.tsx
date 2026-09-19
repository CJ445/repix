import { useRef } from 'react'
import type { Tool } from '../state/types'
import { TOOL_PANEL_ID, toolTabId } from './toolIds'

const TOOLS: { id: Tool; label: string }[] = [
  { id: 'crop', label: 'Crop' },
  { id: 'resize', label: 'Resize' },
  { id: 'colorize', label: 'Colorize' },
  { id: 'upscale', label: 'Upscale' },
]

interface Props {
  tool: Tool
  onChange: (tool: Tool) => void
}

/** Segmented tab control with roving focus. The selected tab gets an underline and heavier weight, not just a fill. */
export default function ToolTabs({ tool, onChange }: Props) {
  const refs = useRef<Partial<Record<Tool, HTMLButtonElement | null>>>({})

  function onKeyDown(e: React.KeyboardEvent, index: number) {
    let next = index
    if (e.key === 'ArrowRight') next = (index + 1) % TOOLS.length
    else if (e.key === 'ArrowLeft') next = (index - 1 + TOOLS.length) % TOOLS.length
    else if (e.key === 'Home') next = 0
    else if (e.key === 'End') next = TOOLS.length - 1
    else return
    e.preventDefault()
    const id = TOOLS[next].id
    onChange(id)
    refs.current[id]?.focus()
  }

  return (
    <div role="tablist" aria-label="Edit tools" className="flex gap-1 rounded-lg bg-sunken p-1 ring-1 ring-line ring-inset">
      {TOOLS.map((t, i) => (
        <button
          key={t.id}
          ref={(el) => {
            refs.current[t.id] = el
          }}
          id={toolTabId(t.id)}
          role="tab"
          type="button"
          aria-selected={tool === t.id}
          aria-controls={TOOL_PANEL_ID}
          tabIndex={tool === t.id ? 0 : -1}
          onClick={() => onChange(t.id)}
          onKeyDown={(e) => onKeyDown(e, i)}
          className="min-h-11 flex-1 rounded-md px-2 text-sm font-medium text-ink-2 transition-colors hover:text-ink md:min-h-9 aria-selected:bg-surface aria-selected:font-semibold aria-selected:text-ink aria-selected:shadow-[inset_0_-2px_0_var(--ink)]"
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}
