# frontend/host/src/pages/

## Purpose
The host app's screens: sign-in, a course picker, per-course management (games and questions,
roster, past sessions — T4), and the big-screen game flow (lobby → question → results → game
over) driven by Socket.io events from the backend.

## Contents
- `LoginPage.tsx` — username/password login (`POST /auth/login`) plus "Sign in with UW NetID":
  on return (`?from=oauth2`, `#oauth2_data=`) it exchanges the temp token at `/auth/exchange-temp`
  (its error text is read as `message`, then `detail`). Stores the access token in
  `localStorage`, then returns to the page `RequireAuth` remembered (`state.from`), else `/home`;
  the SSO round trip always lands on `/home`. It does not skip itself when a token exists, so
  the form stays reachable with an expired token.
- `HomePage.tsx` — the **course picker**: lists `GET /game/my-courses` (courses the user hosts;
  admins see all, never the system course) and opens `/courses/:id/games`. Keeps the "Active
  Sessions" card (Rejoin / Delete); the Delete confirm warns that recorded scores (grades) are
  permanently deleted.
- `course/CourseLayout.tsx` — course header plus Games / Roster / Past Sessions tabs. There is no
  single-course endpoint, so it finds the course in `my-courses`; a course the user doesn't host
  (or the system course) shows "You don't have access to this course" and no tabs. Exposes the
  course to children via `useCourse()` (outlet context). On the editor route it hides the tabs
  and shows "← Back to Games".
- `course/GamesTab.tsx` — `GET /courses/:id/games` (only games the user holds a grant for).
  Create (`POST /courses/:id/games`) and Import JSON (`POST /courses/:id/games/import`) both open
  the new game's editor. Per game: **Start room** (`POST /game/rooms` → lobby), a "Played — locked"
  badge with **Duplicate to edit** (`POST /games/:id/duplicate`), otherwise **Edit questions** and
  Delete (no Delete on locked games).
- `course/QuestionEditorPage.tsx` — moved from the admin app; route
  `/courses/:courseId/games/:gameId/questions`. Loads `GET /games/:id` and its questions,
  redirects if the game's `course_id` differs from the URL, has an editable details header
  (title, description, max players — editable even when locked), per-type `QuestionForm`
  (`formToPayload` / `questionToForm`), add / edit / delete / reorder, Export JSON. Locked games
  are read-only with Duplicate. Answer keys are shown only here.
- `course/RosterTab.tsx` — moved from the admin app. Client-side CSV wizard (`parseCSV`, Canvas
  auto-detection, column mapping) posting mapped rows to `POST /courses/:id/roster/import`, with
  an **Add only (default) / Replace** mode, a mandatory dry-run preview (`dry_run=true`) and, in
  Replace mode with deactivations, a confirm naming how many students will be deactivated. Rows
  the mapping skips (an empty netid, name or email) are listed after the preview; in Replace
  mode, skipped or server-rejected rows need a second confirm. Inline entry edit via
  `PATCH /courses/:id/roster/:entryId`.
- `course/SessionsTab.tsx` — `GET /courses/:id/sessions` (completed and abandoned) with Summary
  (HTML, `/sessions/:id/report`), Scores (CSV, `/sessions/:id/export?format=raw`) and Canvas CSV
  (form: title, assignment id, SIS domain, roster-only, per-question). Downloads only, no delete.
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
Routes are declared in `../App.tsx`: `/login`, `/home`, `/courses/:courseId/{games,roster,sessions}`
and `/courses/:courseId/games/:gameId/questions` (children of `CourseLayout`), and
`/game/:code/{lobby,question,results,gameover}`; all but login sit behind `RequireAuth`. Pages use
`../lib/api` for REST (the course pages use the neutral `/api/courses`, `/api/games`,
`/api/sessions` endpoints from `backend/app/routers/{courses,games,sessions}.py`, which enforce
course HOST + game grant), `../components/ui` for primitives, and `../types/game.ts` for
Socket.io payload types. The host is the only client that
sends `host_advance`; the backend state machine in `backend/app/websocket/gateway.py` decides
what comes next. The host receives the full answer distribution and reveal; players never do.

## Gotchas
- Images (T8): `QuestionPage` shows the prompt image under the prompt; `ResultsPage` and the
  game-over `QuestionCard` show the prompt image and a small thumbnail per option that has one
  (all through `components/ui/QuestionImage`).
- **Adding a question type (T7)** touches `course/QuestionEditorPage.tsx` (type option, form
  state, `build…Payload`, `formToPayload`, `questionToForm`, type label, list preview),
  `../types/game.ts` (`QuestionPayload.type`, `AnswerReveal`), `game/QuestionPage` (`typeLabel`),
  `game/ResultsPage` (`buildBars` / word cloud), and `game/GameOverPage` (`QuestionCard`). Reveal
  rendering is duplicated between Results and GameOver. `answer_data` keys mix snake_case
  (`answer_points`) and camelCase (FITB `acceptedAnswers`, `answerPoints`, `editDistance`); match
  the backend validator exactly.
- **Locked / live games:** the server returns 409 `GAME_LOCKED` / `GAME_LIVE` for question changes;
  the editor shows the message and reloads after any failed question change, so a game that
  became locked while open switches to the read-only view at that point (not before).
- **Roster replace mode deactivates everyone missing from the file**, including rows the wizard
  skipped (they are never sent). The dry-run preview and the two confirms are the only guard,
  so keep them if you change the wizard. The preview is tied to the settings it was run with:
  `previewSeq` is bumped on every mapping or mode change, and a dry-run reply for older
  settings is dropped, so stale counts can't unlock Import. Canvas exports usually contain a
  "Test Student" row with no SIS login, which is why skipped rows need a confirm rather than
  blocking Replace.
- **`points_value` is computed in the editor** for accuracy questions (MC / FITB: highest option;
  TF: higher of the two; multi-select: sum of positive options); only completeness questions use
  the typed-in value. Imported or API-created questions don't go through this.
- **Two roster CSV parsers:** the wizard parses CSVs itself and posts mapped rows to
  `/roster/import`, while `POST /courses/:id/roster` (raw upload, the README's curl example)
  parses on the backend. They can disagree on the same file.
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
- Games belong to a course: Start room sends the game's own course, and the backend rejects a
  mismatch (400 `COURSE_MISMATCH`). A newly added HOST sees no games until an admin grants them
  (no retroactive grants).
