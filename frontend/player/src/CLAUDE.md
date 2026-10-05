# frontend/player/src/

## Purpose
The Player app: what students open on their phones. They enter a room code, identify themselves
(guest, UW NetID, or local account), then answer questions live over Socket.io and see their own
score and rank.

## Contents
Top-level files:
- `main.tsx` — React entry; renders `<App />` in `StrictMode` and imports `index.css`.
- `App.tsx` — the router: `/join`, `/login` (OAuth2 return), `/name/:code`, and
  `/game/:code/{lobby,question,feedback,results,gameover}` nested under `GameLayout`. Anything else
  redirects to `/join`. No route guard; `GameLayout` checks the token itself.
  `basename` is `import.meta.env.BASE_URL` (`/player/` in production builds, `/` in dev).
- `index.css` — Tailwind directives, global dark background, and no tap-highlight flash on mobile.
- `types/game.ts` — hand-written shapes for the Socket.io payloads a player receives
  (`SyncStatePayload`, `QuestionPayload`, `AnswerResultPayload`, `PlayerResultsPayload`,
  `PlayerAnswerReveal`, `PlayerGameOverPayload`, …) and the `PlayerPhase` union.

Subdirectories (each has its own `CLAUDE.md`):
- `pages/` — all screens. `game/GameLayout.tsx` owns the socket and all game state, exposes it via
  `useGame()` (including `emitAnswer`), and navigates when server events arrive.
- `components/` — `ui/` primitives (`Button`, `Card`, `Input`, `TimerBar`), mobile-sized forks of
  the host's.
- `lib/` — `api` (REST over `fetch`), `cn()`, and `isTokenExpired()`.

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
  that have already drifted apart.
