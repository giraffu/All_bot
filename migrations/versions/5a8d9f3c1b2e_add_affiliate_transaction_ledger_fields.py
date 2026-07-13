"""add affiliate transaction ledger fields

Revision ID: 5a8d9f3c1b2e
Revises: dc319228d27a
Create Date: 2026-05-18 12:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5a8d9f3c1b2e"
down_revision: Union[str, Sequence[str], None] = "dc319228d27a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _assert_affiliate_transactions_empty(bind) -> None:
    existing_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM affiliate_transactions")
    ).scalar_one()
    if existing_count:
        raise RuntimeError(
            "affiliate_transactions is not empty; refusing to backfill "
            "direction/reference/idempotency fields with legacy defaults. "
            f"Please migrate existing rows explicitly before rerunning. "
            f"existing_count={existing_count}"
        )


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    _assert_affiliate_transactions_empty(bind)

    op.add_column(
        "affiliate_transactions",
        sa.Column("direction", sa.String(length=10), nullable=True),
    )
    op.add_column(
        "affiliate_transactions",
        sa.Column("reference_type", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "affiliate_transactions",
        sa.Column("reference_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "affiliate_transactions",
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
    )

    bind.execute(
        sa.text(
            """
        UPDATE affiliate_transactions
        SET
            direction = COALESCE(direction, 'IN'),
            reference_type = COALESCE(reference_type, 'LEGACY'),
            reference_id = COALESCE(reference_id, id::text),
            idempotency_key = COALESCE(
                idempotency_key,
                'legacy-affiliate-transaction:' || id::text
            )
        """
        )
    )

    op.alter_column("affiliate_transactions", "direction", nullable=False)
    op.alter_column("affiliate_transactions", "reference_type", nullable=False)
    op.alter_column("affiliate_transactions", "reference_id", nullable=False)
    op.alter_column("affiliate_transactions", "idempotency_key", nullable=False)

    op.create_unique_constraint(
        "uq_affiliate_transactions_idempotency_key",
        "affiliate_transactions",
        ["idempotency_key"],
    )
    op.create_index(
        "ix_affiliate_transactions_user_status_direction",
        "affiliate_transactions",
        ["user_id", "status", "direction"],
        unique=False,
    )
    op.create_index(
        "ix_affiliate_transactions_reference_type_reference_id",
        "affiliate_transactions",
        ["reference_type", "reference_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_affiliate_transactions_reference_type_reference_id",
        table_name="affiliate_transactions",
    )
    op.drop_index(
        "ix_affiliate_transactions_user_status_direction",
        table_name="affiliate_transactions",
    )
    op.drop_constraint(
        "uq_affiliate_transactions_idempotency_key",
        "affiliate_transactions",
        type_="unique",
    )
    op.drop_column("affiliate_transactions", "idempotency_key")
    op.drop_column("affiliate_transactions", "reference_id")
    op.drop_column("affiliate_transactions", "reference_type")
    op.drop_column("affiliate_transactions", "direction")
