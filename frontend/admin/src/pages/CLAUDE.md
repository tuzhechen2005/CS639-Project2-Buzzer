# frontend/admin/src/pages/

## Purpose
The admin dashboard screens, admin-first since T4: user accounts and their course/game access,
courses (with their hosts, players and games), guests, and all past sessions with their exports.
Game, question and roster editing moved to the host app (`frontend/host/src/pages/course/`).

## Contents
- `LoginPage.tsx` — username/password login (`POST /auth/login`), stores the token, goes to
  `/users`. No UW NetID button (unlike host and player). Theme toggle fixed top-right.
- `UsersPage.tsx` — list users (role badge); create a local account (username, display name,
  password ≥ 8 chars, optional email).
- `UserDetailPage.tsx` — edit a user (display name, email, password, role), delete them, and grant
  or revoke **course access** (HOST or PLAYER per course; the system course is never offered) and
  **game access**. The game picker only offers games from courses the user is HOST of (the
  backend returns 409 `NOT_COURSE_HOST` otherwise); each game shows its course, and grants whose
  game's course the user no longer hosts get an **inactive** badge and can be revoked. Grants run
  in parallel (`Promise.allSettled`) and every failure's message is shown.
- `CoursesPage.tsx` — create and edit (name + semester) courses. Per course: its HOSTs and
  PLAYERs (from `GET /admin/courses/:id/access`, linking to user detail), its games (with a
  "played" badge and Delete, `DELETE /admin/games/:id`), and a **Roster** link to the host app
  (`/host/courses/:id/roster`). The system course is hidden; its games appear in an
  **Unassigned games** section with a course picker (`PUT /admin/games/:id {course_id}`) and Delete.
- `GuestsPage.tsx` — list guest accounts, merge a guest's scores into a netid
  (`POST /admin/users/merge-guest`), delete a guest and their scores.
- `SessionsPage.tsx` — all sessions filtered by status; per session: score export (plain CSV or
  Canvas-gradebook CSV with assignment title, SIS domain, roster-only and per-question options),
  the HTML report, and delete (the confirm warns that recorded scores — grades — are deleted).

## How it fits in
Routes are declared in `../App.tsx`: everything except `/login` sits inside `RequireAdmin` and the
sidebar `AdminLayout` (Users, Courses, Guests, Sessions, then a secondary "Host & Play" group
linking to `/host/` and `/player/`; the theme toggle and Logout in its footer); unknown paths
go to `/users`. Each page loads its own data
with `../lib/api` on mount and re-fetches after each change; there is no shared store or cache.
Backend endpoints are in `backend/app/routers/admin.py` (all `require_admin`), except session
delete (`/game/sessions/:id`).

## Gotchas
- **Host and player work happens in the other apps.** The Roster and Host & Play links are plain
  `/host/…` and `/player/` URLs: they work behind nginx on :8080, where the apps share
  `localStorage['token']`, not under the Vite dev servers (separate ports).
- `GET /admin/courses` and `GET /admin/games` include the system course and its games
  (`is_system`, `course_id`); the pages filter them. Moving a game to a course grants it to that
  course's HOSTs (backend); moving into the system course or while the game is live returns 409.
- **There is no way to delete a course** (no button and no backend endpoint).
- Deleting a game also deletes its sessions and scores (grades); played games get a stronger
  `confirm()` warning. Deletes use the browser's `confirm()`.
- `CoursesPage` makes one `/access` request per course on load; fine for a class's worth of
  courses, slow with hundreds.
