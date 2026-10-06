# frontend/player/src/

## Purpose
The Player app: what students open on their phones. They enter a room code, identify themselves
(guest, UW NetID, or local account), then answer questions live over Socket.io and see their own
score and rank.

## Contents
Top-level files:
- `main.tsx` — React entry; calls `initTheme()` (from `theme/theme.ts`) before rendering
  `<App />` in `StrictMode`, and imports `index.css`.
- `App.tsx` — the router: `/join`, `/login` (OAuth2 return), `/name/:code`, and
  `/game/:code/{lobby,question,feedback,results,gameover}` nested under `GameLayout`. Anything else
  redirects to `/join`. No route guard; `GameLayout` checks the token itself. Renders the one
  `ThemeToggle` inside the router (hidden on the question route).
  `basename` is `import.meta.env.BASE_URL` (`/player/` in production builds, `/` in dev).
- `index.css` — imports `theme/tokens.css` first, then the Tailwind directives, and turns off
  the tap-highlight flash on mobile.
- `theme/` — (T9) everything about colour, **byte-identical in host, player and admin**
  (`tests/unit/test_theme_copies.py`): `tokens.css` (the light values in `:root`, the dark
  overrides in `[data-theme="dark"]`, as RGB channels), `colors.js` + `colors.d.ts` (the Tailwind
  colour map, `rgb(var(--x) / <alpha-value>)`), and `theme.ts` (`getStoredTheme`,
  `currentTheme`, `tokenColor`, `applyTheme`, `setTheme`, `initTheme`; the choice is
  `localStorage['buzzer-theme']`, else the OS). The only folder allowed to contain colours.
- `types/game.ts` — hand-written shapes for the Socket.io payloads a player receives
  (`SyncStatePayload`, `QuestionPayload`, `AnswerResultPayload`, `PlayerResultsPayload`,
  `PlayerAnswerReveal`, `PlayerGameOverPayload`, …) and the `PlayerPhase` union.

Subdirectories (each has its own `CLAUDE.md`):
- `pages/` — all screens. `game/GameLayout.tsx` owns the socket and all game state, exposes it via
  `useGame()` (including `emitAnswer`), and navigates when server events arrive.
- `components/` — `ui/` primitives (`Button`, `Card`, `Input`, `TimerBar`, `QuestionImage`),
  mobile-sized forks of the host's (every control ≥ 44 px), plus the plot_point answer screen
  (`PlotPointAnswer`, with its `PlotCanvas`), `PromptText` and `ThemeToggle`.
- `lib/` — `api` (REST over `fetch`), `cn()`, `isTokenExpired()`, `images`, `parseNumber` (what a
  player types into a number) and `numericEstimate` (display helpers for that type), and the
  plot_point modules: `plotGeometry` (pure plane geometry, byte-identical to the host's copy),
  `plotPalette` (canvas colours from the theme tokens), `plotDraw` (canvas painting) and
  `plotPoint` (typed-coordinate rules and result text). The pure ones are unit-tested with
  vitest, and so is `theme/theme.ts` (`lib/theme.test.ts`).

## How it fits in
```
App.tsx (routes) ──▶ pages/ ──REST──▶ lib/api ──▶ /api/*        ─┐
                       │   (ping, guest, login)                   ├─▶ backend :8000
                       └──Socket.io (GameLayout)──▶ /socket.io/* ─┘
                       uses components/ui, types/game.ts
```
In dev, Vite (:5174) proxies `/api` and `/socket.io` to the backend; in production nginx serves
the build at `/player/` (and redirects `/` there). Players usually arrive from the host's QR code
(`/player/join?code=…`). They send only `join_room` and `submit_answer`, and receive just their
own points, score and rank plus the answer reveal; the answer distribution goes only to the host.
The protocol is defined in `backend/app/websocket/events.py` and `gateway.py`.

## Gotchas
Cross-cutting ones. Each subdirectory's `CLAUDE.md` has the details.
- **Colours come only from theme tokens (T9).** Use `bg-surface`, `text-fg-muted`,
  `border-line-strong`, … — never palette classes (`bg-slate-800`, `text-white`) or hex/rgb
  values; `tests/unit/test_no_raw_colours.py` fails on any. A new foreground/background pair
  must be added to the spec's allowed pairs and `tests/unit/test_theme_contrast.py` (WCAG AA,
  both themes). Change `src/theme/` in all three apps at once, or the copy test fails. Canvases
  get colours through `tokenColor()` at draw time and redraw on the `themechange` event.
- **The phone's top-right corner belongs to the theme toggle** (except on the question
  screen); keep fixed content clear of it.
- **`types/game.ts` is a manual mirror of the backend payloads**, and a different file from the
  host's `types/game.ts`. Nothing checks either against the server. It also leaves out fields the
  server sends (`sync_state`'s `currentQuestion`, `hasAnswered`, `yourScore`).
- **Adding a question type (T7)** on the player side touches `types/game.ts`, `QuestionPage`,
  `ResultsPage` and `GameOverPage` (see `pages/CLAUDE.md`), on top of the host and backend changes.
  The answer shape sent in `submit_answer` must match what the backend scores.
- **Reconnect is thin:** a reload after answering, while locked, or during results leaves the
  player on the lobby screen until the next question.
- **Correctness leaks early:** `answer_received` carries `isCorrect` / `pointsAwarded`, visible in
  dev tools before the reveal.
- **Identity sticks** to whatever unexpired token is in `localStorage` until "Play again" clears it.
- No code is shared with the host or admin apps; `lib/`, `components/ui/` and `types/` are copies
  that have already drifted apart. The exception is `lib/plotGeometry.ts`, which must stay
  byte-identical to the host's (`tests/unit/test_plot_geometry_copies.py` checks it).
