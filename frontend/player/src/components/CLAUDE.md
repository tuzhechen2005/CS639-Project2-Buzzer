# frontend/player/src/components/

## Purpose
UI primitives for the player's phone screen. Everything is in `ui/`; the big answer buttons
and option colours are built inline in `pages/game/QuestionPage.tsx`, not here.

## Contents
- `ui/button.tsx` — `Button` with `variant` (default / outline / ghost / destructive) and `size`
  (sm / md / lg); larger tap targets and an `active:scale-95` press effect.
- `ui/card.tsx` — `Card`, `CardHeader`, `CardContent` wrappers.
- `ui/input.tsx` — styled `Input` (larger padding, `text-base` so iOS doesn't zoom on focus).
- `ui/TimerBar.tsx` — countdown bar (green → yellow → red) with seconds readout. Props:
  `totalSeconds`, `paused`.

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
- The timer is display-only; the server decides when the question closes.
