"""add gallery prompt unlocks

Revision ID: 7e2a1b4c9d6f
Revises: 24b7c9d1e3f5
Create Date: 2026-06-05 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7e2a1b4c9d6f"
down_revision: Union[str, Sequence[str], None] = "24b7c9d1e3f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gallery_prompt_unlocks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.BigInteger(), nullable=False),
        sa.Column("cost_credits", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["post_id"], ["gallery_posts.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "post_id",
            name="uq_gallery_prompt_unlocks_user_post",
        ),
    )
    op.create_index(
        "ix_gallery_prompt_unlocks_post_created_at",
        "gallery_prompt_unlocks",
        ["post_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_gallery_prompt_unlocks_user_created_at",
        "gallery_prompt_unlocks",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_gallery_prompt_unlocks_author_id"),
        "gallery_prompt_unlocks",
        ["author_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_gallery_prompt_unlocks_post_id"),
        "gallery_prompt_unlocks",
        ["post_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_gallery_prompt_unlocks_user_id"),
        "gallery_prompt_unlocks",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_gallery_prompt_unlocks_user_id"), table_name="gallery_prompt_unlocks")
    op.drop_index(op.f("ix_gallery_prompt_unlocks_post_id"), table_name="gallery_prompt_unlocks")
    op.drop_index(op.f("ix_gallery_prompt_unlocks_author_id"), table_name="gallery_prompt_unlocks")
    op.drop_index("ix_gallery_prompt_unlocks_user_created_at", table_name="gallery_prompt_unlocks")
    op.drop_index("ix_gallery_prompt_unlocks_post_created_at", table_name="gallery_prompt_unlocks")
    op.drop_table("gallery_prompt_unlocks")
