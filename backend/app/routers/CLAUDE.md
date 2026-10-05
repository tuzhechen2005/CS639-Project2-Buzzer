# backend/app/routers/

## Purpose
FastAPI REST endpoints, all mounted under `/api` by `main.py`. Real-time game traffic does
**not** go through here — see `../websocket/`. The T4 split (docs/plans/t4-ui-restructuring.md):
course-scoped resources live on neutral paths open to course HOSTs; `/api/admin` keeps admin-only
work plus compatibility aliases.

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
- `courses.py` — `/api/courses/{id}/*`, `require_user` + `assert_can_manage_course` (HOST of the
  course, or admin); the system course → 409 `SYSTEM_COURSE`:
  - roster: list, `POST roster` (CSV upload), `POST roster/import` (mapped rows), both with
    `mode=add_only|replace` (default `add_only`) and `dry_run`; `PATCH roster/{entry_id}`.
  - games: `GET games` (only games the caller holds a grant for; admins all), `POST games`
    (course from the path; body has no `course_id`), `POST games/import`.
  - `GET sessions`: COMPLETED/ABANDONED sessions, after reconciling stale ones.
- `games.py` — `/api/games/{id}/*`, `require_user` + `assert_can_use_game` (HOST of the game's
  course **and** a game grant, or admin): get/put/delete, `duplicate`, `export`, and question
  list/create/update/delete/reorder. `delete_game_orchestrated` (also used by the admin alias)
  runs check (service) → `gateway.end_session_from_rest` → delete rows (service).
- `sessions.py` — `/api/sessions/{id}/report|export` (raw or `format=canvas`) for any HOST of the
  session's course; the session must be COMPLETED/ABANDONED after reconciliation, else 409.
- `game.py` — `/api/game/*`, gated by `require_user` plus inline ownership checks:
  - discovery: `my-courses` (HOST courses; admins all; never the system course), `my-games`
    (`can_use_game`; kept for scripts), `my-active-sessions`.
  - rooms: `POST rooms` (`game_service.create_room`: course must equal the game's course),
    `GET rooms/{code}/ping` (public), `GET rooms/{code}`.
  - sessions: `DELETE sessions/{id}` (ends the live room via the gateway, then deletes),
    `GET sessions/{id}/guests`, `POST sessions/{id}/merge-guest`, `GET sessions/{id}/export`
    (legacy raw CSV, no status check). All restricted to the session's host or an admin.
- `admin.py` — `/api/admin/*`, **every** endpoint gated by `require_admin`:
  - admin-only: courses list/create/get/update (list includes the system course), `GET
    courses/{id}/access` (per-course grants), users, guests, guest merge, course-access and
    game-access grants (game grant → 409 `NOT_COURSE_HOST` unless the user hosts the game's
    course; idempotent), the all-sessions list.
  - aliases with the old behaviour, sharing `services/game_admin_service.py`: games and
    questions (create needs `course_id` in the body; `games/import` needs `?course_id=`), roster
    (always `replace`, no `mode`/`dry_run`), sessions `export`/`report` (no status check).

## How it fits in
Permission checks live in the routers (they differ between neutral and admin paths); the
integrity rules (system course, locked, live) live in `services/game_admin_service.py` and
`services/game_service.py`, so every path gets them. Check order everywhere: 404 → 403 → 400 →
409. Routers may import `websocket/gateway.py` (for `end_session_from_rest`); services never do.
The `get_db` dependency **commits automatically** when the request finishes without an error.

## Gotchas
- **Ownership of child ids:** a roster entry or question that doesn't belong to the course/game
  in the path is a 404 — the permission check only covers the path parent.
- `update_question` applies `QuestionUpdate` field by field with **no structural re-validation**
  (see `schemas/CLAUDE.md`) — T7 should fix this.
- Prompt HTML is sanitized in `game_admin_service.sanitize_prompt` (b, i, br, u); any new write
  path must call it.
- `delete_user` still removes scores by hand and never touches Redis.
- Two different guest-merge implementations. The admin one normalizes the netid and promotes the
  guest if no real user exists. The host one (`game.py`) doesn't normalize whitespace, returns 404
  if no user exists, and re-attributes **all** of the guest's scores, not just that session's.
- Game export/import pin `version: 1`. T8 may bump it, but version-1 imports must keep working.
- Game creation auto-grants: a host's game to that host, an admin's (or a moved game) to every
  HOST of the course. A user made HOST later gets no grants on existing games.
