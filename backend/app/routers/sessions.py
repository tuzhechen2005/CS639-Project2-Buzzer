"""
Downloads for a finished session, for any HOST of its course (or an admin):
the HTML summary and the score CSV (raw or Canvas format).
"""

from __future__ import annotations

import io
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.dependencies import require_user
from ..common.exceptions import NotFoundError
from ..database import get_db
from ..models.session import GameSession
from ..models.user import User
from ..redis_client import get_redis
from ..services.export_service import build_canvas_csv, build_session_csv
from ..services.game_service import (
    FINISHED_STATUSES,
    assert_can_read_session,
    integrity_error,
    reconcile_session_status,
)
from ..services.report_service import build_session_report

router = APIRouter(prefix="/sessions", tags=["sessions"])


async def _readable_finished_session(
    db: AsyncSession, redis, user: User, session_id: str
) -> GameSession:
    session = await db.get(GameSession, session_id)
    if not session:
        raise NotFoundError(f"Session {session_id} not found")
    await assert_can_read_session(db, user, session)
    # A session cut off by a restart is still IN_PROGRESS in MySQL; reconciling first
    # makes it downloadable as ABANDONED instead of a 409.
    await reconcile_session_status(db, redis, session)
    if session.status not in FINISHED_STATUSES:
        raise integrity_error(
            "SESSION_NOT_FINISHED", "This session hasn't finished yet."
        )
    return session


@router.get("/{session_id}/report")
async def session_report(
    session_id: str,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_redis),
) -> Response:
    """Standalone HTML summary (aggregate stats, no player names)."""
    await _readable_finished_session(db, redis, user, session_id)
    filename, content = await build_session_report(db, session_id)
    return Response(
        content=content,
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{session_id}/export")
async def export_session(
    session_id: str,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_redis),
    format: Literal["raw", "canvas"] = Query("raw"),
    title: str | None = Query(None, description="Assignment column title (Canvas)"),
    sis_domain: str = Query("", description="Domain appended to netid (Canvas)"),
    roster_only: bool = Query(
        True, description="Skip players without a netid (Canvas)"
    ),
    per_question: bool = Query(False, description="One column per question (Canvas)"),
) -> StreamingResponse:
    await _readable_finished_session(db, redis, user, session_id)
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
