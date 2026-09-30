# backend/app/routers/

## Purpose
FastAPI REST endpoints, all mounted under `/api` by `main.py`. Real-time game traffic does
**not** go through here — see `../websocket/`.

## Contents
- `health.py` — `GET /api/health`: pings MySQL and Redis, counts active `room:*` keys and players.
- `auth.py` — `/api/auth/*`:
  - `login`: username+password gives an access token (2 h) plus an httpOnly refresh cookie (7 d,
    path `/api/auth`). In development only, `{netid}` gives a temp token.
  - `oauth2-callback`: trusts the `X-Auth-Request-User/Email` headers from the upstream OAuth2
    proxy and returns an HTML redirect carrying a temp token in the URL fragment.
  - `exchange-temp`: temp token → access token + refresh cookie.
  - `guest`: creates or reuses a GUEST user by email, but only while the room exists in Redis.
  - `refresh`, `logout`.
- `game.py` — `/api/game/*`, host/player-facing, gated by `require_user` (non-guest) plus inline
  ownership checks:
  - discovery: `my-courses` (courses where the user is HOST; admins see all), `my-games`
    (via `UserGameAccess`; admins see all), `my-active-sessions`.
  - rooms: `POST rooms` (delegates to `game_service.create_room`), `GET rooms/{code}/ping`
    (public), `GET rooms/{code}`.
  - sessions: `DELETE sessions/{id}`, `GET sessions/{id}/guests`,
    `POST sessions/{id}/merge-guest`, `GET sessions/{id}/export` (raw CSV). All are restricted
    to the session's host or an admin.
- `admin.py` — `/api/admin/*`, **every** endpoint gated by `require_admin`:
  - courses: list/create/get/update (no delete).
  - roster: list, `POST roster` (Canvas CSV upload), `POST roster/import` (pre-mapped rows),
    `PATCH roster/{id}`.
  - games: CRUD, `GET games/{id}/export` and `POST games/import` (`buzzer/game` JSON, version 1).
  - questions: list/create/update/delete, `POST reorder` (must list every question id).
  - users: list/create/get/update/delete, `users/guests`, course-access and game-access
    grant/revoke, `users/merge-guest`.
  - sessions: list all, `export` (Canvas or raw CSV), `report` (standalone HTML).

## How it fits in
Routers are thin for CRUD (they query models directly) and delegate anything non-trivial to
`services/`: room creation and access checks, roster parsing, CSV/HTML export. The `get_db`
dependency **commits automatically** when the request finishes without an error, so many update
handlers just mutate ORM objects and return.

## Gotchas
- **T4 is mostly about this file boundary.** Roster management, game/question authoring,
  the session HTML report and Canvas export exist only in `admin.py` behind `require_admin`.
  Hosts currently get only the raw CSV export (`game.py`), and only for sessions they
  personally hosted, not for other sessions in their course.
- `update_question` applies `QuestionUpdate` field by field with **no structural re-validation**
  (see `schemas/CLAUDE.md`).
- Prompt HTML is sanitized with `bleach` (allowed tags: b, i, br, u) on create/update/import. The
  report and clients render the prompt as HTML, so every new write path must sanitize too.
- **Deletion paths clean only MySQL.** `delete_game` and `delete_user` remove dependent sessions
  and scores by hand but never touch Redis, so a live room for that game or user leaves stale
  keys behind. Only `DELETE /game/sessions/{id}` calls `state.delete_room_state`. It also doesn't
  cancel the gateway's in-process timer for a running room.
- Two different guest-merge implementations. The admin one normalizes the netid and promotes the
  guest if no real user exists. The host one (`game.py`) doesn't normalize whitespace, returns 404
  if no user exists, and re-attributes **all** of the guest's scores, not just that session's.
- `export_game` / `import_game` pin `version: 1`. T8 may bump it, but version-1 imports must keep
  working.
- Admin `create_game` / `import_game` grant nobody access. A USER host can't see the game until an
  admin grants `UserGameAccess`.
