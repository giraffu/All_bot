"""add private character reference library

Revision ID: 62d4a8f9c7e1
Revises: 3e9c7a1b5d24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "62d4a8f9c7e1"
down_revision: Union[str, Sequence[str], None] = "3e9c7a1b5d24"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "character_references",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("source_object_key", sa.String(length=1024), nullable=False),
        sa.Column("sheet_object_key", sa.String(length=1024), nullable=True),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="pending", nullable=False
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status in ('pending', 'ready', 'failed', 'deleted')",
            name="ck_character_references_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_character_references_user_id", "character_references", ["user_id"]
    )
    op.create_index(
        "ix_character_references_user_status",
        "character_references",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_character_references_task_id",
        "character_references",
        ["task_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_character_references_task_id", table_name="character_references")
    op.drop_index(
        "ix_character_references_user_status", table_name="character_references"
    )
    op.drop_index("ix_character_references_user_id", table_name="character_references")
    op.drop_table("character_references")
