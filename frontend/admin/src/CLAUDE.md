# frontend/admin/src/

## Purpose
The Admin app: a desktop dashboard for setting up and reviewing games. Admins manage courses and
rosters, users and their access, guests, games and questions, and download session results. It
uses REST only; it takes no part in a live game.

## Contents
Top-level files:
- `main.tsx` — React entry; renders `<App />` in `StrictMode` and imports `index.css`.
- `App.tsx` — the router plus the shell. `/login` is public; everything else sits inside
  `RequireAdmin` (checks only that a token exists) and `AdminLayout` (sidebar: Courses, Users,
  Games, Guests, Sessions, Logout). Routes: `/courses`, `/courses/:courseId/roster`, `/users`,
  `/users/:userId`, `/guests`, `/games`, `/games/:gameId/questions`, `/sessions`; anything else
  goes to `/courses`. `basename` is `import.meta.env.BASE_URL` (`/admin/` in production, `/` in dev).
- `index.css` — Tailwind directives and the global dark background.

Subdirectories (each has its own `CLAUDE.md`):
- `pages/` — the nine screens. The biggest are `QuestionEditorPage` (per-type question forms and
  the form ↔ `config` / `answer_data` conversion), `RosterPage` (client-side CSV import wizard
  with Canvas auto-detection) and `SessionsPage` (CSV / Canvas exports and the HTML report).
- `components/` — `ui/` primitives (`Button`, `Card`, `Input`), identical copies of the host's.
- `lib/` — `api` with `get/post/put/patch/delete` plus `postForm` (uploads) and `download`
  (file exports), and `cn()`.

## How it fits in
```
App.tsx (RequireAdmin + AdminLayout) ──▶ pages/ ──REST──▶ lib/api ──▶ /api/admin/* ──▶ backend :8000
                                          uses components/ui
```
In dev, Vite (:5175) proxies `/api` to the backend; in production nginx serves the build at
`/admin/`. Every endpoint it uses is in `backend/app/routers/admin.py` and guarded by
`require_admin`, except session delete (`/api/game/sessions/:id`). Data created here is what the
other two apps consume: games and questions are what the host runs, and rosters plus course and
game access decide who can host or play.

## Gotchas
Cross-cutting ones. Each subdirectory's `CLAUDE.md` has the details.
- **No shared types.** There is no `types/` folder; each page declares its own interfaces
  (`Course`, `Game`, …), so the same shape is repeated across pages and can drift from the
  backend's `schemas/admin.py`.
- **Adding a question type (T7)** on the admin side is mostly `QuestionEditorPage` (about six
  places; see `pages/CLAUDE.md`), on top of the backend, host and player changes. The `answer_data`
  keys must match the backend validator exactly, and they mix snake_case and camelCase today.
- **Auth is thin:** `RequireAdmin` doesn't check the role, so a non-admin login reaches the
  dashboard and then sees "Admin access required" errors; there is no refresh or 401 redirect.
- **Missing operations:** courses can't be deleted (no UI and no endpoint).
- No code is shared with the host or player apps; `lib/` and `components/ui/` are copies.
