# backend/app/common/

## Purpose
Cross-cutting FastAPI plumbing: authentication/authorization dependencies, the app's error types
and handlers, rate limiting, and structured logging setup.

## Contents
- `dependencies.py` — FastAPI dependencies used by every router:
  - `get_current_user`: reads the JWT from `Authorization: Bearer` (or an `access_token` cookie),
    accepts token types `access` **and** `temp`, and loads the `User` from MySQL.
  - `require_admin`: `role == "ADMIN"`, else 403.
  - `require_user`: rejects `GUEST` (ADMIN and USER pass).
  - `get_refresh_token`: reads the httpOnly `refresh_token` cookie.
- `exceptions.py` — `BuzzerError(code, message, status_code)` and subclasses `NotFoundError`
  (404), `ForbiddenError` (403), `UnauthorizedError` (401), `ConflictError` (409).
  `register_exception_handlers` turns them into `{"error": CODE, "message": ...}`, turns validation
  errors into 422 `{"error": "VALIDATION_ERROR", "detail": [...]}`, and turns anything else into
  a generic 500.
- `rate_limit.py` — the slowapi `limiter`. In development every request gets a random key, so
  limits never fire. In production the key is the client IP, unless the request carries a
  matching `X-Stress-Key` header.
- `logging.py` — structlog configuration: console renderer in dev, JSON in prod; uvicorn access
  logs are muted in prod unless stress-test mode is on.

## How it fits in
`main.py` calls `configure_logging()` and `register_exception_handlers()` and attaches `limiter`.
Routers use `Depends(require_admin)` / `Depends(require_user)` / `Depends(get_current_user)` for
**role** gating. Finer, per-resource checks (does this user host *this* course? run *this* game?
own *this* session?) are **not** here. They live in `services/game_service.py`
(`assert_host_can_use_course`, `assert_host_can_use_game`) and inline in `routers/game.py`
(`session.host_user_id == user.id`).

## Gotchas
- There is **no `require_host` dependency.** "Host" is not a user role; it is a
  `UserCourseAccess.role` scoped to one course. Any T4 endpoint moved from admin to host needs a
  per-course check (e.g. a dependency that takes `course_id`), not a role check.
  `require_user` alone would let every non-guest account in.
- `get_current_user` accepts **temp** tokens (15-min, issued by OAuth2/dev login) as if they were
  access tokens. The socket middleware does the same.
- Error bodies are inconsistent: `BuzzerError` → `{error, message}`, `HTTPException` (used in
  `import_game`) → `{detail}`, validation → `{error, detail}`. The frontends read `detail`
  (see `frontend/*/src/lib/api.ts`), so `BuzzerError` messages show up as `HTTP <status>` there.
- Rate limits are effectively off in development — don't write tests that expect 429 locally.
