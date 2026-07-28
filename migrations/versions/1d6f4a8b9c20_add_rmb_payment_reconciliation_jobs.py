"""add RMB payment reconciliation jobs

Revision ID: 1d6f4a8b9c20
Revises: 62d4a8f9c7e1
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "1d6f4a8b9c20"
down_revision: Union[str, Sequence[str], None] = "62d4a8f9c7e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rmb_payment_reconciliation_jobs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=False),
        sa.Column("lease_token", sa.String(length=64), nullable=True),
        sa.Column("lease_until", sa.DateTime(), nullable=True),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("last_outcome", sa.String(length=100), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status in ('pending', 'processing', 'completed', 'exhausted')",
            name="ck_rmb_payment_reconciliation_jobs_status",
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id"),
    )
    op.create_index(
        "ix_rmb_payment_reconciliation_jobs_due",
        "rmb_payment_reconciliation_jobs",
        ["status", "next_attempt_at"],
    )
    op.create_index(
        "ix_rmb_payment_reconciliation_jobs_lease",
        "rmb_payment_reconciliation_jobs",
        ["status", "lease_until"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_rmb_payment_reconciliation_jobs_lease",
        table_name="rmb_payment_reconciliation_jobs",
    )
    op.drop_index(
        "ix_rmb_payment_reconciliation_jobs_due",
        table_name="rmb_payment_reconciliation_jobs",
    )
    op.drop_table("rmb_payment_reconciliation_jobs")
