# backend/app/

## Purpose
The Buzzer backend: a single ASGI process serving the REST API (FastAPI, `/api/*`) and the
real-time game channel (python-socketio, `/socket.io/*`), backed by MySQL (the permanent record)
and Redis (live room state).

## Contents
Top-level files:
- `main.py` — builds the FastAPI app (CORS, slowapi, exception handlers, routers under `/api`).
  Its lifespan connects Redis and bootstraps the first admin. Exports
  `asgi_app = socketio.ASGIApp(sio, other_asgi_app=app)`, which is what uvicorn serves.
- `config.py` — `Settings` (pydantic-settings, read from `.env`): DB/Redis URLs, JWT keys, CORS,
  `MAX_ROOMS`, admin bootstrap credentials, `STRESS_TEST_KEY`; `is_development` switches several
  behaviors (listed under Gotchas).
- `database.py` — async SQLAlchemy engine (asyncmy), `AsyncSessionLocal`, `Base`, and the
  `get_db` dependency, which **commits on success and rolls back on error**.
- `redis_client.py` — a lazily created global async Redis client (`decode_responses=True`).

Subdirectories (each has its own `CLAUDE.md`):
- `routers/` — REST endpoints: `auth` (login, guest, OAuth2 callback, refresh), `game`
  (host/player: my-courses/games, rooms, session export and guest merge), `admin`
  (everything admin-only: courses, roster, games, questions, users, access grants, session
  export/report), `health`.
- `websocket/` — Socket.io protocol (`events.py`), JWT socket auth, and `gateway.py`: join/rejoin,
  the host-driven phase machine (lobby → question → results → … → game over), answer submission,
  timers, lock/unlock, host-disconnect grace.
- `services/` — business logic: JWT/auth, room lifecycle and access checks, **scoring**, the
  Redis state layer, roster CSV import, CSV and HTML exports.
- `models/` — ORM tables: `User`, `Course`/`CourseRoster`/`UserCourseAccess`,
  `Game`/`Question`/`UserGameAccess`, `GameSession`/`SessionScore`.
- `schemas/` — Pydantic request/response models, including the per-question-type structure rules.
- `common/` — auth dependencies (`get_current_user`, `require_admin`, `require_user`), error
  types and handlers, rate limiter, logging.
- `migrations/` — Alembic (`001_initial_schema`, `002_add_answer_data_to_scores`,
  `003_float_points`). Every model change needs a new revision.

## How it fits in
```
host / player / admin SPAs ──REST──▶ routers/ ──┐
host / player SPAs ──Socket.io──▶ websocket/ ───┼─▶ services/ ─┬─▶ models/ ─▶ MySQL (permanent)
                                                │              └─▶ state_service ─▶ Redis (live, TTL)
                                  common/ (auth deps, errors) ◀─┘   schemas/ validate REST I/O
```
Authorization happens at two levels. **Role** gates are in `common/dependencies.py`:
ADMIN / USER / GUEST. **Per-resource** checks are in `services/game_service.py`:
course HOST access, game access, player roster/enrollment. On top of those, routers and the
gateway check "is this the session's host". The server is the referee: `Question.answer_data`
never leaves the backend except through admin-only question endpoints; clients get
`config` plus a derived "answer reveal" after the question closes.

A typical round: host `host_advance` → gateway loads the question and sets Redis state → broadcasts
`new_question` (sans answer) → player `submit_answer` → `game_service.record_answer` (score, insert
`SessionScore`, update Redis score/answered/distribution) → host `host_advance` →
`question_results` (host gets the distribution; each player gets only their own points and rank) → … →
`game_over`.

## Gotchas
Cross-cutting ones. Each subdirectory's `CLAUDE.md` has the details.
- **T4 boundary:** roster, game/question authoring, the HTML report and Canvas export live only
  under `require_admin`. There is no `require_host`: host is a per-course `UserCourseAccess`
  role, so moving these to hosts needs per-course checks. Games have no `course_id`; access is
  per-user via `UserGameAccess`.
- **Adding a question type (T7)** touches `schemas/` (regex + validator, **on update too**),
  `services/game_service.py` (score, distribution, reveal ×2), `services/report_service.py`,
  and `websocket/gateway.py` (reveal, payload, answer validation). The reveal logic is
  copy-pasted in 4 places.
- **Single-process assumption:** the gateway keeps sid context and timers in process memory, so
  the app can't scale past one worker even with the Redis socket.io manager.
- **Deletes are two-datastore problems:** MySQL FKs mostly don't cascade (routers delete
  dependents by hand), and only session delete cleans Redis.
- **Dev vs prod differ:** in-memory vs Redis socket.io manager, rate limits off in dev,
  `netid`-only login allowed in dev, SQL echo on in dev. Test the nginx build
  (`localhost:8080`) at least once.
- If JWT keys are unset, `auth_service` generates ephemeral keys, and all tokens die on every
  restart (and every `--reload`).
