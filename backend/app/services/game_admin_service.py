"""
Game and question management shared by the neutral routers (/api/courses, /api/games,
/api/sessions) and the /api/admin aliases.

Permission checks stay in the routers, because they differ between the two (course HOST
+ game grant vs. require_admin). The integrity rules — system course, locked, live — are
enforced here, so every write path gets them. Like every service, this module never
imports routers/ or websocket/; ending live rooms is orchestrated by the routers
(docs/plans/t4-ui-restructuring.md §B).
"""

from __future__ import annotations

import json

import bleach
import structlog
from pydantic import ValidationError
from redis.asyncio import Redis
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.exceptions import BuzzerError, ForbiddenError, NotFoundError
from ..models.course import Course
from ..models.game import Game, Question
from ..models.session import GameSession, SessionScore
from ..models.user import User
from ..schemas.admin import (
    GameCreate,
    GameResponse,
    GameUpdate,
    QuestionCreate,
    QuestionUpdate,
)
from . import game_service
from .question_types import validate_definition
from .game_service import (
    FINISHED_STATUSES,
    apply_creation_grants,
    assert_not_system_course,
    assert_questions_editable,
    get_course_or_404,
    grant_game_to_course_hosts,
    integrity_error,
    locked_game_ids,
)

logger = structlog.get_logger()

SUPPORTED_IMPORT_VERSION = 1
_PROMPT_TAGS = ["b", "i", "br", "u"]


def sanitize_prompt(prompt: str) -> str:
    """Every question write path must go through this (clients render prompts as HTML)."""
    return bleach.clean(prompt, tags=_PROMPT_TAGS, attributes={}, strip=True)


# ---------------------------------------------------------------------------
# Games
# ---------------------------------------------------------------------------


def game_response(game: Game, locked: bool) -> GameResponse:
    return GameResponse(
        id=game.id,
        course_id=game.course_id,
        title=game.title,
        description=game.description,
        max_players=game.max_players,
        created_at=game.created_at,
        locked=locked,
    )


async def game_responses(db: AsyncSession, games: list[Game]) -> list[GameResponse]:
    locked = await locked_game_ids(db, [g.id for g in games])
    return [game_response(g, g.id in locked) for g in games]


async def game_response_for(db: AsyncSession, game: Game) -> GameResponse:
    return (await game_responses(db, [game]))[0]


async def list_games(db: AsyncSession, course_id: int | None = None) -> list[Game]:
    query = select(Game).order_by(Game.title)
    if course_id is not None:
        query = query.where(Game.course_id == course_id)
    return list((await db.execute(query)).scalars().all())


async def create_game(
    db: AsyncSession, actor: User, course: Course, data: GameCreate
) -> Game:
    assert_not_system_course(course)
    game = Game(
        course_id=course.id,
        title=data.title,
        description=data.description,
        max_players=data.max_players,
    )
    db.add(game)
    await db.flush()
    await apply_creation_grants(db, actor, game)
    await db.refresh(game)
    logger.info("game_created", game_id=game.id, course_id=course.id, by=actor.id)
    return game


async def update_game(
    db: AsyncSession, redis: Redis, actor: User, game: Game, data: GameUpdate
) -> Game:
    if data.course_id is not None and data.course_id != game.course_id:
        if actor.role != "ADMIN":
            raise ForbiddenError("Only admins can move a game to another course")
        target = await get_course_or_404(db, data.course_id)
        assert_not_system_course(target)
        if await game_service.is_live(db, redis, game.id):
            raise integrity_error(
                "GAME_LIVE",
                "This game has a room open right now. Try again when it ends.",
            )
        # Past sessions keep their original course_id.
        game.course_id = target.id
        await db.flush()
        await grant_game_to_course_hosts(db, game.id, target.id)
        logger.info("game_moved", game_id=game.id, course_id=target.id, by=actor.id)
    if data.title is not None:
        game.title = data.title
    if data.description is not None:
        game.description = data.description
    if data.max_players is not None:
        game.max_players = data.max_players
    await db.flush()
    await db.refresh(game)
    return game


async def delete_game_rows(db: AsyncSession, game: Game) -> None:
    """Step 3 of the router-orchestrated delete: MySQL only (scores, sessions, game).
    Questions and game grants go with the game via ORM cascade."""
    session_ids = select(GameSession.id).where(GameSession.game_id == game.id)
    await db.execute(
        delete(SessionScore).where(SessionScore.session_id.in_(session_ids))
    )
    await db.execute(delete(GameSession).where(GameSession.game_id == game.id))
    await db.delete(game)
    await db.flush()
    logger.info("game_deleted", game_id=game.id)


