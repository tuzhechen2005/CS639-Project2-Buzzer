# backend/app/services/

## Purpose
Business logic shared by the REST routers and the Socket.io gateway: auth/JWT, room lifecycle
and access checks, scoring, Redis live state, roster import, and CSV/HTML exports.

## Contents
- `auth_service.py` — bcrypt password hashing; RS256 JWTs (`access` 2 h and carries `role`,
  `refresh` 7 d, `temp` 15 min); base64-encoded PEM keys come from settings, with **ephemeral
  in-memory keys** as the fallback (tokens die on restart). User helpers:
  `get_or_create_user_by_netid`, `create_guest_user` (reuses a GUEST by email, refuses if the
  email belongs to a real account), `authenticate_local`.
- `bootstrap.py` — on startup, creates the first ADMIN from `ADMIN_USERNAME/PASSWORD` if none
  exists, retrying until `alembic upgrade head` has created the schema.
- `game_service.py` — the game domain:
  - `generate_room_code` (6 chars from an unambiguous charset), `create_room` (checks
    `can_use_game`, then `COURSE_MISMATCH` (400) if the course isn't the game's, then the system
    course; enforces `MAX_ROOMS` by scanning Redis, writes the `GameSession` plus Redis room
    state), `get_session_by_code`, `start_game` / `complete_game` / `abandon_game`.
  - Permission rules (§B of docs/plans/t4-ui-restructuring.md): `can_manage_course` (ADMIN or
    course HOST), `can_use_game` (ADMIN, or HOST of the game's course **and** a grant),
    `can_read_session`, each with an `assert_*` twin raising 403. `authorise_player` (players:
    GUEST and ADMIN always pass; otherwise an active roster row by netid, or course access).
  - Integrity rules (409, admins included): `assert_not_system_course` (`SYSTEM_COURSE`),
    `locked_game_ids`/`is_locked` (game has recorded answers → `GAME_LOCKED`),
    `reconcile_session_status`/`is_live` (liveness decided by the Redis room; a LOBBY/IN_PROGRESS
    session with no room key is marked ABANDONED → `GAME_LIVE` only for real rooms),
    `assert_questions_editable`, `check_can_delete_game`.
  - T8 write protocol: `lock_game` (`SELECT … FOR UPDATE` on the games row) and
    `relock_for_write` (lock, re-fetch the user, re-check the permission inside the lock).
  - Grants: `grant_game` (idempotent), `apply_creation_grants` (host → self; admin → every course
    HOST), `assert_can_grant_game` (`NOT_COURSE_HOST`).
  - **Scoring**: `calculate_score(question, answer_data) → ScoreResult` is a thin wrapper over
    `question_types.score_answer`. COMPLETENESS gives full points for any non-empty answer.
    ACCURACY is decided by the type's handler: an index into `answer_points` (MC), a
    `"true"/"false"` key (TF), the best `acceptedAnswers` match within the Levenshtein
    `editDistance` (FITB), or the sum of selected `answer_points` floored at 0 (MS).
  - `record_answer`: scores the answer, inserts a `SessionScore`, updates the Redis score and the
    answered set, and bumps the Redis answer distribution.
  - `get_leaderboard`, `get_player_question_summary` and `get_host_question_summary` build the
    game-over payloads, including the answer reveal and distributions.
- `question_types.py` — the **question-type registry**. One `QuestionType` handler per type
  (`multiple_choice`, `true_false`, `fill_in_the_blank`, `multi_select`) with `label`,
  `validate_definition`, `validate_answer`, `score`, `reveal`, `distribution_keys` and
  `payload_extras`, all pure functions of a question-like object (`type`, `grading_type`,
  `config`, `answer_data`, `points_value`; `QuestionSpec` for raw rows). The module-level
  `score_answer`, `answer_reveal`, `distribution_keys_for`, `validate_definition`,
  `validate_answer`, `payload_extras`, `known_types` and `label_for` add the cross-type rules
  (empty answer = 0 points, COMPLETENESS, unknown type). **To add a question type, write one
  handler and register it in `_TYPES`.** Imports no routers, gateway, database or Redis.
- `state_service.py` — the Redis live-state layer. Key layout is documented in the module
  docstring: `room:{code}` (JSON, 90-min TTL refreshed on activity), and
  `session:{id}:players | player:{uid} | question | answered:{qid} | dist:{qid}`.
  `delete_room_state` removes all of them. `restore_from_mysql` (rebuilds scores and the next
  question after a Redis loss) is defined but has no callers, so nothing recovers a live game
  whose Redis keys are lost.
- `roster_service.py` — `process_roster_csv` parses a Canvas gradebook export (`Student`
  "Last, First" becomes the given name; `SIS Login ID` becomes netid/email; the "Points Possible"
  row is skipped). `process_roster_rows` handles pre-mapped rows. Both feed `_apply_rows`:
  `mode="replace"` upserts and **deactivates every entry not in the upload** (admin aliases),
  `mode="add_only"` deactivates nobody (host endpoints' default); `dry_run` returns the counts
  without writing. Limit: 1000 rows.
- `game_admin_service.py` — game and question CRUD shared by the neutral routers and the admin
  aliases: create/update (course moves: admin only)/duplicate/import/export, `delete_game_rows`
  (MySQL only, images included), questions with the locked/live checks and the image reference
  checks on the merged config, `sanitize_prompt`, `session_items` and
  `finished_course_sessions`. Duplicate copies image rows and remaps references; export writes
  bundle version 1, or 2 when images are referenced; import accepts both and validates
  everything before writing. Imports no routers/websocket code.
- `image_service.py` (T8, docs/plans/t8-image-support.md) — all image logic: limits (2 MiB,
  1600 px, 16 MP, 50 images / 25 MiB per game, 40 MiB bundles, two decode and two bundle
  semaphores), `normalise` (Pillow; PNG/JPEG/WebP only, stores clean files untouched, otherwise
  re-encodes without metadata; pure and run in the threadpool), the aspect and quota rules,
  `etag_matches`, the `config` convention (`validate_image_fields`, tolerant `image_ids`,
  `remap_image_ids`, `export_config` cleanup), and the image rows (`store_upload`,
  `replace_image`, `delete_image`, `used_by`, `assert_references_valid`). Write functions expect
  the caller to hold the game row lock.
- `export_service.py` — `build_session_csv` (Player, Q1..Qn, Total) and `build_canvas_csv`
  (Canvas import format, SIS Login ID = netid[@domain], optional per-question columns, optional
  `roster_only`).
- `report_service.py` — `build_session_report`: a self-contained HTML report with aggregate
  statistics only (no names), bar charts (including multi_select), a word cloud, and a score
  histogram.

## How it fits in
`routers/` and `websocket/gateway.py` call these; services use `models/` and `state_service`, and
never import routers or the gateway (live rooms are ended by the routers, via
`gateway.end_session_from_rest`). **Division of storage:** Redis holds "what is happening now"
(it may expire); MySQL holds the permanent record. Anything that must outlive the room goes
through `record_answer` / the models.

## Gotchas
- **Per-type logic lives in `question_types.py`.** Scoring, reveal, distribution keys, the
  structure rules, answer validation and the payload extras all come from the registry; the
  places that used to repeat them (`record_answer`, both `get_*_question_summary` functions, the
  gateway and `report_service`) call it. What is still per type outside the registry is only
  presentation: the type badge colour and the chart choice in `report_service.py` (bar chart for
  MC, TF and multi_select, word cloud for FITB).
- The FITB distribution key is the same everywhere (lowercase, internal whitespace collapsed),
  because the live counter, the game-over summary and the report all use `distribution_keys_for`.
- The existing handlers assume well-formed `answer_data`: a string `selectedIndex` for MC
  raises `TypeError` in `score`. Only multi_select answers are shape-checked (`validate_answer`,
  called by the gateway).
- `update_player_score` is read-modify-write on a JSON blob (not atomic). It's safe today only
  because each player writes their own key and duplicates are filtered upstream.
- `create_room` and `delete_room_state` use `redis.keys(...)` (O(N) scans). Fine at 50 rooms.
- `abandon_game` only flushes (the caller commits); `start_game` and `complete_game` commit
  immediately on purpose, to avoid races with concurrent answer handlers.
- `build_session_csv` raises `ValueError` rather than `NotFoundError` for a missing session.
  Routers check existence first.
