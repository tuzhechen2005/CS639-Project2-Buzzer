from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ImageResponse(BaseModel):
    """Image metadata; never the bytes (those are served by GET /api/images/{id})."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    game_id: int
    content_type: str
    size_bytes: int
    width: int
    height: int
    sha256: str
    created_at: datetime
    updated_at: datetime


class ImageListItem(ImageResponse):
    used_by: list[int]  # ids of the game's questions that reference the image
