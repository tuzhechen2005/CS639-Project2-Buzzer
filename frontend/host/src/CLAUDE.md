# frontend/host/src/

## Purpose
The Host app: the instructor's app. Course-first since T4: the host picks a course they HOST,
then manages its games and questions, roster and past-session downloads, starts a room from a
game, and runs the live game (lobby → question → results → game over) on the big screen over
Socket.io. It is the only client that can advance or lock questions.

## Contents
Top-level files:
- `main.tsx` — React entry; renders `<App />` in `StrictMode` and imports `index.css`.
- `App.tsx` — the router. `/login`, `/home` (course picker),
  `/courses/:courseId/{games,roster,sessions}` and `/courses/:courseId/games/:gameId/questions`
  (nested under `CourseLayout`), and `/game/:code/{lobby,question,results,gameover}` (nested
  under `GameLayout`); everything except login is wrapped in `RequireAuth`, which only checks
  that `localStorage.token` exists and otherwise sends you to `/login`, remembering the page
  (`state.from`). `/` and unknown paths go to `/home` when a token exists (an admin arriving
  from the admin app's Host & Play link is already signed in), else to `/login`.
  `basename` is `import.meta.env.BASE_URL` (`/host/` in production builds, `/` in dev).
- `index.css` — Tailwind directives plus the global dark background (`#0f172a`).
- `types/game.ts` — hand-written TypeScript shapes for every Socket.io payload the host receives
  (`SyncStatePayload`, `QuestionPayload`, `HostResultsPayload`, `AnswerReveal`,
  `HostGameOverPayload`, …) and the `HostPhase` union.

Subdirectories (each has its own `CLAUDE.md`):
- `pages/` — all screens. `course/` holds the management screens (layout with tabs, games,
  question editor, roster wizard, past sessions); `game/GameLayout.tsx` owns the socket connection
  and all game state, exposes it through `useGame()`, and navigates between the game routes when
  server events arrive.
- `components/` — `ui/` primitives: `Button`, `Card`, `Input`, and the display-only `TimerBar`.
- `lib/` — `api` (REST over `fetch` with `get/post/put/patch/delete`, `postForm`, `download`,
  bearer token from `localStorage`, readable error messages) and `cn()`.

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
- **`types/game.ts` is a manual mirror of the backend payloads.** Nothing checks it against the
  server; when a gateway payload changes, update this file by hand. The player app has its own,
  different copy.
- **Adding a question type (T7)** on the host side touches the question editor
  (`pages/course/QuestionEditorPage.tsx`, the only editor since T4), `types/game.ts`,
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
- No code is shared with the player or admin apps; `lib/` and `components/ui/` are copies.
