"""add user follows table

Revision ID: e6f7a8b9c0d1
Revises: d4e5f6a7b8c9
Create Date: 2026-05-28 20:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e6f7a8b9c0d1"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_follows",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("follower_id", sa.BigInteger(), nullable=False),
        sa.Column("followee_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["followee_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["follower_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "follower_id",
            "followee_id",
            name="uq_user_follows_follower_followee",
        ),
    )
    op.create_index(
        "ix_user_follows_follower_created_at",
        "user_follows",
        ["follower_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_user_follows_followee_created_at",
        "user_follows",
        ["followee_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_follows_follower_id"),
        "user_follows",
        ["follower_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_follows_followee_id"),
        "user_follows",
        ["followee_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_user_follows_followee_id"), table_name="user_follows")
    op.drop_index(op.f("ix_user_follows_follower_id"), table_name="user_follows")
    op.drop_index("ix_user_follows_followee_created_at", table_name="user_follows")
    op.drop_index("ix_user_follows_follower_created_at", table_name="user_follows")
    op.drop_table("user_follows")
