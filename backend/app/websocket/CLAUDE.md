# backend/app/websocket/

## Purpose
The Socket.io real-time game loop: connection auth, joining and rejoining rooms, the host-driven
phase state machine, answer submission, question timers, and host-disconnect handling.
`docs/realtime.md` walks through one answer end to end. Read it before changing anything here.

## Contents
- `events.py` — every event name as a constant. It is the whole protocol vocabulary; add new
  events here.
  - Client → server: `join_room`, `rejoin_room`, `submit_answer`, and host-only `host_advance`,
    `host_lock_question`.
  - Server → client: room broadcasts (`new_question`, `game_over`, `player_joined/left`,
    `question_locked/unlocked`, `host_disconnected`, `game_abandoned`), targeted replies
    (`answer_received`, `sync_state`, `error`), and host-only events (`answer_status`,
    `answer_phase_ended`). `question_results` is sent separately to the host room and to each
    player's own room.
- `middleware.py` — `authenticate_socket(auth, db)`: validates `auth.token` (access **or** temp
  JWT) and returns the `User`, raising `ValueError` on failure.
- `gateway.py` (~1300 lines) — the `socketio.AsyncServer` (`sio`) and all handlers:
  - `connect`: per-IP rate limit in production (Redis `ws_rate:{ip}`), then JWT auth; stores
    `user_id` in the socket session.
  - `on_join_room`:
    - HOST path: must be the session's `host_user_id` or an ADMIN. Cancels any pending abandon
      task, auto-unlocks if the question was locked because the host disconnected, and emits the
      full `sync_state`.
    - PLAYER path: `authorise_player`, adds the player to Redis, notifies the host, emits
      `sync_state`, and late-joins an open question with the remaining time (minimum 5 s).
  - `on_rejoin_room`: like join, but the role is inferred from the session.
  - `on_host_advance` (state machine on `room_state.question_phase`):
    - `None` (lobby) → `start_game` + first `new_question`.
    - `QUESTION` → `question_results`: the host gets the distribution and reveal; each player
      gets their own points and rank.
    - `RESULTS` → the next `new_question`, or `game_over` with summaries for the host and each
      player.
  - `on_submit_answer`: checks the phase, the lock, the question id and duplicates (Redis
    answered set), plus `question_types.accept_answer` (the type's `validate_answer`, then its
    `normalize_answer`, for every grading type; the normalized answer is what is scored and
    stored); calls `game_service.record_answer`; emits
    `answer_received` to the player and `answer_status` to the host, and `answer_phase_ended` +
    timer cancel when everyone has answered.
  - `on_lock_question`: toggles the lock and pauses or resumes the timer by shifting a "virtual"
    `started_at`.
  - `disconnect`: the host auto-locks the question and starts a 5-min `_host_abandon_task`; a
    player is marked disconnected and the host is notified.
  - `end_session_from_rest(session_id, room_code)`: called **only by routers** (game/session
    deletes) — emits `game_abandoned` (unless the room is COMPLETED), cancels the session's
    timers, makes its sids leave the room and host room and drops them from `_sid_ctx`, deletes
    its Redis state. No DB access; safe when the room is already gone.
  - Helpers: `_question_payload` (client-safe, **never** includes `answer_data`; adds
    `payload_extras` such as `editDistance` for FITB), `_host_room(code)` = `"{code}:host"`,
    `_user_room(uid)` = `"user:{uid}"`.

## How it fits in
`main.py` wraps FastAPI with `socketio.ASGIApp(sio, other_asgi_app=app)`, so `/socket.io/*` is
handled here. Handlers open their own DB sessions (`_db()`: commit on success, rollback on error)
and use `services/state_service` for Redis and `services/game_service` for scoring and
persistence. Pick the audience for every emit: the room code (everyone), `_host_room` (host
only), `_user_room` / `sid` (one player).

## Gotchas
- **Per-process state:** `_sid_ctx` (sid → user/role/room), `_timer_tasks`, `_abandon_tasks`.
  The production `AsyncRedisManager` fans emits out across instances, but these dicts don't
  cross processes. In practice the app must run as a single worker; with more, timers and
  host-only handlers break.
- **Duplicate-answer race:** `has_answered` is checked before `record_answer`, and the answered
  set is updated only after the DB insert, with no DB unique constraint. Two concurrent submits
  from one player can both be scored.
- **Only multi_select answers are shape-validated.** `question_types.validate_answer` is called
  here; the other existing types accept anything, so a malformed MC `selectedIndex` still
  reaches `calculate_score` and raises inside a handler that has no try/except. A new question
  type gets its answer validation by implementing `validate_answer` in its handler.
- Any ADMIN is treated as host on `join_room` (role HOST) and **always** on `rejoin_room`, so an
  admin can't rejoin a room as a player.
- Disconnected players stay in the players set, so "all answered" waits for them (the timer still
  ends the question).
- `sync_state.currentQuestion` differs by role: hosts get a full `_question_payload` +
  `startedAt`; players get the compact Redis record (ids and timing only) and rely on
  `new_question` for content.
- The answer reveal is built by `services/question_types.answer_reveal`, the single copy used by
  the gateway, both game-over summaries and the report.
- `max_possible_score` in `game_over` is cast to `int`, which truncates fractional point values.
