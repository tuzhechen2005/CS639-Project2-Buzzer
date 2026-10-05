"""Images stored in the database, owned by a game (T8)

Revision ID: 005
Revises: 004
Create Date: 2026-10-05

See docs/plans/t8-image-support.md §A. `data` is a LONGBLOB: SQLAlchemy's plain
LargeBinary would be a 64 KiB BLOB on MySQL.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "images",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(20), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.CHAR(64), nullable=False),
        sa.Column(
            "data",
            sa.LargeBinary().with_variant(mysql.LONGBLOB(), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["game_id"], ["games.id"], name="fk_images_game_id", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("game_id", "sha256", name="uq_images_game_sha256"),
    )
    op.create_index("ix_images_game_id", "images", ["game_id"])


def downgrade() -> None:
    op.drop_index("ix_images_game_id", table_name="images")
    op.drop_table("images")
