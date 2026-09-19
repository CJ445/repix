# Repix frontend

React 19 + TypeScript + Vite + Tailwind CSS 4.

```bash
npm install
npm run dev      # http://localhost:5173, proxies /api to VITE_API_PROXY_TARGET (default http://localhost:8000)
npm test         # vitest
npm run lint     # oxlint
npm run build    # tsc -b && vite build
```

## Design notes

- **Color tokens** live in `src/index.css` as semantic roles (`ink`, `ink-2`, `edge`, `accent`, …) with light, dark and increased-contrast values. Use these, not raw `neutral-*` classes. All text pairs are ≥ 4.5:1 and control edges ≥ 3:1.
- `accent` means one thing: the AI produced this (results, Keep, compare handle).
- **Undo/redo** (`src/state/history.ts`): last 10 steps plus Revert to Original; Ctrl/Cmd+Z, Shift+Ctrl/Cmd+Z.
- Controls are 44px tall on small screens and 36px with a pointer; text is 16px / 14px.
