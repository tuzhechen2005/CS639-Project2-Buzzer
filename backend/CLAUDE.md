# backend/

## Purpose
The Python 3.12 backend service (FastAPI + python-socketio), packaged as the `backend` Docker
Compose service.

## Contents
- `app/` — all application code; see `app/CLAUDE.md` for the architecture.
- `app/migrations/` + `alembic.ini` — Alembic migrations (`script_location = app/migrations`;
  the DB URL comes from app settings, not the ini).
- `scripts/generate_keys.py` — generates the RS256 key pair and prints base64 values for
  `JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY` in `.env`.
- `requirements.txt` — runtime deps plus test and load tools (pytest, httpx, locust). Note
  `bcrypt<4.0` is pinned on purpose (passlib incompatibility).
- `Dockerfile` — python:3.12-slim with build deps for asyncmy. Compose mounts the source and runs
  `uvicorn app.main:asgi_app --reload` on :8000.

## How it fits in
nginx (:8080) proxies `/api/` and `/socket.io/` to this service and serves the three built
frontends statically. It depends on the `mysql` and `redis` Compose services. Tests live
outside this directory: `tests/unit`, and `tests/integration` against the live stack. So do the
helper scripts (`scripts/seed_demo.py`, `simulate_players.py`, `smoke_test_websocket.py`).

## Gotchas
- CI runs `ruff check` + `ruff format --check` on `backend/` and `scripts/` for every MR. Run
  `ruff format backend/ scripts/` before pushing.
- Serve `app.main:asgi_app`, not `app.main:app`. The latter has no Socket.io.
- Run with a single worker (see `app/websocket/CLAUDE.md`, per-process state).
- On a fresh database, startup blocks until `alembic upgrade head` has run.