async def duplicate_game(db: AsyncSession, actor: User, game: Game) -> Game:
    assert_not_system_course(await get_course_or_404(db, game.course_id))
    copy = Game(
        course_id=game.course_id,
        title=f"{game.title} (copy)"[:255],
        description=game.description,
        max_players=game.max_players,
    )
    db.add(copy)
    await db.flush()
    for q in await list_questions(db, game.id):
        db.add(
            Question(
                game_id=copy.id,
                type=q.type,
                grading_type=q.grading_type,
                prompt=q.prompt,  # already sanitized on write
                config=q.config,
                answer_data=q.answer_data,
                time_limit_seconds=q.time_limit_seconds,
                points_value=q.points_value,
                order_index=q.order_index,
            )
        )
    await db.flush()
    await apply_creation_grants(db, actor, copy)
    await db.refresh(copy)
    logger.info("game_duplicated", source_id=game.id, game_id=copy.id, by=actor.id)
    return copy


def export_bundle(game: Game, questions: list[Question]) -> tuple[str, bytes]:
    bundle = {
        "format": "buzzer/game",
        "version": SUPPORTED_IMPORT_VERSION,
        "game": {
            "title": game.title,
            "description": game.description,
            "max_players": game.max_players,
        },
        "questions": [
            {
                "type": q.type,
                "grading_type": q.grading_type,
                "prompt": q.prompt,
                "config": q.config,
                "answer_data": q.answer_data,
                "time_limit_seconds": q.time_limit_seconds,
                "points_value": q.points_value,
            }
            for q in questions
        ],
    }
    safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in game.title)
    content = json.dumps(bundle, indent=2, ensure_ascii=False).encode()
    return f"{safe_title}.json", content


def _invalid_import(message: str) -> BuzzerError:
    return BuzzerError("INVALID_IMPORT", message, 400)


def _short(exc: ValidationError) -> str:
    return "; ".join(e["msg"] for e in exc.errors())


async def import_game(
    db: AsyncSession, actor: User, course: Course, raw: bytes
) -> Game:
    """Create a new game in `course` from a buzzer/game bundle. The file never names a
    course."""
    assert_not_system_course(course)
    try:
        bundle = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise _invalid_import(f"Invalid JSON: {exc}") from exc
    if not isinstance(bundle, dict) or bundle.get("format") != "buzzer/game":
        raise _invalid_import("Unrecognised file format")
    version = bundle.get("version")
    if version != SUPPORTED_IMPORT_VERSION:
        raise _invalid_import(
            f"Unsupported version {version!r}; "
            f"server supports version {SUPPORTED_IMPORT_VERSION}"
        )
    try:
        meta = GameCreate(**bundle.get("game", {}))
    except (ValidationError, TypeError) as exc:
        detail = _short(exc) if isinstance(exc, ValidationError) else str(exc)
        raise _invalid_import(f"Invalid game metadata: {detail}") from exc
    questions: list[QuestionCreate] = []
    for i, q in enumerate(bundle.get("questions", []), start=1):
        try:
            questions.append(QuestionCreate(**q))
        except (ValidationError, TypeError) as exc:
            detail = _short(exc) if isinstance(exc, ValidationError) else str(exc)
            raise _invalid_import(f"Question {i} invalid: {detail}") from exc

    game = Game(
        course_id=course.id,
        title=meta.title,
        description=meta.description,
        max_players=meta.max_players,
    )
    db.add(game)
    await db.flush()
    for idx, q in enumerate(questions):
        db.add(_question_from(game.id, q, idx))
    await db.flush()
    await apply_creation_grants(db, actor, game)
    await db.refresh(game)
    logger.info(
        "game_imported", game_id=game.id, course_id=course.id, questions=len(questions)
    )
    return game


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


def _question_from(game_id: int, body: QuestionCreate, order_index: int) -> Question:
    return Question(
        game_id=game_id,
        type=body.type,
        grading_type=body.grading_type,
        prompt=sanitize_prompt(body.prompt),
        config=body.config,
        answer_data=body.answer_data,
        time_limit_seconds=body.time_limit_seconds,
        points_value=body.points_value,
        order_index=order_index,
    )


async def list_questions(db: AsyncSession, game_id: int) -> list[Question]:
    result = await db.execute(
        select(Question)
        .where(Question.game_id == game_id)
        .order_by(Question.order_index)
    )
    return list(result.scalars().all())


