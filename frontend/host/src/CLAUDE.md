# frontend/host/src/

## Purpose
The Host app: the instructor's app. Course-first since T4: the host picks a course they HOST,
then manages its games and questions, roster and past-session downloads, starts a room from a
game, and runs the live game (lobby → question → results → game over) on the big screen over
Socket.io. It is the only client that can advance or lock questions.

## Contents
Top-level files:
- `main.tsx` — React entry; calls `initTheme()` (from `theme/theme.ts`) before rendering
  `<App />` in `StrictMode`, and imports `index.css`.
- `App.tsx` — the router. `/login`, `/home` (course picker),
  `/courses/:courseId/{games,roster,sessions}` and `/courses/:courseId/games/:gameId/questions`
  (nested under `CourseLayout`), and `/game/:code/{lobby,question,results,gameover}` (nested
  under `GameLayout`); everything except login is wrapped in `RequireAuth`, which only checks
  that `localStorage.token` exists and otherwise sends you to `/login`, remembering the page
  (`state.from`). `/` and unknown paths go to `/home` when a token exists (an admin arriving
  from the admin app's Host & Play link is already signed in), else to `/login`.
  `basename` is `import.meta.env.BASE_URL` (`/host/` in production builds, `/` in dev).
- `index.css` — imports `theme/tokens.css` first, then the Tailwind directives.
- `theme/` — (T9) everything about colour, **byte-identical in host, player and admin**
  (`tests/unit/test_theme_copies.py`): `tokens.css` (the light values in `:root`, the dark
  overrides in `[data-theme="dark"]`, as RGB channels), `colors.js` + `colors.d.ts` (the Tailwind
  colour map, `rgb(var(--x) / <alpha-value>)`), and `theme.ts` (`getStoredTheme`,
  `currentTheme`, `tokenColor`, `applyTheme`, `setTheme`, `initTheme`; the choice is
  `localStorage['buzzer-theme']`, else the OS). The only folder allowed to contain colours.
- `types/game.ts` — hand-written TypeScript shapes for every Socket.io payload the host receives
  (`SyncStatePayload`, `QuestionPayload`, `HostResultsPayload`, `AnswerReveal`,
  `HostGameOverPayload`, …) and the `HostPhase` union.

Subdirectories (each has its own `CLAUDE.md`):
- `pages/` — all screens. `course/` holds the management screens (layout with tabs, games,
  question editor, roster wizard, past sessions); `game/GameLayout.tsx` owns the socket connection
  and all game state, exposes it through `useGame()`, and navigates between the game routes when
  server events arrive.
- `components/` — `ui/` primitives (`Button`, `Card`, `Input`, the display-only `TimerBar`,
  `QuestionImage`), `PlotScatter`, the one renderer for every host view of a plot_point plane
  (game question, results, game-over card, editor preview), `PromptText`, and `ThemeToggle`
  (placed on the home, course, login and game screens).
- `lib/` — `api` (REST over `fetch` with `get/post/put/patch/delete`, `postForm`, `download`,
  bearer token from `localStorage`, readable error messages), `cn()`, `images`,
  `numericEstimate` (band bars), and the plot_point modules: `plotGeometry` (pure plane geometry,
  byte-identical to the player's copy), `plotPalette` (canvas colours from the theme tokens),
  `plotDraw` (canvas painting with a projector `scale`) and `plotPoint` (config and reveal
  helpers).

## How it fits in
```
App.tsx (routes) ──▶ pages/ ──REST──▶ lib/api ──▶ /api/*        ─┐
                       │                                          ├─▶ backend :8000
                       └──Socket.io (GameLayout)──▶ /socket.io/* ─┘
                       uses components/ui, types/game.ts
```
In dev, Vite (:5173) proxies `/api` and `/socket.io` to the backend on :8000; in production the
build is served by nginx at `/host/` and the same paths are proxied there. The backend is the
referee: the host receives the full answer distribution and reveal after each question closes,
which players never get. The protocol it speaks is defined in `backend/app/websocket/events.py`
and `gateway.py`.

## Gotchas
Cross-cutting ones. Each subdirectory's `CLAUDE.md` has the details.
- **Colours come only from theme tokens (T9).** Use `bg-surface`, `text-fg-muted`,
  `border-line-strong`, … — never palette classes (`bg-slate-800`, `text-white`) or hex/rgb
  values; `tests/unit/test_no_raw_colours.py` fails on any. A new foreground/background pair
  must be added to the spec's allowed pairs and `tests/unit/test_theme_contrast.py` (WCAG AA,
  both themes). Change `src/theme/` in all three apps at once, or the copy test fails. Canvases
  get colours through `tokenColor()` at draw time and redraw on the `themechange` event.
- **Game screens are projected:** keep new text on the host type scale (body ≥ `text-xl`,
  counts `text-2xl`; see `pages/CLAUDE.md`).
- **`types/game.ts` is a manual mirror of the backend payloads.** Nothing checks it against the
  server; when a gateway payload changes, update this file by hand. The player app has its own,
  different copy.
- **Adding a question type (T7)** on the host side touches the question editor
  (`pages/course/QuestionEditorPage.tsx`, the only editor since T4, or a sibling module it wires
  in, as `pages/course/PlotPointEditor.tsx` does for plot_point), `types/game.ts`,
  `QuestionPage`, `ResultsPage` and `GameOverPage` (see `pages/CLAUDE.md`), on top of the backend
  changes.
- **Access is enforced by the backend.** The course pages only hide what the user can't use
  (`CourseLayout` checks `my-courses`); every rule — course HOST, game grant, locked, live,
  system course — is the server's, and its 403/409 messages are shown as-is.
- **Auth is thin:** a token's presence is the only route guard, there is no refresh or 401
  redirect, and logout just deletes the token.
- **Reconnect is partial:** a reload restores the phase and current question but not results or
  game-over data.
- **Dev vs. production paths differ** (`/` vs `/host/`). The player join QR code is only correct
  behind nginx on :8080.
- No code is shared with the player or admin apps; `lib/` and `components/ui/` are copies. The
  exception is `lib/plotGeometry.ts`, which must stay byte-identical to the player's
  (`tests/unit/test_plot_geometry_copies.py` checks it; its unit tests live in the player app).
