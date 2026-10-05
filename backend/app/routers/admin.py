from __future__ import annotations

import io
import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.dependencies import require_admin
from ..common.exceptions import ConflictError, NotFoundError
from ..database import get_db
from ..models.course import Course, CourseRoster, UserCourseAccess
from ..models.game import Question, UserGameAccess
from ..models.session import GameSession, SessionScore
from ..models.user import User
from ..schemas.admin import (
    AdminGameCreate,
    AdminSessionItem,
    CourseAccessGrant,
    CourseAccessItem,
    CourseCreate,
    CourseResponse,
    CourseUpdate,
    GameAccessGrant,
    GameCreate,
    GameResponse,
    GameUpdate,
    QuestionCreate,
    QuestionReorder,
    QuestionResponse,
    QuestionUpdate,
    RosterEntryPatch,
    RosterEntryResponse,
    RosterImportPayload,
    RosterUploadResult,
    UserCreate,
    UserResponse,
    UserUpdate,
    UserWithAccessResponse,
)
from ..redis_client import get_redis
from ..services import game_admin_service as games
from ..services.auth_service import hash_password
from ..services.export_service import build_canvas_csv, build_session_csv
from ..services.report_service import build_session_report
from ..services.game_service import (
    assert_can_grant_game,
    assert_not_system_course,
    get_course_or_404,
    get_game_or_404,
    grant_game,
)
from ..services.roster_service import process_roster_csv, process_roster_rows
from .games import delete_game_orchestrated

router = APIRouter(prefix="/admin", tags=["admin"])
logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------


@router.get("/courses", response_model=list[CourseResponse])
async def list_courses(
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Course]:
    result = await db.execute(
        select(Course).order_by(Course.semester.desc(), Course.name)
    )
    return result.scalars().all()


