"""add site notice audience fields

Revision ID: c9d2e3f4a5b6
Revises: b8f1c2d3e4f5
Create Date: 2026-05-28 11:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c9d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "b8f1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "site_notices",
        sa.Column(
            "target_groups",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.add_column(
        "site_notices",
        sa.Column(
            "target_identities",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )


def downgrade() -> None:
    op.drop_column("site_notices", "target_identities")
    op.drop_column("site_notices", "target_groups")
