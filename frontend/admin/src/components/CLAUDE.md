# frontend/admin/src/components/

## Purpose
Basic UI primitives for the admin dashboard. Everything is in `ui/`; forms, tables, panels and
wizards are built inline in each page.

## Contents
- `ui/button.tsx` — `Button` with `variant` (default / outline / ghost / destructive) and `size` (sm / md / lg).
- `ui/card.tsx` — `Card`, `CardHeader`, `CardContent` wrappers.
- `ui/input.tsx` — styled `Input`.

## How it fits in
Used by every page in `pages/`. Styling is Tailwind via `lib/utils.ts`'s `cn`; callers override
with `className`. Icons come straight from `lucide-react` in the pages, not from here.

## Gotchas
- All three files are **byte-identical to the host's `components/ui/`** (the player's are resized
  forks). They are copies, not shared code, so a fix has to be made in each app.
- There is no `TimerBar`, modal, table or select component; pages use native `<select>`,
  `confirm()` dialogs and hand-written tables.
