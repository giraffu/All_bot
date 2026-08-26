"""add history type filter index

Revision ID: 5c2a7e9d1b40
Revises: a6d2f8c4e1b9
Create Date: 2026-08-26 14:18:00.000000
"""

from typing import Sequence, Union

from alembic import op


revision: str = "5c2a7e9d1b40"
down_revision: Union[str, Sequence[str], None] = "a6d2f8c4e1b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_history_type",
            "history",
            ["type"],
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_history_type",
            postgresql_concurrently=True,
            if_exists=True,
        )
