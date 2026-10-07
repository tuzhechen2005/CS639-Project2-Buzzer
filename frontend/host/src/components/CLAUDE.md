# frontend/host/src/components/

## Purpose
Presentational UI primitives for the host's large-screen display (`ui/`), plus `PlotScatter`,
the one renderer for every host view of a plot_point plane (T7). Other composite pieces live
inline in pages.

## Contents
- `ui/button.tsx` — `Button` with `variant` (default / outline / ghost / destructive) and `size`
  (sm / md / lg). `rounded-xl`, the shared focus ring, `disabled:opacity-50`; hovers are
  `enabled:hover:` so a disabled button keeps its colour.
- `ui/card.tsx` — `Card`, `CardHeader`, `CardContent` wrappers (`rounded-2xl`, `bg-surface`, `p-6`).
- `ui/input.tsx` — styled `Input` (`surface-raised` with a `line-strong` border, focus ring).
- `ui/TimerBar.tsx` — countdown bar (`success` → `warning` → `danger` on a `surface-raised` track) with a seconds readout. Props:
  `totalSeconds`, optional `initialSeconds` (for reconnect / locked state), `paused`.
- `ui/QuestionImage.tsx` — (T8) a question or option image by id (`/api/images/{id}`, no
  login). Shows a same-size pulsing placeholder while loading, and on failure a short note or
  nothing (`fallbackText={null}`, used where the text label stays visible). `className` sizes the
  box; `align="left"` pins the picture to the left edge. No pre-loading; it never delays a question.
- `PlotScatter.tsx` — (T7 plot_point) the plane with its background image and overlays; with a
  distribution, one dot per `"col,row"` bucket sized by count; with an ACCURACY reveal, the target
  as a star and each band as a square around it labelled with its points. Used by the game
  `QuestionPage` (plane only), `ResultsPage`, the game-over `QuestionCard`, and the editor preview
  (`onPick` turns a click into the snapped target). `scale` enlarges text for the projector.
  Exposes `data-testid="plot-scatter"` and `data-plot-left` / `data-plot-top` / `data-cell-px`.
- `PromptText.tsx` — shows a question prompt with its formatting (via `lib/promptMarkup.ts`),
  as React elements and text, never raw HTML. Use it wherever a prompt is displayed; printing
  `{prompt}` directly shows `<b>` tags and `&lt;` codes literally.
- `ThemeToggle.tsx` — (T9) the sun/moon light/dark switch: name "Dark theme", state in
  `aria-pressed`, icon = current theme. Holds no state of its own: reads `<html data-theme>`
  and re-renders on `themechange`; a click calls `setTheme`. Callers place it with `className`
  (`HomePage`, `CourseLayout`, `LoginPage`, the game `GameLayout`'s room-code panel).
  Byte-identical to the admin's copy.
## How it fits in
Used by everything in `pages/`. Colours are theme tokens (`bg-surface`, `text-fg-muted`, …; `src/theme/`, T9), never palette classes. Styling is Tailwind via `lib/utils.ts`'s `cn`; callers can
override with `className`. Hand-rolled shadcn-style components, not an installed library.

## Gotchas
- `TimerBar` starts its interval once on mount (empty deps). The parent **must** pass
  `key={questionId}` to reset it per question; changing `initialSeconds` alone does nothing.
- `TimerBar` is display-only. The server owns the real timer (`websocket/gateway.py`); pausing
  here only mirrors the host's lock.
- `PlotScatter` reads its colours from the tokens at draw time (`lib/plotPalette.ts`) and redraws
  on `themechange`; a canvas that skipped that would keep the old theme's colours.
- A class passed through `className` that should replace a primitive's hover must use the same
  variant (`enabled:hover:…`), or tailwind-merge keeps both.
- The player app has its own diverging copies of these files.
