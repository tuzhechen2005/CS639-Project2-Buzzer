from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import (
    CHAR,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, deferred, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .course import Course
    from .session import GameSession, SessionScore
    from .user import User


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=sa.text("''")
    )
    max_players: Mapped[int] = mapped_column(Integer, default=150, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    course: Mapped[Course] = relationship("Course", back_populates="games")
    questions: Mapped[list[Question]] = relationship(
        "Question",
        back_populates="game",
        cascade="all, delete-orphan",
        order_by="Question.order_index",
    )
    sessions: Mapped[list[GameSession]] = relationship(
        "GameSession", back_populates="game"
    )
    user_access: Mapped[list[UserGameAccess]] = relationship(
        "UserGameAccess", back_populates="game", cascade="all, delete-orphan"
    )
    images: Mapped[list[Image]] = relationship(
        "Image",
        back_populates="game",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    grading_type: Mapped[str] = mapped_column(
        Enum("ACCURACY", "COMPLETENESS", name="grading_type"), nullable=False
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    answer_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    time_limit_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    points_value: Mapped[float] = mapped_column(sa.Float, default=1.0, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    game: Mapped[Game] = relationship("Game", back_populates="questions")
    scores: Mapped[list[SessionScore]] = relationship(
        "SessionScore", back_populates="question"
    )


class UserGameAccess(Base):
    __tablename__ = "user_game_access"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), primary_key=True
    )

    user: Mapped[User] = relationship("User", back_populates="game_access")
    game: Mapped[Game] = relationship("Game", back_populates="user_access")


class Image(Base):
    """One stored picture, owned by a game (docs/plans/t8-image-support.md §A).

    `data` is deferred: lists and metadata queries never load the bytes. In an async
    session a deferred column cannot be lazy-loaded, so code that needs the bytes selects
    `Image.data` explicitly.
    """

    __tablename__ = "images"
    __table_args__ = (
        UniqueConstraint("game_id", "sha256", name="uq_images_game_sha256"),
        Index("ix_images_game_id", "game_id"),
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False
    )
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    # LargeBinary alone is a 64 KiB BLOB on MySQL; images need LONGBLOB.
    data: Mapped[bytes] = deferred(
        mapped_column(
            LargeBinary().with_variant(mysql.LONGBLOB(), "mysql"), nullable=False
        )
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    game: Mapped[Game] = relationship("Game", back_populates="images")
