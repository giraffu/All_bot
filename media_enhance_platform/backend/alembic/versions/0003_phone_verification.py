"""Add privacy-minimized phone verification state.

Revision ID: 0003_phone_verification
Revises: 0002_attempt_provider_binding
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_phone_verification"
down_revision = "0002_attempt_provider_binding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    user_columns = {item["name"] for item in inspector.get_columns("users")}
    if "phone_hash" not in user_columns:
        op.add_column("users", sa.Column("phone_hash", sa.String(64), nullable=True))
    if "phone_masked" not in user_columns:
        op.add_column("users", sa.Column("phone_masked", sa.String(20), nullable=True))
    if "phone_verified_at" not in user_columns:
        op.add_column(
            "users", sa.Column("phone_verified_at", sa.DateTime(timezone=True), nullable=True)
        )
    user_indexes = {item["name"] for item in sa.inspect(bind).get_indexes("users")}
    phone_index = op.f("ix_users_phone_hash")
    if phone_index not in user_indexes:
        op.create_index(phone_index, "users", ["phone_hash"], unique=True)

    inspector = sa.inspect(bind)
    if "sms_verification_challenges" not in inspector.get_table_names():
        op.create_table(
            "sms_verification_challenges",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("phone_hash", sa.String(64), nullable=False),
            sa.Column("phone_masked", sa.String(20), nullable=False),
            sa.Column("provider_reference", sa.String(180), nullable=True),
            sa.Column("verify_attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            op.f("ix_sms_verification_challenges_user_id"),
            "sms_verification_challenges",
            ["user_id"],
        )
        op.create_index(
            op.f("ix_sms_verification_challenges_phone_hash"),
            "sms_verification_challenges",
            ["phone_hash"],
        )
        op.create_index(
            op.f("ix_sms_verification_challenges_expires_at"),
            "sms_verification_challenges",
            ["expires_at"],
        )
        op.create_index(
            op.f("ix_sms_verification_challenges_created_at"),
            "sms_verification_challenges",
            ["created_at"],
        )


def downgrade() -> None:
    op.drop_table("sms_verification_challenges")
    op.drop_index(op.f("ix_users_phone_hash"), table_name="users")
    op.drop_column("users", "phone_verified_at")
    op.drop_column("users", "phone_masked")
    op.drop_column("users", "phone_hash")
