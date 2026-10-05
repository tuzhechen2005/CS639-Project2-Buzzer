"""
A single game and its questions, for anyone who passes can_use_game (course HOST with a
game grant, or an admin). Check order: 404 → 403 → 400 → 409 (docs/plans/t4-ui-restructuring.md §B).
"""

from __future__ import annotations

import io
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.dependencies import require_user
from ..database import get_db
from ..models.game import Game, Question
from ..models.user import User
from ..redis_client import get_redis
from ..schemas.admin import (
    GameResponse,
    GameUpdate,
    QuestionCreate,
    QuestionReorder,
    QuestionResponse,
    QuestionUpdate,
)
from ..services import game_admin_service as games
from ..services.game_service import (
    assert_can_use_game,
    check_can_delete_game,
    get_game_or_404,
)
from ..websocket.gateway import end_session_from_rest

router = APIRouter(prefix="/games", tags=["games"])


async def _usable_game(db: AsyncSession, user: User, game_id: int) -> Game:
    game = await get_game_or_404(db, game_id)
    await assert_can_use_game(db, user, game)
    return game


async def delete_game_orchestrated(
    db: AsyncSession, redis, user: User, game: Game
) -> None:
    """Check (service) → end live state (gateway) → delete rows (service). Shared with
    the admin alias. Services never import the gateway, so the router does step 2."""
    sessions = await check_can_delete_game(db, redis, user, game)
    for session in sessions:
        await end_session_from_rest(session.id, session.room_code)
    await games.delete_game_rows(db, game)


@router.get("/{game_id}", response_model=GameResponse)
async def get_game(
    game_id: int,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GameResponse:
    game = await _usable_game(db, user, game_id)
    return await games.game_response_for(db, game)


@router.put("/{game_id}", response_model=GameResponse)
async def update_game(
    game_id: int,
    body: GameUpdate,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_redis),
) -> GameResponse:
    game = await _usable_game(db, user, game_id)
    game = await games.update_game(db, redis, user, game, body)
    return await games.game_response_for(db, game)


@router.delete("/{game_id}", status_code=204)
async def delete_game(
    game_id: int,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_redis),
) -> None:
    game = await get_game_or_404(db, game_id)
    await delete_game_orchestrated(db, redis, user, game)


@router.post("/{game_id}/duplicate", response_model=GameResponse, status_code=201)
async def duplicate_game(
    game_id: int,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GameResponse:
    game = await _usable_game(db, user, game_id)
    copy = await games.duplicate_game(db, user, game)
    return games.game_response(copy, locked=False)


@router.get("/{game_id}/export")
async def export_game(
    game_id: int,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    game = await _usable_game(db, user, game_id)
    filename, content = games.export_bundle(
        game, await games.list_questions(db, game.id)
    )
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


@router.get("/{game_id}/questions", response_model=list[QuestionResponse])
async def list_questions(
    game_id: int,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Question]:
    game = await _usable_game(db, user, game_id)
    return await games.list_questions(db, game.id)


@router.post("/{game_id}/questions", response_model=QuestionResponse, status_code=201)
async def create_question(
    game_id: int,
    body: QuestionCreate,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_redis),
) -> Question:
    game = await _usable_game(db, user, game_id)
    return await games.create_question(db, redis, game, body)


@router.put("/{game_id}/questions/{question_id}", response_model=QuestionResponse)
async def update_question(
    game_id: int,
    question_id: int,
    body: QuestionUpdate,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_redis),
) -> Question:
    game = await _usable_game(db, user, game_id)
    question = await games.get_question_or_404(db, game.id, question_id)
    return await games.update_question(db, redis, game, question, body)


@router.delete("/{game_id}/questions/{question_id}", status_code=204)
async def delete_question(
    game_id: int,
    question_id: int,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_redis),
) -> None:
    game = await _usable_game(db, user, game_id)
    question = await games.get_question_or_404(db, game.id, question_id)
    await games.delete_question(db, redis, game, question)


@router.post("/{game_id}/questions/reorder", status_code=204)
async def reorder_questions(
    game_id: int,
    body: QuestionReorder,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_redis),
) -> None:
    game = await _usable_game(db, user, game_id)
    await games.reorder_questions(db, redis, game, body.order)
