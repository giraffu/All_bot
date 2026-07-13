"""add private qqcc bots

Revision ID: 3e9c7a1b5d24
Revises: 2d8b6f1a9c03
Create Date: 2026-07-12 16:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3e9c7a1b5d24"
down_revision: Union[str, Sequence[str], None] = "2d8b6f1a9c03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "private_qqcc_bots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_bot_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_username", sa.String(length=64), nullable=True),
        sa.Column("telegram_display_name", sa.String(length=255), nullable=True),
        sa.Column("token_ciphertext", sa.Text(), nullable=False),
        sa.Column(
            "token_key_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("token_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("webhook_public_id", sa.String(length=64), nullable=False),
        sa.Column("webhook_secret_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "config",
            sa.JSON(),
            server_default=sa.text("'{}'::json"),
            nullable=False,
        ),
        sa.Column(
            "config_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "owner_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "admin_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "runtime_status",
            sa.String(length=32),
            server_default=sa.text("'provisioning'"),
            nullable=False,
        ),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_error_message", sa.String(length=500), nullable=True),
        sa.Column("last_webhook_at", sa.DateTime(), nullable=True),
        sa.Column("last_update_at", sa.DateTime(), nullable=True),
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
            "runtime_status in ('provisioning', 'active', 'paused', 'disabled', 'error')",
            name="ck_private_qqcc_bots_runtime_status",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "token_fingerprint",
            name="uq_private_qqcc_bots_token_fingerprint",
        ),
        sa.UniqueConstraint(
            "webhook_public_id",
            name="uq_private_qqcc_bots_webhook_public_id",
        ),
    )
    op.create_index(
        "ix_private_qqcc_bots_owner_user_id",
        "private_qqcc_bots",
        ["owner_user_id"],
        unique=True,
    )
    op.create_index(
        "ix_private_qqcc_bots_telegram_bot_id",
        "private_qqcc_bots",
        ["telegram_bot_id"],
        unique=True,
    )

    op.create_table(
        "private_qqcc_bot_audit_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("private_bot_id", sa.BigInteger(), nullable=True),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_bot_id", sa.BigInteger(), nullable=False),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("actor_identifier", sa.String(length=128), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("before_status", sa.String(length=32), nullable=True),
        sa.Column("after_status", sa.String(length=32), nullable=True),
        sa.Column(
            "details",
            sa.JSON(),
            server_default=sa.text("'{}'::json"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "actor_type in ('owner', 'admin', 'system')",
            name="ck_private_qqcc_bot_audit_logs_actor_type",
        ),
        sa.ForeignKeyConstraint(
            ["private_bot_id"],
            ["private_qqcc_bots.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_private_qqcc_bot_audit_logs_private_bot_id",
        "private_qqcc_bot_audit_logs",
        ["private_bot_id"],
        unique=False,
    )
    op.create_index(
        "ix_private_qqcc_bot_audit_logs_owner_user_id",
        "private_qqcc_bot_audit_logs",
        ["owner_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_private_qqcc_bot_audit_logs_telegram_bot_id",
        "private_qqcc_bot_audit_logs",
        ["telegram_bot_id"],
        unique=False,
    )

    op.create_table(
        "private_bot_task_submissions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("submission_key", sa.String(length=128), nullable=False),
        sa.Column("private_bot_id", sa.BigInteger(), nullable=False),
        sa.Column("update_id", sa.BigInteger(), nullable=False),
        sa.Column("submission_sequence", sa.Integer(), nullable=False),
        sa.Column("internal_user_id", sa.BigInteger(), nullable=False),
        sa.Column("client_type", sa.String(length=128), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("request_sha256", sa.String(length=64), nullable=False),
        sa.Column("registry_task_id", sa.String(length=64), nullable=False),
        sa.Column("dispatch_task_id", sa.String(length=64), nullable=False),
        sa.Column("dispatch_started_at", sa.DateTime(), nullable=True),
        sa.Column("submission_owner_token", sa.String(length=64), nullable=True),
        sa.Column("submission_owner_deadline_at", sa.DateTime(), nullable=True),
        sa.Column("reconcile_not_before_at", sa.DateTime(), nullable=True),
        sa.Column(
            "submission_owner_fence",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("backend_task_id", sa.String(length=128), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'reserved'"),
            nullable=False,
        ),
        sa.Column("actual_cost", sa.Integer(), nullable=True),
        sa.Column("debit_confirmed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "saved_inputs",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column(
            "compensation_status",
            sa.String(length=32),
            server_default=sa.text("'not_required'"),
            nullable=False,
        ),
        sa.Column("compensation_lease_token", sa.String(length=64), nullable=True),
        sa.Column("compensation_lease_until", sa.DateTime(), nullable=True),
        sa.Column(
            "compensation_attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("compensation_last_error", sa.String(length=500), nullable=True),
        sa.Column("compensation_completed_at", sa.DateTime(), nullable=True),
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
            "status in ('reserved', 'dispatching', 'submitted', 'failed')",
            name="ck_private_bot_task_submissions_status",
        ),
        sa.CheckConstraint(
            "compensation_status in ('not_required', 'pending', 'processing', 'completed')",
            name="ck_private_bot_task_submissions_compensation_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "submission_key",
            name="uq_private_bot_task_submissions_submission_key",
        ),
        sa.UniqueConstraint(
            "registry_task_id",
            name="uq_private_bot_task_submissions_registry_task_id",
        ),
    )
    op.create_index(
        "ix_private_bot_task_submissions_private_bot_id",
        "private_bot_task_submissions",
        ["private_bot_id"],
        unique=False,
    )
    op.create_index(
        "ix_private_bot_task_submissions_internal_user_id",
        "private_bot_task_submissions",
        ["internal_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_private_bot_task_submissions_reconcile_due",
        "private_bot_task_submissions",
        ["status", "reconcile_not_before_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_private_bot_task_submissions_compensation_due",
        "private_bot_task_submissions",
        ["compensation_status", "compensation_lease_until", "id"],
        unique=False,
    )
    op.create_index(
        "ix_private_bot_task_submissions_retention",
        "private_bot_task_submissions",
        ["status", "compensation_status", "updated_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_private_bot_task_submissions_retention",
        table_name="private_bot_task_submissions",
    )
    op.drop_index(
        "ix_private_bot_task_submissions_compensation_due",
        table_name="private_bot_task_submissions",
    )
    op.drop_index(
        "ix_private_bot_task_submissions_reconcile_due",
        table_name="private_bot_task_submissions",
    )
    op.drop_index(
        "ix_private_bot_task_submissions_internal_user_id",
        table_name="private_bot_task_submissions",
    )
    op.drop_index(
        "ix_private_bot_task_submissions_private_bot_id",
        table_name="private_bot_task_submissions",
    )
    op.drop_table("private_bot_task_submissions")
    op.drop_index(
        "ix_private_qqcc_bot_audit_logs_telegram_bot_id",
        table_name="private_qqcc_bot_audit_logs",
    )
    op.drop_index(
        "ix_private_qqcc_bot_audit_logs_owner_user_id",
        table_name="private_qqcc_bot_audit_logs",
    )
    op.drop_index(
        "ix_private_qqcc_bot_audit_logs_private_bot_id",
        table_name="private_qqcc_bot_audit_logs",
    )
    op.drop_table("private_qqcc_bot_audit_logs")
    op.drop_index(
        "ix_private_qqcc_bots_telegram_bot_id",
        table_name="private_qqcc_bots",
    )
    op.drop_index(
        "ix_private_qqcc_bots_owner_user_id",
        table_name="private_qqcc_bots",
    )
    op.drop_table("private_qqcc_bots")
