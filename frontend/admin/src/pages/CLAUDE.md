# frontend/admin/src/pages/

## Purpose
The admin dashboard screens: managing courses and rosters, users and their access, guests, games
and their questions, and past game sessions with their exports.

## Contents
- `LoginPage.tsx` — username/password login (`POST /auth/login`), stores the token, goes to
  `/courses`. No UW NetID button (unlike host and player).
- `CoursesPage.tsx` — list, create and edit (name + semester) courses; links to each roster.
- `RosterPage.tsx` — a course's roster: active and inactive entries, inline edit (netid, name,
  email, active flag via `PATCH`). CSV import is a client-side wizard: a hand-written RFC-4180
  parser (`parseCSV`), auto-detection of Canvas gradebook exports (`SIS Login ID` column, the
  "Points Possible" row, `Last, First` names, `@domain` netids), column mapping, preview, then
  `POST /admin/courses/:id/roster/import` with already-mapped JSON rows.
- `UsersPage.tsx` — list users (role badge); create a local account (username, display name,
  password ≥ 8 chars, optional email).
- `UserDetailPage.tsx` — edit a user (display name, email, password, role), delete them, and grant
  or revoke **course access** (HOST or PLAYER per course) and **game access**.
- `GuestsPage.tsx` — list guest accounts, merge a guest's scores into a netid
  (`POST /admin/users/merge-guest`), delete a guest and their scores.
- `GamesPage.tsx` — list, create and edit games (title, description, max players), import a game
  from JSON (`postForm` → opens the new game's editor), delete a game and all its sessions.
- `QuestionEditorPage.tsx` (~790 lines) — a game's questions: add, edit, delete, reorder (up/down
  arrows → `POST …/questions/reorder` with the full id order), export the game as JSON. The
  `QuestionForm` has per-type editors, and `formToPayload` / `questionToForm` convert between
  form state and the API's `config` / `answer_data`.
- `SessionsPage.tsx` — past sessions filtered by status; per session: score export (plain CSV or
  Canvas-gradebook CSV with assignment title, SIS domain, roster-only and per-question options),
  the HTML report, and delete.

## How it fits in
Routes are declared in `../App.tsx`: everything except `/login` sits inside `RequireAdmin` and the
sidebar `AdminLayout` (Courses, Users, Games, Guests, Sessions); unknown paths go to `/courses`.
Each page loads its own data with `../lib/api` on mount and re-fetches after each change; there is
no shared store or cache. Backend endpoints are in `backend/app/routers/admin.py`.

## Gotchas
- **Adding a question type (T7)** needs a new option in `QuestionForm`, a form-state branch, a
  `build…Payload` function, branches in `formToPayload` and `questionToForm`, a type label, and a
  preview block in the question list, on top of the backend, host and player changes. The
  `answer_data` shape must match what `backend/app/schemas/` validates.
- **`answer_data` key style is inconsistent:** multiple choice, true/false and multi-select use
  `answer_points` (snake_case), but fill-in-the-blank uses `acceptedAnswers`, `answerPoints` and
  `editDistance` (camelCase). Copy the backend's expectation exactly; don't "fix" one side alone.
- **`points_value` is computed in the browser** for accuracy questions (MC / FITB: highest option;
  TF: higher of the two; multi-select: sum of positive options). Only completeness questions use
  the typed-in value. Imported or API-created questions don't go through this.
- **There is no way to delete a course** (no button and no backend endpoint). Rosters can only be
  deactivated entry by entry.
- **Two CSV parsers:** the UI parses rosters itself and posts JSON to `/roster/import`, while
  `POST /courses/:id/roster` (raw CSV upload, used in the README's curl example) parses on the
  backend. They can disagree on the same file.
- Granting several courses or games fires parallel requests (`Promise.all`); if one fails, the
  others may already have been applied.
- Session delete calls `/game/sessions/:id` (the host endpoint), not an `/admin` path.
- Deleting a game also deletes its sessions and scores; deletes use the browser's `confirm()`.
