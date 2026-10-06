# backend/app/schemas/

## Purpose
Pydantic v2 request/response models for the REST API. This is where request **shape and
structural validation** live — including the per-question-type rules for `config`/`answer_data`.

## Contents
- `auth.py` — `LoginRequest` (username+password, or `netid` for the dev-only fallback),
  `TokenResponse`, `TempTokenResponse`, `RefreshResponse`, `GuestJoinRequest`
  (display_name, email, 6-char room_code).
- `admin.py` — models for `routers/admin.py`:
  - Courses: `CourseCreate/Update/Response`.
  - Roster: `RosterEntryResponse`, `RosterUploadResult` (imported/updated/deactivated/errors),
    `RosterEntryPatch`, `RosterRowIn` + `RosterImportPayload` (pre-mapped rows from the admin
    column-mapping wizard).
  - Games: `GameCreate/Update/Response`.
  - Questions: `QuestionCreate` (with a `model_validator` enforcing the per-type structure below),
    `QuestionUpdate`, `QuestionResponse` (includes `answer_data`, so it's for the admin/editor only),
    `QuestionReorder`.
  - Users/access: `UserCreate/Update/Response`, `CourseAccessGrant` (HOST|PLAYER),
    `GameAccessGrant`, `UserWithAccessResponse`, `AdminSessionItem`.
- `image.py` (T8) — `ImageResponse` (metadata only, never the bytes) and `ImageListItem`
  (+ `used_by`: question ids). Image references inside `config` are **not** validated here but in
  `services/image_service.py`, called from the question and import services.
- `game.py` — host/player-facing models for `routers/game.py`: `QuestionPublic` (no
  `answer_data`/`grading_type`), `RoomCreateRequest/Response`, `RoomInfoResponse`,
  `ActiveSessionItem`, `MyCourseItem`, `MyGameItem`; plus internal `ScoreResult`
  (`points_awarded`, `is_correct`) returned by the scoring code.

## Question structure rules (`QuestionCreate.validate_structure`)
| type | `config` | `answer_data` (ACCURACY only) |
|---|---|---|
| `multiple_choice` | `options`: list, ≥2 | `answer_points`: list of non-negative numbers, same length as options |
| `true_false` | — | `answer_points`: dict with exactly keys `"true"`, `"false"` |
| `fill_in_the_blank` | — | `acceptedAnswers`: non-empty strings; `answerPoints`: same length; `editDistance`: int ≥ 0 |
| `multi_select` | `options`: list, ≥2 | `answer_points`: numbers (negatives allowed as penalties), same length as options |
| `numeric_estimate` | optional `unit`: string, 1–20 chars | `target`: finite, \|v\| ≤ 1e15; `mode`: `relative` / `absolute` (relative needs a non-zero target); `bands`: 1–5 `{within > 0, points > 0}`, within increasing, points decreasing; `points_value` = first band's points |
| `plot_point` | `xMin`/`xMax`/`yMin`/`yMax` (min < max, multiples of their step), `xStep`/`yStep` (1, 2 or 5 × 10^k), 1–20 cells per axis; optional `xLabel`/`yLabel` (1–20 chars) and up to 20 `overlays` (point, line, polynomial) | `target` `{x, y}` on a grid point inside the plane; `bands`: 1–5 `{within: int ≥ 0 cells, points > 0}`, within increasing, points decreasing; `points_value` = first band's points |

COMPLETENESS questions skip the `answer_data` checks. The structure rules themselves live in
`services/question_types.py` (`validate_definition`); `QuestionCreate` calls it from its
`model_validator`, and the allowed `type` values come from `known_types()` (a `field_validator`
on `QuestionCreate.type` and `QuestionUpdate.type`), so a new type is registered in one place.

## How it fits in
Routers declare these as parameters/`response_model`. `QuestionCreate` is reused by the game JSON
import (`routers/admin.py::import_game`), so its rules also define what a valid `sample_games/*.json`
question is.

## Gotchas
- **`QuestionUpdate` itself checks only field types**, but updates are not unchecked:
  `game_admin_service.update_question` merges the update into the stored question and re-runs
  `validate_definition` (then the image checks) on the result, so a `PUT` cannot leave a
  question that create would reject (422 `VALIDATION_ERROR`).
- Adding a question type means adding one handler to `services/question_types.py` (see
  `services/CLAUDE.md`); nothing in this directory needs editing for it.
- Key naming is inconsistent by type: `answer_points` (snake) vs `acceptedAnswers`/`answerPoints`/
  `editDistance` (camel). Existing JSON files depend on these exact names.
- Games: `GameCreate` (no `course_id`; the neutral endpoint takes it from the path, and
  `extra="forbid"` makes a body `course_id` a 422), `AdminGameCreate` (+ required `course_id`, admin
  alias), `GameUpdate` (optional `course_id`; only admins may change it), `GameResponse` (+
  `course_id`, `locked`). `CourseResponse` has `is_system`; no request schema accepts it.
  `CourseAccessItem` backs `GET /api/admin/courses/{id}/access`.
- `merge-guest` endpoints take a raw `dict` body, not a schema.
