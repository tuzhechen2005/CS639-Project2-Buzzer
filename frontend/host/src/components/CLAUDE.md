# frontend/host/src/components/

## Purpose
Presentational UI primitives for the host's large-screen display. Everything is in `ui/`;
there are no app-specific composite components yet (those live inline in pages).

## Contents
- `ui/button.tsx` — `Button` with `variant` (default / outline / ghost / destructive) and `size` (sm / md / lg).
- `ui/card.tsx` — `Card`, `CardHeader`, `CardContent` wrappers (dark slate panel styling).
- `ui/input.tsx` — styled `Input`.
- `ui/TimerBar.tsx` — countdown bar (green → yellow → red) with a seconds readout. Props:
  `totalSeconds`, optional `initialSeconds` (for reconnect / locked state), `paused`.

## How it fits in
Used by everything in `pages/`. Styling is Tailwind via `lib/utils.ts`'s `cn`; callers can
override with `className`. Hand-rolled shadcn-style components, not an installed library.

## Gotchas
- `TimerBar` starts its interval once on mount (empty deps). The parent **must** pass
  `key={questionId}` to reset it per question; changing `initialSeconds` alone does nothing.
- `TimerBar` is display-only. The server owns the real timer (`websocket/gateway.py`); pausing
  here only mirrors the host's lock.
- Dark-theme colours are hardcoded (slate/indigo); there is no theme token layer.
- The player app has its own diverging copies of these files.
