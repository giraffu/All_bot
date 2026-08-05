"""add media archive outbox and verified receipts

Revision ID: a4c8e2f6b901
Revises: 8e1d3f5a7b90
"""

from alembic import op
import sqlalchemy as sa


revision = "a4c8e2f6b901"
down_revision = "8e1d3f5a7b90"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "media_archive_outbox",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "history_id",
            sa.Integer(),
            sa.ForeignKey("history.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("manifest_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("lease_owner", sa.String(128)),
        sa.Column("lease_expires_at", sa.DateTime()),
        sa.Column(
            "available_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(64)),
        sa.Column("last_error_message", sa.String(1000)),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("archived_at", sa.DateTime()),
        sa.UniqueConstraint("history_id", name="uq_media_archive_outbox_history"),
        sa.CheckConstraint(
            "status in ('pending', 'leased', 'retry', 'archived', 'manual_review')",
            name="ck_media_archive_outbox_status",
        ),
    )
    op.create_index(
        "ix_media_archive_outbox_claim",
        "media_archive_outbox",
        ["status", "available_at", "id"],
    )
    op.create_table(
        "media_archive_receipts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "history_id",
            sa.Integer(),
            sa.ForeignKey("history.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(64), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("mime_type", sa.String(128)),
        sa.Column("nas_bucket", sa.String(128), nullable=False),
        sa.Column("nas_key", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.String(32), nullable=False, server_default="archived_verified"
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "history_id", "role", "ordinal", name="uq_media_archive_receipt_asset"
        ),
        sa.CheckConstraint(
            "status in ('archived_verified', 'checksum_error')",
            name="ck_media_archive_receipt_status",
        ),
    )
    op.create_index(
        "ix_media_archive_receipts_sha256", "media_archive_receipts", ["sha256"]
    )


def downgrade():
    op.drop_index(
        "ix_media_archive_receipts_sha256", table_name="media_archive_receipts"
    )
    op.drop_table("media_archive_receipts")
    op.drop_index("ix_media_archive_outbox_claim", table_name="media_archive_outbox")
    op.drop_table("media_archive_outbox")
