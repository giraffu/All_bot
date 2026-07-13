"""expand history type length

Revision ID: 7f3a9c1d2e4b
Revises: 4f9a2b7c8d10
Create Date: 2026-06-17 17:05:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7f3a9c1d2e4b"
down_revision: Union[str, Sequence[str], None] = "4f9a2b7c8d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "history",
        "type",
        existing_type=sa.String(length=20),
        type_=sa.String(length=64),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "history",
        "type",
        existing_type=sa.String(length=64),
        type_=sa.String(length=20),
        existing_nullable=True,
    )