@router.post("/courses", response_model=CourseResponse, status_code=201)
async def create_course(
    body: CourseCreate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Course:
    course = Course(name=body.name, semester=body.semester)
    db.add(course)
    await db.flush()
    await db.refresh(course)
    await db.commit()
    logger.info("course_created", course_id=course.id, name=body.name)
    return course


@router.get("/courses/{course_id}", response_model=CourseResponse)
async def get_course(
    course_id: int,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Course:
    course = await db.get(Course, course_id)
    if not course:
        raise NotFoundError(f"Course {course_id} not found")
    return course


@router.put("/courses/{course_id}", response_model=CourseResponse)
async def update_course(
    course_id: int,
    body: CourseUpdate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Course:
    course = await get_course_or_404(db, course_id)
    assert_not_system_course(course)
    if body.name is not None:
        course.name = body.name
    if body.semester is not None:
        course.semester = body.semester
    return course


@router.get("/courses/{course_id}/access", response_model=list[CourseAccessItem])
async def list_course_access(
    course_id: int,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict]:
    """One row per UserCourseAccess grant of the course (HOST and PLAYER)."""
    await get_course_or_404(db, course_id)
    result = await db.execute(
        select(UserCourseAccess, User)
        .join(User, User.id == UserCourseAccess.user_id)
        .where(UserCourseAccess.course_id == course_id)
        .order_by(UserCourseAccess.role, User.display_name, User.username)
    )
    return [
        {
            "user_id": u.id,
            "display_name": u.display_name,
            "netid": u.netid,
            "username": u.username,
            "role": uca.role,
        }
        for uca, u in result.all()
    ]


# ---------------------------------------------------------------------------
# Roster — aliases kept for compatibility: replace mode, no mode/dry_run options
# ---------------------------------------------------------------------------


@router.get("/courses/{course_id}/roster", response_model=list[RosterEntryResponse])
async def list_roster(
    course_id: int,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[CourseRoster]:
    assert_not_system_course(await get_course_or_404(db, course_id))
    result = await db.execute(
        select(CourseRoster)
        .where(CourseRoster.course_id == course_id)
        .order_by(CourseRoster.full_name)
    )
    return result.scalars().all()


@router.post("/courses/{course_id}/roster", response_model=RosterUploadResult)
async def upload_roster(
    course_id: int,
    file: Annotated[UploadFile, File(description="Canvas gradebook CSV export")],
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RosterUploadResult:
    assert_not_system_course(await get_course_or_404(db, course_id))
    content = await file.read()
    return await process_roster_csv(db, course_id, content)


@router.post("/courses/{course_id}/roster/import", response_model=RosterUploadResult)
async def import_roster_rows(
    course_id: int,
    payload: RosterImportPayload,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RosterUploadResult:
    assert_not_system_course(await get_course_or_404(db, course_id))
    rows = [
        {"netid": r.netid, "full_name": r.full_name, "email": r.email}
        for r in payload.rows
    ]
    result = await process_roster_rows(db, course_id, rows)
    await db.commit()
    return result


@router.patch(
    "/courses/{course_id}/roster/{roster_id}", response_model=RosterEntryResponse
)
async def patch_roster_entry(
    course_id: int,
    roster_id: int,
    body: RosterEntryPatch,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CourseRoster:
    assert_not_system_course(await get_course_or_404(db, course_id))
    result = await db.execute(
        select(CourseRoster).where(
            CourseRoster.id == roster_id,
            CourseRoster.course_id == course_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise NotFoundError(f"Roster entry {roster_id} not found in course {course_id}")
    if body.is_active is not None:
        entry.is_active = body.is_active
    if body.netid is not None:
        entry.netid = body.netid.strip().lower()
    if body.full_name is not None:
        entry.full_name = body.full_name.strip()
    if body.email is not None:
        entry.email = str(body.email).lower()
    return entry


# ---------------------------------------------------------------------------
# Games — aliases of /api/courses/{id}/games and /api/games/* for admins
# (docs/plans/t4-ui-restructuring.md §D). Same service functions, so the locked, live
# and system-course rules apply here too.
# ---------------------------------------------------------------------------


@router.get("/games", response_model=list[GameResponse])
async def list_games(
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[GameResponse]:
    """Every game, including those in the system course, each with course_id/locked."""
    return await games.game_responses(db, await games.list_games(db))


@router.post("/games", response_model=GameResponse, status_code=201)
async def create_game(
    body: AdminGameCreate,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GameResponse:
    course = await get_course_or_404(db, body.course_id)
    data = GameCreate(**body.model_dump(exclude={"course_id"}))
    game = await games.create_game(db, admin, course, data)
    await db.commit()
    return games.game_response(game, locked=False)


@router.get("/games/{game_id}", response_model=GameResponse)
async def get_game(
    game_id: int,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GameResponse:
    return await games.game_response_for(db, await get_game_or_404(db, game_id))


@router.put("/games/{game_id}", response_model=GameResponse)
async def update_game(
    game_id: int,
    body: GameUpdate,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_redis),
) -> GameResponse:
    game = await get_game_or_404(db, game_id)
    game = await games.update_game(db, redis, admin, game, body)
    return await games.game_response_for(db, game)


@router.delete("/games/{game_id}", status_code=204)
async def delete_game(
    game_id: int,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_redis),
) -> None:
    """Admins may delete any game; live sessions are ended first (§B)."""
    game = await get_game_or_404(db, game_id)
    await delete_game_orchestrated(db, redis, admin, game)


@router.get("/games/{game_id}/questions", response_model=list[QuestionResponse])
async def list_questions(
    game_id: int,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Question]:
    game = await get_game_or_404(db, game_id)
    return await games.list_questions(db, game.id)


@router.post(
    "/games/{game_id}/questions", response_model=QuestionResponse, status_code=201
)
async def create_question(
    game_id: int,
    body: QuestionCreate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_redis),
) -> Question:
    game = await get_game_or_404(db, game_id)
    question = await games.create_question(db, redis, game, body)
    await db.commit()
    return question


@router.put("/games/{game_id}/questions/{question_id}", response_model=QuestionResponse)
async def update_question(
    game_id: int,
    question_id: int,
    body: QuestionUpdate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_redis),
) -> Question:
    game = await get_game_or_404(db, game_id)
    question = await games.get_question_or_404(db, game.id, question_id)
    return await games.update_question(db, redis, game, question, body)


@router.delete("/games/{game_id}/questions/{question_id}", status_code=204)
async def delete_question(
    game_id: int,
    question_id: int,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_redis),
) -> None:
    game = await get_game_or_404(db, game_id)
    question = await games.get_question_or_404(db, game.id, question_id)
    await games.delete_question(db, redis, game, question)


@router.post("/games/{game_id}/questions/reorder", status_code=204)
async def reorder_questions(
    game_id: int,
    body: QuestionReorder,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_redis),
) -> None:
    game = await get_game_or_404(db, game_id)
    await games.reorder_questions(db, redis, game, body.order)


@router.get("/games/{game_id}/export")
async def export_game(
    game_id: int,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    game = await get_game_or_404(db, game_id)
    filename, content = games.export_bundle(
        game, await games.list_questions(db, game.id)
    )
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/games/import", status_code=201)
async def import_game(
    file: Annotated[UploadFile, File(description="buzzer/game JSON bundle")],
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    course_id: int = Query(..., gt=0, description="Course the new game belongs to"),
) -> dict:
    course = await get_course_or_404(db, course_id)
    game = await games.import_game(db, admin, course, await file.read())
    await db.commit()
    return {"game_id": game.id}


# ---------------------------------------------------------------------------
# Users (local accounts)
# ---------------------------------------------------------------------------


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[User]:
    result = await db.execute(
        select(User).where(User.role != "GUEST").order_by(User.role, User.username)
    )
    return result.scalars().all()


@router.post("/users", response_model=UserResponse, status_code=201)
async def create_user(
    body: UserCreate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    # Enforce unique username
    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none():
        raise ConflictError(f"Username '{body.username}' is already taken")

    user = User(
        id=str(uuid.uuid4()),
        username=body.username,
        display_name=body.display_name,
        email=str(body.email) if body.email else None,
        password_hash=hash_password(body.password),
        role="USER",
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    await db.commit()
    logger.info("local_user_created", user_id=user.id, username=body.username)
    return user


@router.get("/users/guests", response_model=list[UserResponse])
async def list_guests(
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[User]:
    result = await db.execute(
        select(User).where(User.role == "GUEST").order_by(User.created_at.desc())
    )
    return result.scalars().all()


@router.get("/users/{user_id}", response_model=UserWithAccessResponse)
async def get_user(
    user_id: str,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError(f"User {user_id} not found")

    ca_result = await db.execute(
        select(UserCourseAccess).where(UserCourseAccess.user_id == user_id)
    )
    ga_result = await db.execute(
        select(UserGameAccess).where(UserGameAccess.user_id == user_id)
    )

    course_access = [
        {"course_id": ca.course_id, "role": ca.role} for ca in ca_result.scalars().all()
    ]
    game_access = [ga.game_id for ga in ga_result.scalars().all()]

    return {
        **{
            c: getattr(user, c)
            for c in [
                "id",
                "username",
                "netid",
                "display_name",
                "email",
                "role",
                "created_at",
                "last_login",
            ]
        },
        "course_access": course_access,
        "game_access": game_access,
    }


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    body: UserUpdate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError(f"User {user_id} not found")
    if body.username is not None:
        existing = await db.execute(
            select(User).where(User.username == body.username, User.id != user_id)
        )
        if existing.scalar_one_or_none():
            raise ConflictError(f"Username '{body.username}' is already taken")
        user.username = body.username
    if body.display_name is not None:
        user.display_name = body.display_name
    if body.email is not None:
        user.email = str(body.email)
    if body.password is not None:
        user.password_hash = hash_password(body.password)
    if body.role is not None:
        user.role = body.role
    return user


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError(f"User {user_id} not found")
    if user.role == "ADMIN":
        raise ConflictError("Cannot delete an admin account")
    # Delete scores first — the session_scores.user_id column is NOT NULL so
    # SQLAlchemy's default SET-NULL cascade would fail without this.
    from sqlalchemy import delete as sa_delete

    await db.execute(sa_delete(SessionScore).where(SessionScore.user_id == user_id))
    await db.delete(user)


# ---------------------------------------------------------------------------
# Access management
# ---------------------------------------------------------------------------


@router.post("/users/{user_id}/course-access", status_code=204)
async def grant_course_access(
    user_id: str,
    body: CourseAccessGrant,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError(f"User {user_id} not found")
    course = await get_course_or_404(db, body.course_id)
    assert_not_system_course(course)

    result = await db.execute(
        select(UserCourseAccess).where(
            UserCourseAccess.user_id == user_id,
            UserCourseAccess.course_id == body.course_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.role = body.role  # update role if access already exists
    else:
        db.add(
            UserCourseAccess(user_id=user_id, course_id=body.course_id, role=body.role)
        )


@router.delete("/users/{user_id}/course-access/{course_id}", status_code=204)
async def revoke_course_access(
    user_id: str,
    course_id: int,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    result = await db.execute(
        select(UserCourseAccess).where(
            UserCourseAccess.user_id == user_id,
            UserCourseAccess.course_id == course_id,
        )
    )
    access = result.scalar_one_or_none()
    if not access:
        raise NotFoundError(
            f"No course access record for user {user_id} / course {course_id}"
        )
    await db.delete(access)


@router.post("/users/{user_id}/game-access", status_code=204)
async def grant_game_access(
    user_id: str,
    body: GameAccessGrant,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError(f"User {user_id} not found")
    game = await get_game_or_404(db, body.game_id)
    # 409 unless the user is a HOST of the game's course (and it isn't the system
    # course). Re-granting an existing row is a no-op.
    await assert_can_grant_game(db, user_id, game)
    await grant_game(db, user_id, game.id)


@router.delete("/users/{user_id}/game-access/{game_id}", status_code=204)
async def revoke_game_access(
    user_id: str,
    game_id: int,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    result = await db.execute(
        select(UserGameAccess).where(
            UserGameAccess.user_id == user_id,
            UserGameAccess.game_id == game_id,
        )
    )
    access = result.scalar_one_or_none()
    if not access:
        raise NotFoundError(
            f"No game access record for user {user_id} / game {game_id}"
        )
    await db.delete(access)


# ---------------------------------------------------------------------------
# Guest merge
# ---------------------------------------------------------------------------


@router.post("/users/merge-guest", status_code=204)
async def merge_guest(
    body: dict,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    guest_user_id: str = body.get("guest_user_id", "")
    target_netid: str = body.get("target_netid", "")

    if not guest_user_id or not target_netid:
        raise ConflictError("guest_user_id and target_netid are required")

    guest = await db.get(User, guest_user_id)
    if not guest or guest.role != "GUEST":
        raise NotFoundError(f"Guest user {guest_user_id} not found")

    normalized_netid = target_netid.strip().lower()

    # Find the real user by netid
    result = await db.execute(select(User).where(User.netid == normalized_netid))
    real_user = result.scalar_one_or_none()

    if real_user:
        # Real user already has an account — re-attribute scores and delete the guest record
        scores_result = await db.execute(
            select(SessionScore).where(SessionScore.user_id == guest_user_id)
        )
        for score in scores_result.scalars().all():
            score.user_id = real_user.id
        await db.delete(guest)
        logger.info("guest_merged", guest_id=guest_user_id, real_user_id=real_user.id)
    else:
        # No account yet for this netid (student hasn't logged in via OAuth2) —
        # promote the guest record in-place so scores are retained without re-attribution
        guest.netid = normalized_netid
        guest.role = "USER"
        logger.info("guest_promoted", guest_id=guest_user_id, netid=normalized_netid)


# ---------------------------------------------------------------------------
# Sessions (admin view)
# ---------------------------------------------------------------------------


@router.get("/sessions", response_model=list[AdminSessionItem])
async def list_sessions(
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status: str | None = Query(
        None, description="Filter by status (LOBBY, IN_PROGRESS, COMPLETED, ABANDONED)"
    ),
) -> list[dict]:
    """List all game sessions across all hosts, newest first."""
    query = select(GameSession).order_by(GameSession.created_at.desc())
    if status:
        query = query.where(GameSession.status == status)
    result = await db.execute(query)
    return await games.session_items(db, list(result.scalars().all()))


@router.get("/sessions/{session_id}/export")
async def export_session(
    session_id: str,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    format: str = Query("canvas", description="'canvas' or 'raw'"),
    title: str | None = Query(
        None, description="Assignment column title (Canvas format)"
    ),
    sis_domain: str = Query(
        "", description="Domain appended to netid for SIS Login ID (e.g. wisc.edu)"
    ),
    roster_only: bool = Query(
        True, description="Exclude players without a netid (guests, local accounts)"
    ),
    per_question: bool = Query(
        False, description="One column per question instead of total"
    ),
) -> StreamingResponse:
    """Download session scores as CSV. Supports Canvas gradebook import format."""
    session = await db.get(GameSession, session_id)
    if not session:
        raise NotFoundError(f"Session {session_id} not found")

    if format == "canvas":
        filename, content = await build_canvas_csv(
            db,
            session_id,
            assignment_title=title,
            sis_domain=sis_domain,
            roster_only=roster_only,
            per_question=per_question,
        )
    else:
        filename, content = await build_session_csv(db, session_id)

    return StreamingResponse(
        io.BytesIO(content),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/sessions/{session_id}/report")
async def session_report(
    session_id: str,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Download a standalone HTML report for a session (aggregate stats, no PII)."""
    session = await db.get(GameSession, session_id)
    if not session:
        raise NotFoundError(f"Session {session_id} not found")
    filename, content = await build_session_report(db, session_id)
    return Response(
        content=content,
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