async def get_question_or_404(
    db: AsyncSession, game_id: int, question_id: int
) -> Question:
    """A question that doesn't belong to the game in the path is a 404 (ownership)."""
    result = await db.execute(
        select(Question).where(Question.id == question_id, Question.game_id == game_id)
    )
    question = result.scalar_one_or_none()
    if not question:
        raise NotFoundError(f"Question {question_id} not found in game {game_id}")
    return question


async def create_question(
    db: AsyncSession, redis: Redis, game: Game, body: QuestionCreate
) -> Question:
    await assert_questions_editable(db, redis, game)
    if body.order_index is None:
        max_idx = (
            await db.execute(
                select(func.max(Question.order_index)).where(
                    Question.game_id == game.id
                )
            )
        ).scalar_one_or_none()
        order_index = (max_idx + 1) if max_idx is not None else 0
    else:
        order_index = body.order_index
    question = _question_from(game.id, body, order_index)
    db.add(question)
    await db.flush()
    await db.refresh(question)
    return question


async def update_question(
    db: AsyncSession, redis: Redis, game: Game, question: Question, body: QuestionUpdate
) -> Question:
    await assert_questions_editable(db, redis, game)
    if body.type is not None:
        question.type = body.type
    if body.grading_type is not None:
        question.grading_type = body.grading_type
    if body.prompt is not None:
        question.prompt = sanitize_prompt(body.prompt)
    if body.config is not None:
        question.config = body.config
    if body.answer_data is not None:
        question.answer_data = body.answer_data
    if body.time_limit_seconds is not None:
        question.time_limit_seconds = body.time_limit_seconds
    if body.points_value is not None:
        question.points_value = body.points_value
    if body.order_index is not None:
        question.order_index = body.order_index
    # Update must enforce the same structure as create: validate the merged result, so a
    # partial update (say, only `type`) cannot leave a config that does not match it.
    try:
        validate_definition(question)
    except ValueError as exc:
        raise BuzzerError("VALIDATION_ERROR", str(exc), 422) from exc
    await db.flush()
    await db.refresh(question)
    return question


async def delete_question(
    db: AsyncSession, redis: Redis, game: Game, question: Question
) -> None:
    await assert_questions_editable(db, redis, game)
    await db.delete(question)
    await db.flush()


async def reorder_questions(
    db: AsyncSession, redis: Redis, game: Game, order: list[int]
) -> None:
    await assert_questions_editable(db, redis, game)
    questions = {q.id: q for q in await list_questions(db, game.id)}
    if len(order) != len(questions) or set(order) != set(questions):
        raise integrity_error(
            "QUESTIONS_CHANGED", "Questions changed, reload and try again"
        )
    for idx, qid in enumerate(order):
        questions[qid].order_index = idx
    await db.flush()


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


async def session_items(db: AsyncSession, sessions: list[GameSession]) -> list[dict]:
    """AdminSessionItem rows, shared by the admin list and the course Past Sessions."""
    rows = []
    for s in sessions:
        game = await db.get(Game, s.game_id)
        course = await db.get(Course, s.course_id)
        host = await db.get(User, s.host_user_id) if s.host_user_id else None
        player_count = (
            await db.execute(
                select(func.count(SessionScore.user_id.distinct())).where(
                    SessionScore.session_id == s.id
                )
            )
        ).scalar_one() or 0
        rows.append(
            {
                "session_id": s.id,
                "room_code": s.room_code,
                "status": s.status,
                "game_id": s.game_id,
                "game_title": game.title if game else "Unknown",
                "course_id": s.course_id,
                "course_name": course.name if course else "Unknown",
                "course_semester": course.semester if course else "",
                "host_display_name": (host.display_name or host.username or host.netid)
                if host
                else None,
                "created_at": s.created_at,
                "completed_at": s.completed_at,
                "player_count": player_count,
            }
        )
    return rows


async def finished_course_sessions(
    db: AsyncSession, redis: Redis, course_id: int
) -> list[GameSession]:
    """COMPLETED/ABANDONED sessions of a course, newest first, after reconciling stale
    LOBBY/IN_PROGRESS rows so a session cut off by a restart shows up as ABANDONED."""
    stale = await db.execute(
        select(GameSession).where(
            GameSession.course_id == course_id,
            GameSession.status.in_(("LOBBY", "IN_PROGRESS")),
        )
    )
    for session in stale.scalars().all():
        await game_service.reconcile_session_status(db, redis, session)
    result = await db.execute(
        select(GameSession)
        .where(
            GameSession.course_id == course_id,
            GameSession.status.in_(FINISHED_STATUSES),
        )
        .order_by(GameSession.created_at.desc())
    )
    return list(result.scalars().all())
