# frontend/player/src/components/

## Purpose
UI primitives for the player's phone screen in `ui/`, plus the plot_point answer screen (T7).
The big answer buttons and option colours of the other types are built inline in
`pages/game/QuestionPage.tsx`, not here.

## Contents
- `ui/button.tsx` — `Button` with `variant` (default / outline / ghost / destructive) and `size`
  (sm / md / lg); larger tap targets and an `active:scale-95` press effect.
- `ui/card.tsx` — `Card`, `CardHeader`, `CardContent` wrappers.
- `ui/input.tsx` — styled `Input` (larger padding, `text-base` so iOS doesn't zoom on focus).
- `ui/TimerBar.tsx` — countdown bar (green → yellow → red) with seconds readout. Props:
  `totalSeconds`, `paused`.
- `ui/QuestionImage.tsx` — (T8) a question or option image by id (`/api/images/{id}`, no
  login). Shows a same-size pulsing placeholder while loading, and on failure a short note or
  nothing (`fallbackText={null}`, used where the text label stays visible). `className` sizes the
  box; `align="left"` pins the picture to the left edge. No pre-loading; it never delays a question.
- `PlotCanvas.tsx` — (T7 plot_point) the coordinate-plane canvas. Fills its box with square cells
  (capped at the plane's height), draws at `devicePixelRatio`, redraws on resize/rotation, loads
  the background image without blocking. The first pointer places and drags the point, snapping
  live; locking ends a drag. Exposes `data-plot-left` / `data-plot-top` / `data-cell-px` for the
  browser test.
- `PlotPointAnswer.tsx` — the whole plot_point answer screen: canvas, `aria-live` readout, Submit,
  and the collapsed "Type coordinates" panel (rules in `lib/plotPoint.ts`). Controls sit below the
  canvas in portrait and in a column to its right in landscape, as **one** element tree whose
  classes change on rotation (two trees would remount the timer and the canvas). Rendered by
  `QuestionPage` with `key={questionId}`; the point survives lock/unlock and rotation.

## How it fits in
Used by the pages in `pages/`. Styling is Tailwind via `lib/utils.ts`'s `cn`; callers can
override with `className`.

## Gotchas
- These are **forks of the host's `components/ui/`**, not shared code: same API, different sizing
  (mobile-first). Keep that in mind when fixing a bug in one copy.
- Unlike the host's `TimerBar`, this one has **no `initialSeconds` prop**; it always counts down
  from `totalSeconds`. Late joiners still see the right time only because the backend rewrites
  `timeLimitSeconds` to the remaining time (minimum 5 s) in the `new_question` it sends them.
- `TimerBar` starts its interval once on mount; the parent must pass `key={questionId}` to reset it.
  Any remount restarts it at full time (it has no remaining-time input), so never move it between
  element trees mid-question.
- The timer is display-only; the server decides when the question closes.
