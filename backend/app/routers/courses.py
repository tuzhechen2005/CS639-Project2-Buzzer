"""
Course-scoped resources for course HOSTs (and admins): roster, games, past sessions.

Every handler follows the check order of docs/plans/t4-ui-restructuring.md §B:
404 (missing) → 403 (permission) → 400 → 409 (integrity).
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.dependencies import require_user
from ..common.exceptions import NotFoundError
from ..database import get_db
from ..models.course import CourseRoster
from ..models.user import User
from ..redis_client import get_redis
from ..schemas.admin import (
    AdminSessionItem,
    GameCreate,
    GameResponse,
    RosterEntryPatch,
    RosterEntryResponse,
    RosterImportPayload,
    RosterUploadResult,
)
from ..services import game_admin_service as games
from ..services.game_service import (
    assert_can_manage_course,
    assert_not_system_course,
    get_course_or_404,
    granted_game_ids,
)
from ..services.roster_service import process_roster_csv, process_roster_rows

router = APIRouter(prefix="/courses", tags=["courses"])

RosterModeQuery = Annotated[
    Literal["add_only", "replace"],
    Query(
        description="add_only (default) never deactivates; replace deactivates entries missing from the upload"
    ),
]
DryRunQuery = Annotated[bool, Query(description="Return the counts without saving")]


async def _managed_course(
    db: AsyncSession, user: User, course_id: int, *, system_ok: bool
):
    course = await get_course_or_404(db, course_id)
    await assert_can_manage_course(db, user, course_id)
    if not system_ok:
        assert_not_system_course(course)
    return course


# ---------------------------------------------------------------------------
# Roster
# ---------------------------------------------------------------------------


@router.get("/{course_id}/roster", response_model=list[RosterEntryResponse])
async def list_roster(
    course_id: int,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[CourseRoster]:
    await _managed_course(db, user, course_id, system_ok=False)
    result = await db.execute(
        select(CourseRoster)
        .where(CourseRoster.course_id == course_id)
        .order_by(CourseRoster.full_name)
    )
    return list(result.scalars().all())


@router.post("/{course_id}/roster", response_model=RosterUploadResult)
async def upload_roster(
    course_id: int,
    file: Annotated[UploadFile, File(description="Canvas gradebook CSV export")],
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    mode: RosterModeQuery = "add_only",
    dry_run: DryRunQuery = False,
) -> RosterUploadResult:
    await _managed_course(db, user, course_id, system_ok=False)
    return await process_roster_csv(
        db, course_id, await file.read(), mode=mode, dry_run=dry_run
    )


@router.post("/{course_id}/roster/import", response_model=RosterUploadResult)
async def import_roster_rows(
    course_id: int,
    payload: RosterImportPayload,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    mode: RosterModeQuery = "add_only",
    dry_run: DryRunQuery = False,
) -> RosterUploadResult:
    await _managed_course(db, user, course_id, system_ok=False)
    rows = [r.model_dump() for r in payload.rows]
    return await process_roster_rows(db, course_id, rows, mode=mode, dry_run=dry_run)


@router.patch("/{course_id}/roster/{entry_id}", response_model=RosterEntryResponse)
async def patch_roster_entry(
    course_id: int,
    entry_id: int,
    body: RosterEntryPatch,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CourseRoster:
    await _managed_course(db, user, course_id, system_ok=False)
    # Ownership: an entry of another course is a 404, not an edit of that course.
    result = await db.execute(
        select(CourseRoster).where(
            CourseRoster.id == entry_id, CourseRoster.course_id == course_id
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise NotFoundError(f"Roster entry {entry_id} not found in course {course_id}")
    if body.is_active is not None:
        entry.is_active = body.is_active
    if body.netid is not None:
        entry.netid = body.netid.strip().lower()
    if body.full_name is not None:
        entry.full_name = body.full_name.strip()
    if body.email is not None:
        entry.email = str(body.email).lower()
    await db.flush()
    await db.refresh(entry)
    return entry


# ---------------------------------------------------------------------------
# Games
# ---------------------------------------------------------------------------


@router.get("/{course_id}/games", response_model=list[GameResponse])
async def list_course_games(
    course_id: int,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[GameResponse]:
    """Games of the course the caller can use: admins see all, hosts only granted ones."""
    await _managed_course(db, user, course_id, system_ok=True)
    course_games = await games.list_games(db, course_id)
    if user.role != "ADMIN":
        allowed = await granted_game_ids(db, user.id, [g.id for g in course_games])
        course_games = [g for g in course_games if g.id in allowed]
    return await games.game_responses(db, course_games)


@router.post("/{course_id}/games", response_model=GameResponse, status_code=201)
async def create_course_game(
    course_id: int,
    body: GameCreate,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GameResponse:
    course = await _managed_course(db, user, course_id, system_ok=False)
    game = await games.create_game(db, user, course, body)
    return games.game_response(game, locked=False)


@router.post("/{course_id}/games/import", response_model=GameResponse, status_code=201)
async def import_course_game(
    course_id: int,
    file: Annotated[UploadFile, File(description="buzzer/game JSON bundle")],
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GameResponse:
    course = await _managed_course(db, user, course_id, system_ok=False)
    game = await games.import_game(db, user, course, await file.read())
    return games.game_response(game, locked=False)


# ---------------------------------------------------------------------------
# Past sessions
# ---------------------------------------------------------------------------


@router.get("/{course_id}/sessions", response_model=list[AdminSessionItem])
async def list_course_sessions(
    course_id: int,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_redis),
) -> list[dict]:
    """COMPLETED and ABANDONED sessions of the course, newest first."""
    await _managed_course(db, user, course_id, system_ok=False)
    sessions = await games.finished_course_sessions(db, redis, course_id)
    return await games.session_items(db, sessions)
