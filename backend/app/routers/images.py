"""
Images of a game (docs/plans/t8-image-support.md §D).

Management under /api/games/{game_id}/images uses the T4 game permissions
(require_user + can_use_game) and the question integrity rules. Check order:
404 game → 403 → 404 image → 413/415/400 file → 409. Every write follows the write
protocol: read phase → db.rollback() → process the file with no connection held →
lock_game first in a new transaction → re-check → write → explicit commit.

Reading, GET /api/images/{image_id}, needs no login: the random id is the capability
(plain <img> tags, players and guests). It uses its own short database session.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.dependencies import require_user
from ..common.exceptions import NotFoundError
from ..database import AsyncSessionLocal, get_db
from ..models.game import Image
from ..models.user import User
from ..redis_client import get_redis
from ..schemas.image import ImageListItem, ImageResponse
from ..services import image_service as images
from ..services.game_service import (
    assert_can_use_game,
    assert_questions_editable,
    get_game_or_404,
    relock_for_write,
)
from .games import end_read_phase

router = APIRouter(tags=["images"])

_UploadFile = Annotated[
    UploadFile, File(description="PNG, JPEG or WebP, at most 2 MiB")
]


async def _process(file: UploadFile) -> images.NormalisedImage:
    """Step 3 of the write protocol: all file errors, before any lock is taken."""
    data = await images.read_upload(file, images.MAX_UPLOAD_BYTES)
    if data is None:
        raise images.image_too_large()
    return await images.normalise_async(data)


def _response(image: Image) -> ImageResponse:
    return ImageResponse.model_validate(image)


@router.get("/games/{game_id}/images", response_model=list[ImageListItem])
async def list_images(
    game_id: int,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ImageListItem]:
    """Allowed at any time, also for locked and live games."""
    game = await get_game_or_404(db, game_id)
    await assert_can_use_game(db, user, game)
    usage = await images.used_by(db, game_id)
    return [
        ImageListItem(**_response(image).model_dump(), used_by=usage.get(image.id, []))
        for image in await images.list_images(db, game_id)
    ]


@router.post(
    "/games/{game_id}/images",
    response_model=ImageResponse,
    status_code=201,
    responses={200: {"description": "The game already holds these exact bytes"}},
)
async def upload_image(
    game_id: int,
    file: _UploadFile,
    response: Response,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_redis),
) -> ImageResponse:
    game = await get_game_or_404(db, game_id)
    await assert_can_use_game(db, user, game)
    user_id = await end_read_phase(db, user)
    processed = await _process(file)
    _, game = await relock_for_write(db, user_id, game_id)
    await assert_questions_editable(db, redis, game)
    image, created = await images.store_upload(db, game_id, processed)
    result = _response(image)
    await db.commit()
    if not created:
        response.status_code = 200
    return result


@router.put("/games/{game_id}/images/{image_id}", response_model=ImageResponse)
async def replace_image(
    game_id: int,
    image_id: str,
    file: _UploadFile,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_redis),
) -> ImageResponse:
    game = await get_game_or_404(db, game_id)
    await assert_can_use_game(db, user, game)
    await images.get_image_in_game_or_404(db, game_id, image_id)
    user_id = await end_read_phase(db, user)
    processed = await _process(file)
    _, game = await relock_for_write(db, user_id, game_id)
    image = await images.get_image_in_game_or_404(db, game_id, image_id)
    await assert_questions_editable(db, redis, game)
    image = await images.replace_image(db, game_id, image, processed)
    result = _response(image)
    await db.commit()
    return result


@router.delete("/games/{game_id}/images/{image_id}", status_code=204)
async def delete_image(
    game_id: int,
    image_id: str,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_redis),
) -> None:
    game = await get_game_or_404(db, game_id)
    await assert_can_use_game(db, user, game)
    await images.get_image_in_game_or_404(db, game_id, image_id)
    user_id = await end_read_phase(db, user)
    _, game = await relock_for_write(db, user_id, game_id)
    image = await images.get_image_in_game_or_404(db, game_id, image_id)
    await assert_questions_editable(db, redis, game)
    await images.delete_image(db, game_id, image)
    await db.commit()


@router.get(
    "/images/{image_id}",
    response_class=Response,
    responses={200: {"content": {"image/png": {}, "image/jpeg": {}, "image/webp": {}}}},
)
async def read_image(
    image_id: str,
    if_none_match: Annotated[str | None, Header()] = None,
) -> Response:
    """No authentication. Its own session, closed before the response is sent, so a
    burst of 150 phones does not hold pooled connections during the downloads."""
    async with AsyncSessionLocal() as db:
        meta = await images.read_image_meta(db, image_id)
        if meta is None:
            raise NotFoundError(f"Image {image_id} not found")
        content_type, sha256 = meta
        headers = {
            "ETag": f'"{sha256}"',
            "Cache-Control": "public, max-age=60",
        }
        if images.etag_matches(if_none_match, sha256):
            return Response(status_code=304, headers=headers)
        data = await images.read_image_data(db, image_id)
    if data is None:  # deleted between the two selects
        raise NotFoundError(f"Image {image_id} not found")
    return Response(
        content=data,
        media_type=content_type,
        headers={
            **headers,
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )
