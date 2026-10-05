# frontend/host/src/pages/

## Purpose
The host app's screens: sign-in, room setup, and the big-screen game flow (lobby → question →
results → game over) driven by Socket.io events from the backend.

## Contents
- `LoginPage.tsx` — username/password login (`POST /auth/login`) plus "Sign in with UW NetID":
  on return (`?from=oauth2`, `#oauth2_data=`) it exchanges the temp token at `/auth/exchange-temp`.
  Stores the access token in `localStorage`.
- `HomePage.tsx` — loads my courses, my games and my active sessions. Lists active sessions
  (Rejoin / Delete), and creates a room from a selected course + game (`POST /game/rooms`),
  then navigates to `/game/:code/lobby`. Auto-selects when there is exactly one course or game.
- `game/GameLayout.tsx` — owns the game: opens the Socket.io connection, emits
  `join_room {role: HOST}`, listens to every server event, holds all game state, and exposes it
  via `GameContext` / `useGame()` (including `emitAdvance` → `host_advance` and
  `emitLockQuestion` → `host_lock_question`). **Server events drive navigation** between the
  child routes. Also renders the persistent QR + room-code corner panel.
- `game/LobbyPage.tsx` — big QR code and room code, player count, auto-advance toggle, Start
  (disabled with 0 players).
- `game/QuestionPage.tsx` — prompt, type/grading labels, `TimerBar`, answered count,
  Lock/Unlock, and Show Results. With auto-advance on, advances 1.5 s after the answer phase ends.
- `game/ResultsPage.tsx` — answer reveal: bar chart for MC / TF / multi-select / completeness,
  a word cloud for fill-in-the-blank. Next Question / Show Final Results; auto-advance countdown.
- `game/GameOverPage.tsx` — score histogram (auto-bucketed), average / high / player count, and a
  per-question breakdown card (distribution, correct count, average answer time).

## How it fits in
Routes are declared in `../App.tsx` (`/login`, `/home`, `/game/:code/{lobby,question,results,gameover}`,
all but login behind `RequireAuth`). Pages use `../lib/api` for REST, `../components/ui` for
primitives, and `../types/game.ts` for Socket.io payload types. The host is the only client that
sends `host_advance`; the backend state machine in `backend/app/websocket/gateway.py` decides
what comes next. The host receives the full answer distribution and reveal; players never do.

## Gotchas
- **Adding a question type (T7)** touches `../types/game.ts` (`QuestionPayload.type`,
  `AnswerReveal`), `QuestionPage` (`typeLabel`), `ResultsPage` (`buildBars` / word cloud), and
  `GameOverPage` (`QuestionCard`). Reveal rendering is duplicated between Results and GameOver.
- `ResultsPage` recomputes fill-in-the-blank correctness client-side with its own Levenshtein;
  it must stay consistent with the backend's fuzzy matching or the colours will lie.
- **Reconnect gaps:** `sync_state` restores phase, players, question and lock, but not
  `questionResults` or `gameOver`. Reloading during results shows no chart, and the
  `COMPLETED` / `ABANDONED` statuses aren't handled at all.
- `autoAdvance` is in-memory React state and is lost on reload.
- The player join URL is built from `window.location.origin` + `/player/join`, duplicated in
  `GameLayout` and `LobbyPage`. In Vite dev (host on :5173) that QR points to the wrong origin;
  it is only correct behind nginx (:8080).
- Any socket `error` event replaces the whole screen with an error and a "Back to Home" link.
- `QuestionPage` hides the prompt while the question is locked.
- `answer_phase_ended` is ignored if its `questionId` isn't the current question
  (guards against stale timer tasks); keep that check if you touch it.
- Games and courses are picked independently on `HomePage`; games have no `course_id`.
