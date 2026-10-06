# frontend/admin/src/

## Purpose
The Admin app: an admin-first desktop dashboard (T4). Admins manage user accounts and their
course/game access, create and edit courses (and see each course's hosts, players and games,
including Unassigned games to move), merge or delete guests, and export results for any session.
Host and player work (games, questions, rosters, running a room) happens in the host and player
apps, linked from a secondary "Host & Play" group. It uses REST only; it takes no part in a live
game.

## Contents
Top-level files:
- `main.tsx` — React entry; renders `<App />` in `StrictMode` and imports `index.css`.
- `App.tsx` — the router plus the shell. `/login` is public; everything else sits inside
  `RequireAdmin` (checks only that a token exists) and `AdminLayout` (sidebar: Users, Courses,
  Guests, Sessions, then "Host & Play" links to `/host/` and `/player/`, and Logout). Routes:
  `/users`, `/users/:userId`, `/courses`, `/guests`, `/sessions`; anything else goes to `/users`. `basename` is `import.meta.env.BASE_URL` (`/admin/` in production, `/` in dev).
- `index.css` — Tailwind directives and the global dark background.

Subdirectories (each has its own `CLAUDE.md`):
- `pages/` — six screens: Login, Users, UserDetail (course and game grants, inactive-grant
  badges), Courses (hosts, players, games, Unassigned games), Guests, Sessions (CSV / Canvas
  exports and the HTML report). The question editor and roster wizard moved to the host app.
- `components/` — `ui/` primitives (`Button`, `Card`, `Input`), identical copies of the host's.
- `lib/` — `api` with `get/post/put/patch/delete` plus `postForm` and `download` (file exports),
  readable error messages, and `cn()`.

## How it fits in
```
App.tsx (RequireAdmin + AdminLayout) ──▶ pages/ ──REST──▶ lib/api ──▶ /api/admin/* ──▶ backend :8000
                                          uses components/ui
```
In dev, Vite (:5175) proxies `/api` to the backend; in production nginx serves the build at
`/admin/`. Every endpoint it uses is in `backend/app/routers/admin.py` and guarded by
`require_admin`, except session delete (`/api/game/sessions/:id`). The access granted here is
what the other two apps rely on: course HOST plus a game grant decides which games a host can
manage and run, and course access and rosters decide who can play.

## Gotchas
Cross-cutting ones. Each subdirectory's `CLAUDE.md` has the details.
- **No shared types.** There is no `types/` folder; each page declares its own interfaces
  (`Course`, `Game`, …), so the same shape is repeated across pages and can drift from the
  backend's `schemas/admin.py`.
- **No question editor here any more.** Adding a question type (T7) touches the host app's
  `pages/course/QuestionEditorPage.tsx`, not this app.
- **Cross-app links only work behind nginx (:8080):** the Roster and Host & Play links are plain
  `/host/…` and `/player/` URLs and rely on the shared `localStorage['token']`.
- **Auth is thin:** `RequireAdmin` doesn't check the role, so a non-admin login reaches the
  dashboard and then sees "Admin access required" errors on every page; there is no refresh or 401
  redirect.
- **Missing operations:** courses can't be deleted (no UI and no endpoint).
- No code is shared with the host or player apps; `lib/` and `components/ui/` are copies.
