# frontend/

## Purpose
The three browser apps of Buzzer. Each is a separate Vite + React 18 + TypeScript + Tailwind npm
project with its own `node_modules`, configs and build; they share no code.

## Contents
Each folder has its own `CLAUDE.md` (package level) and `src/CLAUDE.md` (app level).

| App | Who uses it | Talks to the backend via | Dev port | Served at (:8080) |
|---|---|---|---|---|
| `host/` | Instructor: picks a course they HOST, manages its games and questions, roster and past-session downloads (T4), runs the game on the big screen | REST (`/api/courses`, `/api/games`, `/api/sessions`, `/api/game`) + Socket.io (sends `host_advance`, `host_lock_question`) | 5173 | `/host/` |
| `player/` | Students, on phones: join with a code, answer, see their own score and rank | REST + Socket.io (sends `join_room`, `submit_answer`) | 5174 | `/player/` (also `/`) |
| `admin/` | Admins, on desktop: users and their course/game access, courses (hosts, players, games, Unassigned games), a game's question editor (a copy of the host's), guests, all-session exports; links to host and player apps | REST only (`/api/admin/*`) | 5175 | `/admin/` |

All three are laid out the same way: `src/App.tsx` (routes), `src/pages/` (screens; host and
player have a `game/` subfolder whose `GameLayout.tsx` owns the socket and all live state; host
also has `course/` for the management screens),
`src/components/ui/` (primitives), `src/lib/` (`api` REST client and `cn()`), and `src/theme/`
(the colour tokens and light/dark switching, identical in all three; T9). Host and player
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

The data flows in one direction across the apps: **admin** creates courses and users and grants
course HOST/PLAYER and game access; **host** (a course HOST) builds that course's games and
questions, keeps its roster, starts a room from a game and runs the session; **players** of that
course (or guests) join it.
During a game the backend is the referee. The host gets the full answer distribution and reveal;
each player only gets their own results; admins see finished sessions and download exports.

## Gotchas
Cross-app ones. Each app's `CLAUDE.md` files have the details.
- **Adding a question type (T7)** touches all three apps (the admin app has its own copy of the
  host's question editor, so the editor changes are made twice), on top of the backend
  (`schemas/`, `services/game_service.py`, `services/report_service.py`, `websocket/gateway.py`):
  - host: `pages/course/QuestionEditorPage.tsx` (type option, form state, `build…Payload`,
    `formToPayload`, `questionToForm`, type label, list preview — the only editor since T4),
    `types/game.ts`, `QuestionPage` (`typeLabel`), `ResultsPage` (`buildBars` / word cloud),
    `GameOverPage` (`QuestionCard`)
  - player: `types/game.ts`, `QuestionPage` (new answer UI), `ResultsPage` (`describeAnswer`),
    `GameOverPage` (`describePlayerAnswer`, `describeCorrectAnswer`)
  The editor's `answer_data` keys, the player's `submit_answer` shape and both `types/game.ts`
  files must all match the backend exactly. Today `answer_data` mixes snake_case and camelCase.
  A type with a lot of UI can live in its own modules that those files wire in, as `plot_point`
  does (player `components/PlotPointAnswer`, host `components/PlotScatter` and
  `pages/course/PlotPointEditor`).
- **Copied code that has drifted.** `lib/api.ts` (host and admin are identical, player
  only `get`/`post`; all three share the same error-text logic), `components/ui/` (admin = host
  byte-for-byte; player is a mobile-sized fork, and its `TimerBar` lacks `initialSeconds`), and
  `types/game.ts` (host and player differ). A bug fix in one copy doesn't reach the others. The
  exceptions are checked copies that must stay **byte-identical**: `lib/plotGeometry.ts` (T7
  plot_point; host, player and admin, `tests/unit/test_plot_geometry_copies.py`), `lib/promptMarkup.ts`
  (host, player and admin, `test_prompt_markup_copies.py`) and the whole `src/theme/` folder (all three
  apps, `test_theme_copies.py`). `components/ThemeToggle.tsx` is identical in host and admin but
  not test-checked. `lib/plotDraw.ts` is copied too but differs on purpose (the host's and admin's have a
  projector `scale`; the player's does not).
- **One theme for the product (T9).** Colours exist only in `src/theme/tokens.css` (light in
  `:root`, dark overrides in `[data-theme="dark"]`); components use token classes (`bg-surface`,
  `text-fg-muted`, `bg-option-3`, …). `tests/unit/test_no_raw_colours.py` fails on any palette
  class or colour literal outside `src/theme/`, and `tests/unit/test_theme_contrast.py` checks
  every allowed pair for WCAG AA in both themes; a new pair goes into the spec
  (`docs/plans/t9-theming.md`) and that test together. The choice is one `localStorage` key,
  `buzzer-theme`, so on :8080 a toggle in one app applies to the others on their next load
  (never live); on the dev ports each app keeps its own. `tests/e2e/test_t9_theme_ui.py` covers
  the toggle.
- **Every button, link and field shows the shared focus ring** (`focus-visible:ring-2
  ring-focus ring-offset-2 ring-offset-page`), in all three apps, primitives and pages alike;
  `tests/unit/test_focus_rings.py` fails with file:line on any that doesn't. Clickable things are
  real buttons or links, never `<div onClick>`, so the keyboard can reach them.
- **Nothing checks the frontend types against the backend.** Payload types are hand-written and
  can silently fall out of date when `backend/app/websocket/gateway.py` or the schemas change.
- **Auth is thin everywhere:** route guards only check that a token exists in
  `localStorage['token']` (admin doesn't check the role), there is no token refresh, and an expired
  token shows up as an error rather than a redirect. All three apps on the same origin
  (:8080) share that one `localStorage` key, so logging into one app replaces the others' token.
- **Error text comes from the backend.** All three `lib/api.ts` copies show `body.message`, then
  a string `body.detail`, then a 422 `detail[].msg` list, else `HTTP <status>`. If the backend's
  error shape changes, update all three copies together.
- **Reconnect is incomplete** in both live apps: a reload restores the current question but not
  results or game-over screens, and players who reload after answering wait on the lobby screen.
- **Access is decided by the backend (T4).** Roster, game/question authoring and session
  downloads moved to the host app on top of per-course checks (course HOST + game grant, see
  `docs/plans/t4-ui-restructuring.md`). The frontends only hide what a user can't use; the
  server's 403/409 messages are the real rules.
- **Cross-app links only work behind nginx (:8080):** the admin app's Roster and Host & Play
  links are plain `/host/…` / `/player/` URLs relying on the shared token.
- **Dev vs. production differ:** paths are `/` in dev and `/host/`, `/player/`, `/admin/` in
  production, so the host's player QR code only works on :8080.
- **Build gotchas apply to all three:** `dist/` is a snapshot (empty means nginx 403s), `tsc -b`
  leaves compiled `vite.config.js` / `tailwind.config.js` that shadow the `.ts` configs, and CI's
  `frontend-typecheck` (`npx tsc --noEmit`) is the only automated check. The player app has a
  vitest suite (`npm test` in `frontend/player`: the number parser, numeric_estimate text, the
  plot_point geometry and typed-coordinate rules, and `theme.ts`) that CI does not run. The host
  has no test runner; its plot_point screens are covered by the Playwright tests in `tests/e2e/`.
