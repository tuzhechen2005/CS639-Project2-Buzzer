# frontend/player/src/pages/

## Purpose
The player's phone screens: entering a room code, choosing how to identify (guest, UW NetID, or
local account), then the live game (lobby → question → feedback → results → game over) driven by
Socket.io events.

## Contents
- `JoinPage.tsx` — 6-character room code entry; validates with `GET /game/rooms/:code/ping`, then
  goes to `/name/:code`. Auto-submits when opened from the host's QR code (`?code=`).
- `NamePage.tsx` — three modes: **guest** (display name + email → `POST /auth/guest`, remembers
  both in `localStorage`), **UW NetID** (link to the OAuth2 flow; stashes the room code in
  `sessionStorage['joinRoomCode']`), and **local account** (`POST /auth/login`). If a non-expired
  token already exists, it skips all of that and shows a single "Join Game" button.
- `LoginPage.tsx` — OAuth2 return landing page only (`?from=oauth2#oauth2_data=`): exchanges the
  temp token at `/auth/exchange-temp`, then returns to `/name/<saved code>`. Anything else
  redirects to `/join`.
- `game/GameLayout.tsx` — owns the game: checks the token, opens Socket.io, emits
  `join_room {role: PLAYER}`, listens to server events, holds state in `GameContext` /
  `useGame()`, and exposes `emitAnswer` → `submit_answer`. **Server events drive navigation.**
  Shows a "Host disconnected" banner. Disconnects itself after `game_over`.
- `game/LobbyPage.tsx` — room code, spinner, player count; "waiting for host to start" or
  "waiting for next question" depending on game status.
- `game/QuestionPage.tsx` — one layout per question type: coloured MC buttons (tap = submit),
  True/False, a text box for fill-in-the-blank, toggle-and-submit for multi-select, and for
  numeric_estimate a decimal text box with a ± button, an echo line ("= 1,665 steps") and a
  Submit that is enabled only when `lib/parseNumber` accepts the text. Measures
  answer time from when the page mounted. Disables input while the host has locked the question.
- `game/FeedbackPage.tsx` — static "Answer locked in!" screen shown after `answer_received`.
- `game/ResultsPage.tsx` — Correct / Close! (partial numeric credit) / Incorrect / "Answer recorded"
  (completeness), what you answered, accepted answers for fill-in-the-blank, target, difference and
  band for numeric_estimate, points for this question, running total and rank.
- `game/GameOverPage.tsx` — final score and rank, plus a per-question list of your answer vs the
  correct one. "Play again" clears the token and goes to `/join`.

## How it fits in
Routes are declared in `../App.tsx` (`/join`, `/login`, `/name/:code`,
`/game/:code/{lobby,question,feedback,results,gameover}`; anything else → `/join`). There is no
route guard; `GameLayout` does the token check itself. Pages use `../lib`, `../components/ui`, and
`../types/game.ts`. Players only ever *receive* their own results (points, score, rank) and the
answer reveal after the question closes; the full distribution goes only to the host.

## Gotchas
- **Adding a question type (T7)** touches `../types/game.ts` (`QuestionPayload.type`,
  `PlayerAnswerReveal`, `QuestionSummaryItem.playerAnswer`), `QuestionPage` (a new branch; unknown
  types fall through to "Unsupported question type"), `ResultsPage` (`describeAnswer`) and
  `GameOverPage` (`describePlayerAnswer`, `describeCorrectAnswer`). The answer shape you emit must
  match what `backend/app/websocket/gateway.py` and `services/game_service.py` expect.
- `ResultsPage.describeAnswer` has no `multi_select` case, so multi-select results never show
  "You answered". It also shows "Correct!" for any points > 0 (partial multi-select credit
  included) and "Incorrect" when the player didn't answer at all.
- **Reconnect is thin.** `sync_state` only restores player count, lock and status; the payload's
  `currentQuestion`, `hasAnswered` and `yourScore` are ignored. The backend re-sends the open
  question only if the player hasn't answered and it isn't locked, so a player who reloads after
  answering, while locked, or during results sits on the lobby screen until the next question.
- **Answer correctness reaches the client early.** The backend's `answer_received` includes
  `isCorrect` and `pointsAwarded`. `FeedbackPage` doesn't display them, but they are visible in
  the browser's dev tools before the host reveals results.
- `emitAnswer` is fire-and-forget: if the socket is down, the button stays disabled and nothing
  retries. Duplicate-submit echoes (`alreadyAnswered: true`) are ignored.
- **Identity sticks.** Any unexpired token (a previous guest or account) skips the mode picker on
  `NamePage`; the only way to switch is "Play again" on the game-over screen, which clears it.
  Guests aren't tied to a room, so an old guest token works in any room.
- `GameLayout` ignores `connect_error` and `error` after game over, because it disconnects on purpose.
