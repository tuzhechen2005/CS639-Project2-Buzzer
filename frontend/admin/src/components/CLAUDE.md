# frontend/admin/src/components/

## Purpose
Basic UI primitives for the admin dashboard in `ui/`, plus the theme toggle; forms, tables, panels and
wizards are built inline in each page.

## Contents
- `ui/button.tsx` — `Button` with `variant` (default / outline / ghost / destructive) and `size` (sm / md / lg).
- `ui/card.tsx` — `Card`, `CardHeader`, `CardContent` wrappers.
- `ui/input.tsx` — styled `Input`.
- `ThemeToggle.tsx` — (T9) the sun/moon light/dark switch ("Dark theme", `aria-pressed`), placed
  in the sidebar footer above Logout and fixed top-right on the login page. Byte-identical to the
  host's copy.

## How it fits in
Used by every page in `pages/`. Colours are theme tokens (`bg-surface`, `text-fg-muted`, …; `src/theme/`, T9), never palette classes. Styling is Tailwind via `lib/utils.ts`'s `cn`; callers override
with `className`. Icons come straight from `lucide-react` in the pages, not from here.

## Gotchas
- All three `ui/` files and `ThemeToggle.tsx` are **byte-identical to the host's copies** (the player's are resized
  forks). They are copies, not shared code, so a fix has to be made in each app.
- There is no `TimerBar`, modal, table or select component; pages use native `<select>`,
  `confirm()` dialogs and hand-written tables.
