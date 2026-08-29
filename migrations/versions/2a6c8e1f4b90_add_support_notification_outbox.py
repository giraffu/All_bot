"""add durable support notification outbox

Revision ID: 2a6c8e1f4b90
Revises: 8d4f2a6b1c90
Create Date: 2026-08-29 15:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2a6c8e1f4b90"
down_revision: Union[str, Sequence[str], None] = "8d4f2a6b1c90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "support_notification_outbox",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "ticket_id",
            sa.BigInteger(),
            sa.ForeignKey("support_tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("recipient_telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("payload_text", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.String(24), nullable=False, server_default="pending"
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("lease_token", sa.String(64)),
        sa.Column("lease_owner", sa.String(128)),
        sa.Column("lease_until", sa.DateTime()),
        sa.Column("last_error_type", sa.String(100)),
        sa.Column("last_error_message", sa.String(500)),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("sent_at", sa.DateTime()),
        sa.Column("failed_at", sa.DateTime()),
        sa.UniqueConstraint(
            "ticket_id",
            "recipient_telegram_user_id",
            name="uq_support_notification_outbox_ticket_recipient",
        ),
        sa.CheckConstraint(
            "status in ('pending', 'processing', 'retry', 'sent', 'failed')",
            name="ck_support_notification_outbox_status",
        ),
    )
    op.create_index(
        "ix_support_notification_outbox_claim",
        "support_notification_outbox",
        ["status", "next_attempt_at", "id"],
    )
    op.create_index(
        "ix_support_notification_outbox_recipient_created",
        "support_notification_outbox",
        ["recipient_telegram_user_id", "created_at"],
    )
    op.create_table(
        "support_notification_attempts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "outbox_id",
            sa.BigInteger(),
            sa.ForeignKey("support_notification_outbox.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("worker_id", sa.String(128), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger()),
        sa.Column("error_type", sa.String(100)),
        sa.Column("error_message", sa.String(500)),
        sa.Column("retry_at", sa.DateTime()),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("finished_at", sa.DateTime()),
        sa.UniqueConstraint(
            "outbox_id",
            "attempt_number",
            name="uq_support_notification_attempt_number",
        ),
        sa.CheckConstraint(
            "status in ('processing', 'retry', 'sent', 'failed', 'abandoned')",
            name="ck_support_notification_attempt_status",
        ),
    )
    op.create_index(
        "ix_support_notification_attempts_created",
        "support_notification_attempts",
        ["created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_support_notification_attempts_created",
        table_name="support_notification_attempts",
    )
    op.drop_table("support_notification_attempts")
    op.drop_index(
        "ix_support_notification_outbox_recipient_created",
        table_name="support_notification_outbox",
    )
    op.drop_index(
        "ix_support_notification_outbox_claim",
        table_name="support_notification_outbox",
    )
    op.drop_table("support_notification_outbox")
