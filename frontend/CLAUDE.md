# frontend/

## Purpose
The three browser apps of Buzzer. Each is a separate Vite + React 18 + TypeScript + Tailwind npm
project with its own `node_modules`, configs and build; they share no code.

## Contents
Each folder has its own `CLAUDE.md` (package level) and `src/CLAUDE.md` (app level).

| App | Who uses it | Talks to the backend via | Dev port | Served at (:8080) |
|---|---|---|---|---|
| `host/` | Instructor, on the big screen: creates a room, runs the game, sees answer distributions | REST + Socket.io (sends `host_advance`, `host_lock_question`) | 5173 | `/host/` |
| `player/` | Students, on phones: join with a code, answer, see their own score and rank | REST + Socket.io (sends `join_room`, `submit_answer`) | 5174 | `/player/` (also `/`) |
| `admin/` | Admins, on desktop: courses, rosters, users and access, guests, games and questions, session exports | REST only (`/api/admin/*`) | 5175 | `/admin/` |

All three are laid out the same way: `src/App.tsx` (routes), `src/pages/` (screens; host and
player have a `game/` subfolder whose `GameLayout.tsx` owns the socket and all live state),
`src/components/ui/` (primitives), and `src/lib/` (`api` REST client and `cn()`). Host and player
also have `src/types/game.ts` for socket payloads; admin declares types inside each page.

## How it fits in
```
            admin ──REST──────────────┐
host ──REST + Socket.io──┐            ├─▶ nginx :8080 (/api, /socket.io) ─┐
player ─REST + Socket.io─┴────────────┘                                    ├─▶ backend :8000
      (dev: each Vite server proxies straight to :8000; admin only /api)   ┘
```
The root `package.json` runs them (`npm run dev` starts all three; `dev:host` / `dev:player` /
`dev:admin` start one; `install:all`, `build`). In dev, use the Vite ports; for :8080, run
`npm run build` and nginx serves each `dist/` folder.

The data flows in one direction across the apps: **admin** creates games, questions, rosters and
access grants; **host** picks a course and game and runs a session; **players** join that session.
During a game the backend is the referee. The host gets the full answer distribution and reveal;
each player only gets their own results; admins see finished sessions and download exports.

## Gotchas
Cross-app ones. Each app's `CLAUDE.md` files have the details.
- **Adding a question type (T7)** touches all three apps, on top of the backend
  (`schemas/`, `services/game_service.py`, `services/report_service.py`, `websocket/gateway.py`):
  - admin: `QuestionEditorPage` (type option, form state, `build…Payload`, `formToPayload`,
    `questionToForm`, type label, list preview)
  - host: `types/game.ts`, `QuestionPage` (`typeLabel`), `ResultsPage` (`buildBars` / word cloud),
    `GameOverPage` (`QuestionCard`)
  - player: `types/game.ts`, `QuestionPage` (new answer UI), `ResultsPage` (`describeAnswer`),
    `GameOverPage` (`describePlayerAnswer`, `describeCorrectAnswer`)
  The admin's `answer_data` keys, the player's `submit_answer` shape and both `types/game.ts`
  files must all match the backend exactly. Today `answer_data` mixes snake_case and camelCase.
- **Copied code that has drifted.** `lib/api.ts` (admin's has the most methods, player's the
  fewest), `components/ui/` (admin = host byte-for-byte; player is a mobile-sized fork, and its
  `TimerBar` lacks `initialSeconds`), and `types/game.ts` (host and player differ). A bug fix in
  one copy doesn't reach the others.
- **Nothing checks the frontend types against the backend.** Payload types are hand-written and
  can silently fall out of date when `backend/app/websocket/gateway.py` or the schemas change.
- **Auth is thin everywhere:** route guards only check that a token exists in
  `localStorage['token']` (admin doesn't check the role), there is no token refresh, and an expired
  token shows up as error messages rather than a redirect. All three apps on the same origin
  (:8080) share that one `localStorage` key, so logging into one app replaces the others' token.
- **Reconnect is incomplete** in both live apps: a reload restores the current question but not
  results or game-over screens, and players who reload after answering wait on the lobby screen.
- **Admin-only features (T4):** roster import, game and question authoring, the HTML report and
  Canvas export exist only in the admin app and only behind `require_admin` on the backend.
  Moving any of them into the host app needs per-course permission checks on the backend, not
  just new screens.
- **Dev vs. production differ:** paths are `/` in dev and `/host/`, `/player/`, `/admin/` in
  production, so the host's player QR code only works on :8080.
- **Build gotchas apply to all three:** `dist/` is a snapshot (empty means nginx 403s), `tsc -b`
  leaves compiled `vite.config.js` / `tailwind.config.js` that shadow the `.ts` configs, and CI's
  `frontend-typecheck` (`npx tsc --noEmit`) is the only automated check; there are no frontend tests.
