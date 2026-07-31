"""add affiliate usdt redeem workflow

Revision ID: c2e4f6a8b0d1
Revises: 7d2a9b4c6e81
"""

from alembic import op
import sqlalchemy as sa


revision = "c2e4f6a8b0d1"
down_revision = "7d2a9b4c6e81"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("affiliate_redeems", sa.Column("payout_network", sa.String(20)))
    op.add_column("affiliate_redeems", sa.Column("payout_address", sa.String(128)))
    op.add_column("affiliate_redeems", sa.Column("payout_tx_hash", sa.String(128)))
    op.add_column("affiliate_redeems", sa.Column("admin_note", sa.String(500)))
    op.add_column("affiliate_redeems", sa.Column("rejection_reason", sa.String(500)))
    op.add_column("affiliate_redeems", sa.Column("processed_by", sa.String(255)))
    op.add_column("affiliate_redeems", sa.Column("processed_at", sa.DateTime()))
    op.create_unique_constraint(
        "uq_affiliate_redeems_payout_tx_hash",
        "affiliate_redeems",
        ["payout_tx_hash"],
    )
    op.create_index(
        "uq_affiliate_redeems_user_pending_usdt",
        "affiliate_redeems",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text(
            "redeem_type = 'USDT' AND status = 'PENDING'"
        ),
    )
    op.create_index(
        "ix_affiliate_redeems_type_status_created",
        "affiliate_redeems",
        ["redeem_type", "status", "created_at"],
    )


def downgrade():
    op.drop_index(
        "ix_affiliate_redeems_type_status_created",
        table_name="affiliate_redeems",
    )
    op.drop_index(
        "uq_affiliate_redeems_user_pending_usdt",
        table_name="affiliate_redeems",
    )
    op.drop_constraint(
        "uq_affiliate_redeems_payout_tx_hash",
        "affiliate_redeems",
        type_="unique",
    )
    for column in (
        "processed_at",
        "processed_by",
        "rejection_reason",
        "admin_note",
        "payout_tx_hash",
        "payout_address",
        "payout_network",
    ):
        op.drop_column("affiliate_redeems", column)
