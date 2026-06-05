"""add runtime checkpoints

Revision ID: 0f4e7b9c1a23
Revises: 7e2a1b4c9d6f
Create Date: 2026-06-05 22:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0f4e7b9c1a23"
down_revision: Union[str, Sequence[str], None] = "7e2a1b4c9d6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "runtime_checkpoints",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column(
            "value",
            sa.JSON(),
            server_default=sa.text("'{}'::json"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("runtime_checkpoints")
