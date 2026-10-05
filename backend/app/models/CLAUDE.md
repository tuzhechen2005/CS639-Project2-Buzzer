# backend/app/models/

## Purpose
SQLAlchemy 2.0 ORM table definitions (typed `Mapped[...]` style) for the permanent MySQL record.
Schema changes here require an Alembic migration in `../migrations/versions/`.

## Contents
- `__init__.py` — imports every model in FK-dependency order so `Base.metadata` is complete
  (Alembic autogenerate and relationship resolution depend on this). Add new models here.
- `user.py` — `User`: UUID string PK; `role` enum `ADMIN | USER | GUEST`. Identity comes from one
  of `netid` (OAuth2/dev login), `username` + `password_hash` (local accounts), or `email` (guests).
  All four columns are nullable; `netid`, `email`, `username` are unique.
- `course.py` — `Course` (name, semester, `is_system`, `games`); `CourseRoster` (per-course list of students from a
  Canvas CSV: `netid`, `full_name`, `email`, `is_active`, unique on `(course_id, netid)`);
  `UserCourseAccess` (composite PK `user_id + course_id`, `role` enum `HOST | PLAYER`).
- `game.py` — `Game` (`course_id`, title, description, `max_players`); `Question` (polymorphic via `type`
  string + two JSON columns: `config` = what the player sees, `answer_data` = the answer key and
  point table, never sent to clients; `grading_type` enum `ACCURACY | COMPLETENESS`; `order_index`);
  `UserGameAccess` (composite PK `user_id + game_id`, no role).
- `session.py` — `GameSession` (one played instance: UUID PK, 6-char unique `room_code`,
  `game_id`, `course_id`, `host_user_id`, `status` enum `LOBBY | IN_PROGRESS | COMPLETED | ABANDONED`);
  `SessionScore` (one row per player per answered question: `points_awarded` float, `is_correct`,
  `answer_time_ms`, raw player `answer_data` JSON).

## How it fits in
Used by `services/` (all business logic) and directly by `routers/` for simple CRUD. The live
game state lives in Redis (`services/state_service.py`), not here — these tables are what survive
after a room ends. Relationships:

```
User ─┬─ UserCourseAccess(HOST|PLAYER) ─ Course ─┬─ CourseRoster
      │                                          └─ GameSession ─ SessionScore ─ Question
      └─ UserGameAccess ─ Game ─ Question                ▲
                           └──────────────── GameSession ┘
```

## Gotchas
- **Every game belongs to one course** (`Game.course_id`, NOT NULL, migration 004). Using a game
  also needs a per-user `UserGameAccess` grant; `GameSession.course_id` always equals the game's
  course at creation time but is not updated if an admin later moves the game.
- **System course:** `Course.is_system` marks the single migration-created "Unassigned" course that
  holds games no session could place. Identify it only by this flag, never by name; the API
  rejects grants, rosters and rooms on it.
- **Two separate course-membership sources.** A player may join a course's game via an active
  `CourseRoster` row (matched on `netid`) *or* a `UserCourseAccess` row. Hosts are only in
  `UserCourseAccess`. The roster is not linked to `User` by FK — only by `netid` string.
- **Deletes that don't cascade.** `SessionScore.user_id`, `SessionScore.question_id`,
  `GameSession.game_id`/`course_id`/`host_user_id` have no `ondelete`. Routers delete dependent
  rows by hand first (see `delete_user` in `routers/admin.py`, `game_admin_service.delete_game_rows`). A new delete path
  must do the same, and must also clean the Redis side.
- **No uniqueness on `(session_id, user_id, question_id)`** in `SessionScore` — duplicate-answer
  protection is only the Redis "answered" set checked in the gateway.
- `Question` has no per-type columns; a new question type normally needs **no** migration, just a
  new `config`/`answer_data` shape. Images (T8) stored in the DB will need a new table.
- `points_value` / `points_awarded` are floats (migration 003); some callers still annotate or
  cast them as `int`.
