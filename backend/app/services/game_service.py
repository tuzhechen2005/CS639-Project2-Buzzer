from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.exceptions import (
    BuzzerError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from ..models.course import Course, CourseRoster, UserCourseAccess
from ..models.game import Game, Question, UserGameAccess
from ..models.session import GameSession, SessionScore
from ..models.user import User
from ..schemas.game import ScoreResult
from . import state_service as state
from .question_types import (
    QuestionSpec,
    answer_reveal,
    distribution_keys_for,
    score_answer,
)

logger = structlog.get_logger()

# Character set from spec: unambiguous alphanumeric (no 0/O/1/I/L)
_ROOM_CHARSET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
_MAX_CODE_ATTEMPTS = 5


# ---------------------------------------------------------------------------
# Room code generation
# ---------------------------------------------------------------------------


async def generate_room_code(redis: Redis) -> str:
    for _ in range(_MAX_CODE_ATTEMPTS):
        code = "".join(secrets.choice(_ROOM_CHARSET) for _ in range(6))
        if not await redis.exists(f"room:{code}"):
            return code
    raise ConflictError("Could not generate a unique room code — try again")


# ---------------------------------------------------------------------------
# Permission and integrity rules (docs/plans/t4-ui-restructuring.md §B)
#
# can_* are bool predicates; their assert_* twins raise ForbiddenError. Admins pass
# every permission rule. The integrity rules (system course, locked, live) apply to
# admins too and raise 409 with a specific error code.
# ---------------------------------------------------------------------------

_LIVE_STATUSES = ("LOBBY", "IN_PROGRESS")
FINISHED_STATUSES = ("COMPLETED", "ABANDONED")


def integrity_error(code: str, message: str) -> BuzzerError:
    return BuzzerError(code, message, 409)


async def get_course_or_404(db: AsyncSession, course_id: int) -> Course:
    course = await db.get(Course, course_id)
    if not course:
        raise NotFoundError(f"Course {course_id} not found")
    return course


async def get_game_or_404(db: AsyncSession, game_id: int) -> Game:
    game = await db.get(Game, game_id)
    if not game:
        raise NotFoundError(f"Game {game_id} not found")
    return game


async def is_course_host(db: AsyncSession, user_id: str, course_id: int) -> bool:
    result = await db.execute(
        select(UserCourseAccess.user_id).where(
            UserCourseAccess.user_id == user_id,
            UserCourseAccess.course_id == course_id,
            UserCourseAccess.role == "HOST",
        )
    )
    return result.first() is not None


async def has_game_grant(db: AsyncSession, user_id: str, game_id: int) -> bool:
    result = await db.execute(
        select(UserGameAccess.user_id).where(
            UserGameAccess.user_id == user_id, UserGameAccess.game_id == game_id
        )
    )
    return result.first() is not None


async def can_manage_course(db: AsyncSession, user: User, course_id: int) -> bool:
    """ADMIN, or HOST of the course. Says nothing about the system course."""
    if user.role == "ADMIN":
        return True
    return await is_course_host(db, user.id, course_id)


async def assert_can_manage_course(
    db: AsyncSession, user: User, course_id: int
) -> None:
    if not await can_manage_course(db, user, course_id):
        raise ForbiddenError("You do not have HOST access to this course")


async def can_use_game(db: AsyncSession, user: User, game: Game) -> bool:
    """ADMIN, or (HOST of the game's course AND a game grant)."""
    if user.role == "ADMIN":
        return True
    return await is_course_host(db, user.id, game.course_id) and await has_game_grant(
        db, user.id, game.id
    )


async def assert_can_use_game(db: AsyncSession, user: User, game: Game) -> None:
    if not await can_use_game(db, user, game):
        raise ForbiddenError("You do not have access to this game")


async def granted_game_ids(
    db: AsyncSession, user_id: str, game_ids: list[int]
) -> set[int]:
    """The subset of game_ids the user holds a grant for (one query)."""
    if not game_ids:
        return set()
    result = await db.execute(
        select(UserGameAccess.game_id).where(
            UserGameAccess.user_id == user_id, UserGameAccess.game_id.in_(game_ids)
        )
    )
    return set(result.scalars().all())


async def can_read_session(db: AsyncSession, user: User, session: GameSession) -> bool:
    return await can_manage_course(db, user, session.course_id)


async def assert_can_read_session(
    db: AsyncSession, user: User, session: GameSession
) -> None:
    if not await can_read_session(db, user, session):
        raise ForbiddenError("You do not have HOST access to this session's course")


def assert_not_system_course(course: Course) -> None:
    if course.is_system:
        raise integrity_error(
            "SYSTEM_COURSE",
            "The Unassigned course can't be used for this. "
            "Move the game to a real course first.",
        )


async def locked_game_ids(db: AsyncSession, game_ids: list[int]) -> set[int]:
    """Games (of game_ids) with at least one recorded answer, in one grouped query."""
    if not game_ids:
        return set()
    result = await db.execute(
        select(GameSession.game_id)
        .join(SessionScore, SessionScore.session_id == GameSession.id)
        .where(GameSession.game_id.in_(game_ids))
        .group_by(GameSession.game_id)
    )
    return set(result.scalars().all())


async def is_locked(db: AsyncSession, game_id: int) -> bool:
    return game_id in await locked_game_ids(db, [game_id])


async def reconcile_session_status(
    db: AsyncSession, redis: Redis, session: GameSession
) -> bool:
    """
    Return whether a LOBBY/IN_PROGRESS session is really live, deciding by its Redis
    room. A session whose room key is gone is marked ABANDONED (MySQL status goes stale
    when a lobby expires or a restart loses the host-abandon timer). If Redis is
    unreachable the session counts as live and nothing is written.
    """
    if session.status not in _LIVE_STATUSES:
        return False
    try:
        room = await state.get_room_state(redis, session.room_code)
    except (RedisError, OSError) as exc:
        logger.warning(
            "reconcile_redis_unreachable", session_id=session.id, error=str(exc)
        )
        return True
    if room is None or room.get("session_id") not in (None, session.id):
        session.status = "ABANDONED"
        session.completed_at = session.completed_at or datetime.now(timezone.utc)
        await db.flush()
        logger.info("session_reconciled_abandoned", session_id=session.id)
        return False
    return room.get("status") in _LIVE_STATUSES


async def is_live(db: AsyncSession, redis: Redis, game_id: int) -> bool:
    result = await db.execute(
        select(GameSession).where(
            GameSession.game_id == game_id, GameSession.status.in_(_LIVE_STATUSES)
        )
    )
    live = False
    for session in result.scalars().all():
        # Reconcile every session, not just until the first live one, so stale rows
        # are cleaned up in one pass.
        if await reconcile_session_status(db, redis, session):
            live = True
    return live


async def assert_questions_editable(db: AsyncSession, redis: Redis, game: Game) -> None:
    """Locked is checked before live, so is_live (and its ABANDONED write) runs only
    for games without recorded answers."""
    if await is_locked(db, game.id):
        raise integrity_error(
            "GAME_LOCKED",
            "This game has been played, so its questions can't change. "
            "Duplicate it to make an editable copy.",
        )
    if await is_live(db, redis, game.id):
        raise integrity_error(
            "GAME_LIVE", "This game has a room open right now. Try again when it ends."
        )


async def lock_game(db: AsyncSession, game_id: int) -> Game:
    """SELECT ... FOR UPDATE on the games row: the first statement of every write
    transaction that follows the T8 write protocol (docs/plans/t8-image-support.md §D).

    MySQL runs REPEATABLE READ here and a transaction's snapshot is taken by its first
    plain read, so callers end the read phase with `db.rollback()` before calling this;
    a locking read does not create the snapshot, so later plain reads see everything
    committed by earlier lock holders. Lock order everywhere: games row first, then
    game_sessions, images, questions.
    """
    result = await db.execute(
        select(Game)
        .where(Game.id == game_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    game = result.scalar_one_or_none()
    if not game:
        raise NotFoundError(f"Game {game_id} not found")
    return game


async def relock_for_write(
    db: AsyncSession, user_id: str, game_id: int, *, admin_only: bool = False
) -> tuple[User, Game]:
    """Step 4 of the write protocol: lock the game, then re-fetch the user and re-run
    the permission check inside the lock (the role may have changed, or the user been
    deleted, since the read phase). `admin_only` is the rule of the /api/admin aliases."""
    game = await lock_game(db, game_id)
    user = await db.get(User, user_id, populate_existing=True)
    if user is None or user.role == "GUEST":
        raise ForbiddenError("Authenticated account required")
    if admin_only:
        if user.role != "ADMIN":
            raise ForbiddenError("Admin access required")
    else:
        await assert_can_use_game(db, user, game)
    return user, game


async def check_can_delete_game(
    db: AsyncSession, redis: Redis, user: User, game: Game
) -> list[GameSession]:
    """
    Step 1 of the router-orchestrated delete: check permission and the delete rules,
    and return every session the router must end (step 2) before the rows are deleted
    (step 3). Called with the games row already locked (lock_game): is_live may mark
    stale sessions ABANDONED, and those game_sessions writes must come after the games
    lock to keep the lock order (docs/plans/t8-image-support.md §D).
    """
    await assert_can_use_game(db, user, game)
    if user.role != "ADMIN":
        await assert_questions_editable(db, redis, game)
    result = await db.execute(select(GameSession).where(GameSession.game_id == game.id))
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Game grants
# ---------------------------------------------------------------------------


async def grant_game(db: AsyncSession, user_id: str, game_id: int) -> None:
    """Idempotent: an existing (user, game) row is left as is."""
    if not await has_game_grant(db, user_id, game_id):
        db.add(UserGameAccess(user_id=user_id, game_id=game_id))
        await db.flush()


async def grant_game_to_course_hosts(
    db: AsyncSession, game_id: int, course_id: int
) -> None:
    result = await db.execute(
        select(UserCourseAccess.user_id).where(
            UserCourseAccess.course_id == course_id, UserCourseAccess.role == "HOST"
        )
    )
    for user_id in result.scalars().all():
        await grant_game(db, user_id, game_id)


async def apply_creation_grants(db: AsyncSession, actor: User, game: Game) -> None:
    """A host's new game is granted to that host; an admin's to every HOST of its course."""
    if actor.role == "ADMIN":
        await grant_game_to_course_hosts(db, game.id, game.course_id)
    else:
        await grant_game(db, actor.id, game.id)


async def assert_can_grant_game(db: AsyncSession, user_id: str, game: Game) -> None:
    course = await get_course_or_404(db, game.course_id)
    assert_not_system_course(course)
    if not await is_course_host(db, user_id, game.course_id):
        raise integrity_error(
            "NOT_COURSE_HOST",
            "This user isn't a HOST of the game's course. Grant course HOST access first.",
        )


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


async def create_room(
    db: AsyncSession,
    redis: Redis,
    host: User,
    game_id: int,
    course_id: int,
    max_rooms: int = 50,
) -> GameSession:
    # Check order (§B): 404 → 403 → 400 → 409. The course is the game's course.
    game = await get_game_or_404(db, game_id)
    await assert_can_use_game(db, host, game)
    if course_id != game.course_id:
        raise BuzzerError(
            "COURSE_MISMATCH", "This game belongs to a different course", 400
        )
    assert_not_system_course(await get_course_or_404(db, game.course_id))

    # Enforce global room limit — count only LOBBY/IN_PROGRESS rooms.
    # COMPLETED/ABANDONED rooms may linger in Redis briefly for reconnection
    # but do not consume a concurrent-room slot.
    all_room_keys = await redis.keys("room:*")
    room_count = 0
    for key in all_room_keys:
        key_str = key if isinstance(key, str) else key.decode()
        if len(key_str) != 11:  # "room:" (5 chars) + 6-char code
            continue
        room_state_data = await state.get_room_state(redis, key_str[5:])
        if room_state_data and room_state_data.get("status") in (
            "LOBBY",
            "IN_PROGRESS",
        ):
            room_count += 1
    if room_count >= max_rooms:
        raise ConflictError(f"Maximum of {max_rooms} concurrent rooms reached")

    room_code = await generate_room_code(redis)

    session = GameSession(
        id=str(uuid.uuid4()),
        room_code=room_code,
        game_id=game_id,
        course_id=course_id,
        host_user_id=host.id,
        status="LOBBY",
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)

    # Store room state in Redis
    await state.set_room_state(
        redis,
        room_code,
        {
            "session_id": session.id,
            "game_id": game_id,
            "course_id": course_id,
            "host_user_id": host.id,
            "status": "LOBBY",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    logger.info(
        "room_created",
        room_code=room_code,
        session_id=session.id,
        host_id=host.id,
        game_id=game_id,
        course_id=course_id,
    )
    return session


async def get_session_by_code(
    db: AsyncSession, redis: Redis, room_code: str
) -> tuple[GameSession, dict | None]:
    """
    Return (session, redis_state). redis_state is None if Redis has no record
    (session may still be in MySQL as COMPLETED/ABANDONED).
    """
    redis_state = await state.get_room_state(redis, room_code)

    result = await db.execute(
        select(GameSession)
        .where(GameSession.room_code == room_code)
        .options(selectinload(GameSession.game))
    )
    session = result.scalar_one_or_none()
    if not session:
        raise NotFoundError(f"Room '{room_code}' not found or has expired")

    return session, redis_state


async def start_game(
    db: AsyncSession, redis: Redis, session: GameSession
) -> list[Question]:
    """Transition LOBBY → IN_PROGRESS. Returns ordered question list."""
    if session.status != "LOBBY":
        raise ConflictError(f"Cannot start a game in '{session.status}' state")

    result = await db.execute(
        select(Question)
        .where(Question.game_id == session.game_id)
        .order_by(Question.order_index)
    )
    questions = result.scalars().all()
    if not questions:
        raise ConflictError(
            "This game has no questions — add questions before starting"
        )

    session.status = "IN_PROGRESS"
    # Commit immediately so concurrent on_submit_answer handlers in separate DB
    # sessions see IN_PROGRESS rather than the unflushed LOBBY status.
    await db.commit()

    # Update Redis status
    room_state = await state.get_room_state(redis, session.room_code)
    if room_state:
        room_state["status"] = "IN_PROGRESS"
        await state.set_room_state(redis, session.room_code, room_state)

    logger.info("game_started", session_id=session.id, question_count=len(questions))
    return list(questions)


async def complete_game(db: AsyncSession, redis: Redis, session: GameSession) -> None:
    session.status = "COMPLETED"
    session.completed_at = datetime.now(timezone.utc)
    # Commit so player join attempts racing with game_over see COMPLETED.
    await db.commit()
    logger.info("game_completed", session_id=session.id)
    # Keep Redis state 10 more minutes for reconnection, then let it expire naturally


async def abandon_game(db: AsyncSession, redis: Redis, session: GameSession) -> None:
    session.status = "ABANDONED"
    session.completed_at = datetime.now(timezone.utc)
    await db.flush()
    await state.delete_room_state(redis, session.room_code, session.id)
    logger.info("game_abandoned", session_id=session.id)


# ---------------------------------------------------------------------------
# Player authorisation at join time
# ---------------------------------------------------------------------------


async def authorise_player(db: AsyncSession, user: User, session: GameSession) -> str:
    """
    Check whether the player is permitted to join this session.
    Returns the display name to use for the player.
    Raises ForbiddenError / NotFoundError if not authorised.
    """
    if user.role == "GUEST":
        return user.display_name or "Guest"

    if user.role == "ADMIN":
        return user.display_name or user.username or "Admin"

    # OAuth2 user — check course roster
    if user.netid:
        result = await db.execute(
            select(CourseRoster).where(
                CourseRoster.course_id == session.course_id,
                CourseRoster.netid == user.netid,
                CourseRoster.is_active == True,  # noqa: E712
            )
        )
        roster_entry = result.scalar_one_or_none()
        if roster_entry:
            return roster_entry.full_name  # first name from CSV

    # Local account with explicit PLAYER role for this course
    result = await db.execute(
        select(UserCourseAccess).where(
            UserCourseAccess.user_id == user.id,
            UserCourseAccess.course_id == session.course_id,
            UserCourseAccess.role == "PLAYER",
        )
    )
    if result.scalar_one_or_none():
        return user.display_name or user.username or "Player"

    # Local account with HOST role can also join as player
    result = await db.execute(
        select(UserCourseAccess).where(
            UserCourseAccess.user_id == user.id,
            UserCourseAccess.course_id == session.course_id,
            UserCourseAccess.role == "HOST",
        )
    )
    if result.scalar_one_or_none():
        return user.display_name or user.username or "Host"

    raise ForbiddenError("You are not enrolled in the course roster for this game")


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def calculate_score(question: Question, answer_data: dict) -> ScoreResult:
    """
    Calculate points for a player's answer (see question_types.score_answer):
    COMPLETENESS gives full points for any answer, no answer gives 0, and ACCURACY is
    decided by the question type's handler.
    """
    return score_answer(question, answer_data)


async def record_answer(
    db: AsyncSession,
    redis: Redis,
    session_id: str,
    user_id: str,
    question: Question,
    answer_data: dict,
    answer_time_ms: int | None,
) -> ScoreResult:
    """
    Score an answer, write it to MySQL immediately, and update Redis score.
    Returns the score result.
    """
    result = calculate_score(question, answer_data)

    # Persist to MySQL immediately (per-question persistence guarantee)
    score_row = SessionScore(
        session_id=session_id,
        user_id=user_id,
        question_id=question.id,
        points_awarded=result.points_awarded,
        answer_time_ms=answer_time_ms,
        is_correct=result.is_correct,
        answer_data=answer_data or None,
    )
    db.add(score_row)
    await db.flush()

    # Update Redis running score and answered set
    await state.update_player_score(redis, session_id, user_id, result.points_awarded)
    await state.mark_answered(redis, session_id, question.id, user_id)

    # Increment the answer-distribution counters for the results chart
    for key in distribution_keys_for(question, answer_data):
        await state.increment_answer_dist(redis, session_id, question.id, key)

    return result


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------


async def get_leaderboard(db: AsyncSession, session_id: str) -> list[dict]:
    """
    Aggregate session_scores from MySQL to produce a leaderboard.
    Used for QUESTION_RESULTS and GAME_OVER broadcasts.
    """
    from sqlalchemy import func as sqlfunc

    rows = await db.execute(
        select(
            SessionScore.user_id,
            sqlfunc.sum(SessionScore.points_awarded).label("total_score"),
        )
        .where(SessionScore.session_id == session_id)
        .group_by(SessionScore.user_id)
        .order_by(sqlfunc.sum(SessionScore.points_awarded).desc())
    )
    return [{"user_id": r.user_id, "score": float(r.total_score or 0)} for r in rows]


async def get_player_question_summary(
    db: AsyncSession, session_id: str, user_id: str
) -> list[dict]:
    """
    Per-question breakdown for a single player — used in GAME_OVER payload.
    """
    rows = await db.execute(
        select(
            Question.id.label("question_id"),
            Question.prompt,
            Question.points_value,
            Question.type.label("q_type"),
            Question.grading_type,
            Question.config,
            Question.answer_data.label("q_answer_data"),
            SessionScore.points_awarded,
            SessionScore.answer_time_ms,
            SessionScore.answer_data.label("player_answer"),
        )
        .join(GameSession, GameSession.game_id == Question.game_id)
        .outerjoin(
            SessionScore,
            (SessionScore.question_id == Question.id)
            & (SessionScore.session_id == session_id)
            & (SessionScore.user_id == user_id),
        )
        .where(GameSession.id == session_id)
        .order_by(Question.order_index)
    )

    result = []
    for r in rows:
        q_type = r.q_type
        grading_type = r.grading_type
        pts_val = r.points_value
        reveal = answer_reveal(
            QuestionSpec(
                type=q_type,
                grading_type=grading_type,
                config=r.config or {},
                answer_data=r.q_answer_data or {},
                points_value=pts_val,
            )
        )

        result.append(
            {
                "questionId": r.question_id,
                "prompt": r.prompt,
                "type": q_type,
                "gradingType": grading_type,
                "config": r.config or {},
                "pointsAwarded": r.points_awarded or 0,
                "maxPoints": pts_val,
                "answerTimeMs": r.answer_time_ms,
                "playerAnswer": r.player_answer,
                "answerReveal": reveal,
            }
        )

    return result


async def get_host_question_summary(
    db: AsyncSession, session_id: str, total_players: int
) -> list[dict]:
    """Per-question breakdown for the host game-over screen.
    Returns prompt, answer reveal, distribution, and correct/answered counts."""
    from collections import defaultdict

    rows = await db.execute(
        select(
            Question.id.label("question_id"),
            Question.order_index,
            Question.prompt,
            Question.type.label("q_type"),
            Question.grading_type,
            Question.config,
            Question.answer_data.label("q_answer_data"),
            Question.points_value,
            SessionScore.user_id,
            SessionScore.points_awarded,
            SessionScore.answer_data.label("player_answer"),
            SessionScore.answer_time_ms,
            SessionScore.is_correct,
        )
        .join(GameSession, GameSession.game_id == Question.game_id)
        .outerjoin(
            SessionScore,
            (SessionScore.question_id == Question.id)
            & (SessionScore.session_id == session_id),
        )
        .where(GameSession.id == session_id)
        .order_by(Question.order_index)
    )

    questions_meta: dict[int, dict] = {}
    questions_order: list[int] = []
    scores_by_q: dict[int, list[dict]] = defaultdict(list)

    for r in rows:
        qid = r.question_id
        if qid not in questions_meta:
            questions_meta[qid] = {
                "order_index": r.order_index,
                "prompt": r.prompt,
                "type": r.q_type,
                "grading_type": r.grading_type,
                "config": r.config or {},
                "answer_data": r.q_answer_data or {},
                "points_value": r.points_value,
            }
            questions_order.append(qid)
        if r.user_id is not None:
            scores_by_q[qid].append(
                {
                    "player_answer": r.player_answer,
                    "is_correct": bool(r.is_correct),
                    "answer_time_ms": r.answer_time_ms,
                }
            )

    result = []
    for qnum, qid in enumerate(questions_order, start=1):
        q = questions_meta[qid]
        scores = scores_by_q[qid]
        q_type = q["type"]
        pts_val = q["points_value"]
        grading_type = q["grading_type"]
        spec = QuestionSpec(
            type=q_type,
            grading_type=grading_type,
            config=q["config"],
            answer_data=q["answer_data"],
            points_value=pts_val,
        )
        reveal = answer_reveal(spec)

        dist: dict[str, int] = {}
        correct_count = 0
        total_time = 0
        time_count = 0
        for s in scores:
            # Same keys as the live distribution in record_answer.
            for k in distribution_keys_for(spec, s["player_answer"]):
                dist[k] = dist.get(k, 0) + 1
            if s["is_correct"]:
                correct_count += 1
            if s["answer_time_ms"] is not None:
                total_time += s["answer_time_ms"]
                time_count += 1

        result.append(
            {
                "questionId": qid,
                "questionNumber": qnum,
                "prompt": q["prompt"],
                "type": q_type,
                "gradingType": grading_type,
                "config": q["config"],
                "pointsValue": pts_val,
                "answerReveal": reveal,
                "answerDistribution": dist,
                "totalAnswered": len(scores),
                "totalPlayers": total_players,
                "correctCount": correct_count,
                "avgAnswerTimeMs": round(total_time / time_count)
                if time_count
                else None,
            }
        )

    return result
