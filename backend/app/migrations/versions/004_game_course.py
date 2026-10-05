"""Attach every game to a course; add the system "Unassigned" course (T4)

Revision ID: 004
Revises: 003
Create Date: 2026-10-05

See docs/plans/t4-ui-restructuring.md §A for the step order.
"""

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

_FK_NAME = "fk_games_course_id"
_INDEX_NAME = "ix_games_course_id"


def upgrade() -> None:
    conn = op.get_bind()

    # 1. System-course flag.
    op.add_column(
        "courses",
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # 2. Nullable column first, no FK yet, so existing rows can be backfilled.
    op.add_column("games", sa.Column("course_id", sa.Integer(), nullable=True))

    # 3. Each played game takes the course of its most recent session.
    conn.execute(
        sa.text(
            """
            UPDATE games g
            SET g.course_id = (
                SELECT gs.course_id FROM game_sessions gs
                WHERE gs.game_id = g.id
                ORDER BY gs.created_at DESC, gs.id DESC
                LIMIT 1
            )
            """
        )
    )

    # 4. Games never played go to the system "Unassigned" course.
    unassigned = conn.execute(
        sa.text("SELECT COUNT(*) FROM games WHERE course_id IS NULL")
    ).scalar_one()
    if unassigned:
        conn.execute(
            sa.text(
                "INSERT INTO courses (name, semester, is_system) "
                "VALUES ('Unassigned', '', 1)"
            )
        )
        system_id = conn.execute(
            sa.text("SELECT id FROM courses WHERE is_system = 1 ORDER BY id LIMIT 1")
        ).scalar_one()
        conn.execute(
            sa.text("UPDATE games SET course_id = :cid WHERE course_id IS NULL"),
            {"cid": system_id},
        )
        logger.warning(
            "004: %d unplayed game(s) assigned to the system course 'Unassigned' (id=%d)",
            unassigned,
            system_id,
        )

    # 5–6. Enforce the invariant, then add the index and FK.
    op.alter_column("games", "course_id", existing_type=sa.Integer(), nullable=False)
    op.create_index(_INDEX_NAME, "games", ["course_id"])
    op.create_foreign_key(_FK_NAME, "games", "courses", ["course_id"], ["id"])

    # 7. No new grants. Report grants that stop working because the user is not a
    #    HOST of the game's (new) course, so an admin can review them.
    inactive = conn.execute(
        sa.text(
            """
            SELECT uga.user_id, uga.game_id, g.course_id
            FROM user_game_access uga
            JOIN games g ON g.id = uga.game_id
            LEFT JOIN user_course_access uca
              ON uca.user_id = uga.user_id
             AND uca.course_id = g.course_id
             AND uca.role = 'HOST'
            WHERE uca.user_id IS NULL
            """
        )
    ).all()
    for row in inactive:
        logger.warning(
            "004: inactive game grant user=%s game=%s (not HOST of course %s)",
            row.user_id,
            row.game_id,
            row.course_id,
        )


def downgrade() -> None:
    op.drop_constraint(_FK_NAME, "games", type_="foreignkey")
    op.drop_index(_INDEX_NAME, table_name="games")
    op.drop_column("games", "course_id")
    # The system course can hold no sessions, roster entries or grants (§B), so it can go.
    op.execute(sa.text("DELETE FROM courses WHERE is_system = 1"))
    op.drop_column("courses", "is_system")
