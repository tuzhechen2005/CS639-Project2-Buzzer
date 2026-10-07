# frontend/admin/src/

## Purpose
The Admin app: an admin-first desktop dashboard (T4). Admins manage user accounts and their
course/game access, create and edit courses (and see each course's hosts, players and games,
including Unassigned games to move), merge or delete guests, and export results for any session.
Rosters and running a room happen in the host and player apps, linked from a secondary
"Host & Play" group. Admins can also create and edit a game's questions here, in a copy of the
host's question editor (all six types, including numeric_estimate and plot_point), reached from
a game's **Questions** link on the Courses page. It uses REST only; it takes no part in a live
game.

## Contents
Top-level files:
- `main.tsx` — React entry; calls `initTheme()` (from `theme/theme.ts`) before rendering
  `<App />` in `StrictMode`, and imports `index.css`.
- `App.tsx` — the router plus the shell. `/login` is public; everything else sits inside
  `RequireAdmin` (checks only that a token exists) and `AdminLayout` (sidebar: Users, Courses,
  Guests, Sessions, then "Host & Play" links to `/host/` and `/player/`, and the theme toggle
  and Logout in the footer). Routes: `/users`, `/users/:userId`, `/courses`,
  `/courses/:courseId/games/:gameId/questions` (the question editor), `/guests`, `/sessions`;
  anything else goes to `/users`. `basename` is `import.meta.env.BASE_URL`
  (`/admin/` in production, `/` in dev).
- `index.css` — imports `theme/tokens.css` first, then the Tailwind directives.
- `theme/` — (T9) everything about colour, **byte-identical in host, player and admin**
  (`tests/unit/test_theme_copies.py`): `tokens.css` (the light values in `:root`, the dark
  overrides in `[data-theme="dark"]`, as RGB channels), `colors.js` + `colors.d.ts` (the Tailwind
  colour map, `rgb(var(--x) / <alpha-value>)`), and `theme.ts` (`getStoredTheme`,
  `currentTheme`, `tokenColor`, `applyTheme`, `setTheme`, `initTheme`; the choice is
  `localStorage['buzzer-theme']`, else the OS). The only folder allowed to contain colours.

Subdirectories (each has its own `CLAUDE.md`):
- `types/game.ts` — a copy of the host's question and payload types, which the copied editor
  modules import.
- `pages/` — seven screens: Login, Users, UserDetail (course and game grants, inactive-grant
  badges), Courses (hosts, players, games with a Questions link, Unassigned games), Guests,
  Sessions (CSV / Canvas exports and the HTML report), and GameQuestions (the question editor,
  in `pages/course/`). The roster wizard lives only in the host app.
- `components/` — `ui/` primitives (`Button`, `Card`, `Input`) and `ThemeToggle`, identical
  copies of the host's, plus the editor's `PlotScatter`, `PromptText` and `ui/QuestionImage`.
- `lib/` — `api` (identical to the host's: `get/post/put/patch/delete`, `postForm`, `putForm`,
  `download`), readable error messages, `cn()`, and the editor's `images`, `numericEstimate`,
  `plotDraw`, `plotGeometry`, `plotPalette`, `plotPoint` and `promptMarkup`.

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
- **Colours come only from theme tokens (T9).** Use `bg-surface`, `text-fg-muted`,
  `border-line-strong`, … — never palette classes (`bg-slate-800`, `text-white`) or hex/rgb
  values; `tests/unit/test_no_raw_colours.py` fails on any. A new foreground/background pair
  must be added to the spec's allowed pairs and `tests/unit/test_theme_contrast.py` (WCAG AA,
  both themes). Change `src/theme/` in all three apps at once, or the copy test fails.
Cross-cutting ones. Each subdirectory's `CLAUDE.md` has the details.
- **Mostly no shared types.** The pages declare their own interfaces (`Course`, `Game`, …), so
  the same shape is repeated and can drift from the backend's `schemas/admin.py`. The one
  exception is `types/game.ts`, a copy of the host's that only the question editor uses.
- **The question editor is a copy of the host's.** `pages/course/QuestionEditorPage.tsx`,
  `PlotPointEditor.tsx` and `ImageLibrary.tsx`, with the components and `lib/` modules they
  import, were copied unchanged, except that `Game` is declared in `QuestionEditorPage.tsx`
  instead of imported from the host's `GamesTab`. Adding a question type (T7) therefore means
  editing the host's editor **and** this copy. It calls the course routes (`/games/:id/…`),
  which an admin passes; Unassigned games have no Questions link, because those routes refuse
  the system course (move the game to a real course first).
- **Cross-app links only work behind nginx (:8080):** the Roster and Host & Play links are plain
  `/host/…` and `/player/` URLs and rely on the shared `localStorage['token']`.
- **Auth is thin:** `RequireAdmin` doesn't check the role, so a non-admin login reaches the
  dashboard and then sees "Admin access required" errors on every page; there is no refresh or 401
  redirect.
- **Missing operations:** courses can't be deleted (no UI and no endpoint).
- No code is shared with the host or player apps; `lib/` and `components/ui/` are copies.
  `lib/plotGeometry.ts` must stay byte-identical in all three (`tests/unit/test_plot_geometry_copies.py`).
