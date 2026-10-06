from __future__ import annotations

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from ..services.question_types import known_types, validate_definition


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------


class CourseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1, max_length=255)
    semester: str = Field(..., min_length=1, max_length=50)


class CourseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(None, min_length=1, max_length=255)
    semester: str | None = Field(None, min_length=1, max_length=50)


class CourseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    semester: str
    is_system: bool = False
    created_at: datetime


class CourseAccessItem(BaseModel):
    """One UserCourseAccess row of a course, for the admin course view."""

    user_id: str
    display_name: str | None
    netid: str | None
    username: str | None
    role: str


# ---------------------------------------------------------------------------
# Roster
# ---------------------------------------------------------------------------


class RosterEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    course_id: int
    netid: str
    full_name: str
    email: str
    is_active: bool
    imported_at: datetime


class RosterUploadResult(BaseModel):
    imported: int
    updated: int
    deactivated: int
    errors: list[str]


class RosterEntryPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_active: bool | None = None
    netid: str | None = Field(None, min_length=1, max_length=100)
    full_name: str | None = Field(None, min_length=1, max_length=255)
    email: EmailStr | None = None


class RosterRowIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    netid: str = Field(..., min_length=1, max_length=100)
    full_name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., min_length=1, max_length=255)


class RosterImportPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: list[RosterRowIn] = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Games
# ---------------------------------------------------------------------------


class GameCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field("", max_length=5000)
    max_players: int = Field(150, ge=1, le=500)


class AdminGameCreate(GameCreate):
    """Admin alias body: the neutral endpoint takes the course from the path instead."""

    course_id: int = Field(..., gt=0)


class GameUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=5000)
    max_players: int | None = Field(None, ge=1, le=500)
    # Admins may move a game; anyone may send the game's current course unchanged.
    course_id: int | None = Field(None, gt=0)


class GameResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    course_id: int
    title: str
    description: str
    max_players: int
    created_at: datetime
    locked: bool = False


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


class QuestionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    grading_type: str = Field(..., pattern="^(ACCURACY|COMPLETENESS)$")
    prompt: str = Field(..., min_length=1, max_length=2000)
    config: dict = Field(default_factory=dict)
    answer_data: dict = Field(default_factory=dict)
    time_limit_seconds: int = Field(30, ge=2, le=300)
    points_value: float = Field(1.0, ge=0, le=100000)
    order_index: int | None = Field(None, ge=0)

    @field_validator("type")
    @classmethod
    def known_type(cls, v: str) -> str:
        if v not in known_types():
            raise ValueError(f"type must be one of: {', '.join(sorted(known_types()))}")
        return v

    @model_validator(mode="after")
    def validate_structure(self) -> QuestionCreate:
        # Per-type structure rules live in services/question_types.py.
        validate_definition(self)
        return self


class QuestionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str | None = None
    grading_type: str | None = Field(None, pattern="^(ACCURACY|COMPLETENESS)$")
    prompt: str | None = Field(None, min_length=1, max_length=2000)
    config: dict | None = None
    answer_data: dict | None = None
    time_limit_seconds: int | None = Field(None, ge=2, le=300)
    points_value: float | None = Field(None, ge=0, le=100000)
    order_index: int | None = Field(None, ge=0)

    @field_validator("type")
    @classmethod
    def known_type(cls, v: str | None) -> str | None:
        if v is not None and v not in known_types():
            raise ValueError(f"type must be one of: {', '.join(sorted(known_types()))}")
        return v


class QuestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    game_id: int
    type: str
    grading_type: str
    prompt: str
    config: dict
    answer_data: dict
    time_limit_seconds: int
    points_value: float
    order_index: int
    created_at: datetime


class QuestionReorder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order: list[int] = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Users (local accounts)
# ---------------------------------------------------------------------------


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    display_name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=72)
    email: EmailStr | None = None

    @field_validator("username")
    @classmethod
    def lower_username(cls, v: str) -> str:
        return v.lower()


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str | None = Field(
        None, min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$"
    )
    display_name: str | None = Field(None, min_length=1, max_length=255)
    email: EmailStr | None = None
    password: str | None = Field(None, min_length=8, max_length=72)
    role: str | None = Field(None, pattern="^(USER|ADMIN)$")

    @field_validator("username")
    @classmethod
    def lower_username(cls, v: str | None) -> str | None:
        return v.lower() if v is not None else None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    username: str | None
    netid: str | None
    display_name: str | None
    email: str | None
    role: str
    created_at: datetime
    last_login: datetime | None


# ---------------------------------------------------------------------------
# Access management
# ---------------------------------------------------------------------------


class CourseAccessGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int
    role: str = Field(..., pattern="^(HOST|PLAYER)$")


class GameAccessGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    game_id: int


class UserWithAccessResponse(UserResponse):
    course_access: list[dict]
    game_access: list[int]


# ---------------------------------------------------------------------------
# Sessions (admin view)
# ---------------------------------------------------------------------------


class AdminSessionItem(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    session_id: str
    room_code: str
    status: str
    game_id: int
    game_title: str
    course_id: int
    course_name: str
    course_semester: str
    host_display_name: str | None
    created_at: datetime
    completed_at: datetime | None
    player_count: int
