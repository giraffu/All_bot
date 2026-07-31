from datetime import datetime

from sqlalchemy import (
    DECIMAL,
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index(
            "idx_users_lower_username",
            func.lower(Column("username", String(100))),
            unique=True,
        ),
        Index("ix_users_created_at_id", "created_at", "id"),
        Index("ix_users_credits_id", "credits", "id"),
        Index("ix_users_checkin_count_id", "checkin_count", "id"),
        Index("ix_users_referral_count_id", "referral_count", "id"),
        Index("ix_users_generation_count_id", "generation_count", "id"),
        Index("ix_users_last_activity_id", "last_activity", "id"),
    )

    id = Column(
        BigInteger, primary_key=True, autoincrement=True
    )  # Internal System ID (was Telegram User ID)

    # New Multi-platform login fields
    telegram_id = Column(
        BigInteger, unique=True, index=True, nullable=True
    )  # Real TG ID
    google_id = Column(String(255), unique=True, index=True, nullable=True)
    email = Column(String(255), unique=True, index=True, nullable=True)
    hashed_password = Column(String(255), nullable=True)
    password_version = Column(Integer, default=1, nullable=False)

    username = Column(String(100), nullable=True)
    full_name = Column(String(200), nullable=True)
    language_code = Column(String(20), nullable=True)  # i18n support
    credits = Column(Integer, default=6)
    last_checkin = Column(Date, nullable=True)
    is_channel_member = Column(Boolean, default=False)
    is_submission_banned = Column(
        Boolean, default=False, nullable=False, server_default=text("false")
    )
    submission_banned_at = Column(DateTime, nullable=True)
    submission_ban_reason = Column(String(255), nullable=True)
    user_group = Column(
        String(20), default="凡人"
    )  # 凡人, 练气期, 筑基期, 金丹期, 元婴期
    current_identity = Column(
        String(20), default="外门弟子"
    )  # 外门弟子, 内门弟子, 核心弟子, 真传弟子
    identity_expire_at = Column(DateTime, nullable=True)
    total_contributions = Column(Integer, default=0)  # 累计贡献次数
    approved_contributions = Column(Integer, default=0)  # 累计被采纳次数

    # Denormalized counts for performance
    referral_count = Column(Integer, default=0)
    generation_count = Column(Integer, default=0)
    checkin_count = Column(Integer, default=0)
    last_activity = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.now)
    invited_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)

    # Relationships
    inviter_user = relationship("User", remote_side=[id], backref="invited_users")
    referrals_made = relationship(
        "Referral", foreign_keys="Referral.inviter_id", back_populates="inviter"
    )
    referred_by = relationship(
        "Referral", foreign_keys="Referral.invitee_id", back_populates="invitee"
    )
    history = relationship("History", back_populates="user")
    private_qqcc_bot = relationship(
        "PrivateQqccBot",
        back_populates="owner",
        uselist=False,
        passive_deletes=True,
    )


class SupportTicket(Base):
    __tablename__ = "support_tickets"
    __table_args__ = (
        CheckConstraint(
            "category in ('recharge', 'bug', 'suggestion', 'business', 'uncategorized')",
            name="ck_support_tickets_category",
        ),
        CheckConstraint(
            "status in ('open', 'processing', 'resolved', 'closed')",
            name="ck_support_tickets_status",
        ),
        Index("ix_support_tickets_status_last_message", "status", "last_message_at"),
        Index("ix_support_tickets_telegram_status", "telegram_user_id", "status"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    telegram_user_id = Column(BigInteger, nullable=False, index=True)
    internal_user_id = Column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    category = Column(
        String(32), nullable=False, server_default=text("'uncategorized'")
    )
    status = Column(String(32), nullable=False, server_default=text("'open'"))
    username = Column(String(100), nullable=True)
    full_name = Column(String(200), nullable=True)
    language_code = Column(String(20), nullable=True)
    assigned_admin = Column(String(100), nullable=True)
    closed_at = Column(DateTime, nullable=True)
    last_message_at = Column(
        DateTime, nullable=False, default=datetime.now, server_default=func.now()
    )
    created_at = Column(
        DateTime, nullable=False, default=datetime.now, server_default=func.now()
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
        server_default=func.now(),
    )


class SupportMessage(Base):
    __tablename__ = "support_messages"
    __table_args__ = (
        CheckConstraint(
            "sender_type in ('user', 'admin', 'internal')",
            name="ck_support_messages_sender_type",
        ),
        Index("ix_support_messages_ticket_created", "ticket_id", "created_at", "id"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ticket_id = Column(
        BigInteger,
        ForeignKey("support_tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_type = Column(String(16), nullable=False)
    body = Column(Text, nullable=True)
    telegram_message_id = Column(BigInteger, nullable=True)
    attachments = Column(
        JSON, nullable=False, default=list, server_default=text("'[]'::json")
    )
    created_at = Column(
        DateTime, nullable=False, default=datetime.now, server_default=func.now()
    )

    ticket = relationship("SupportTicket", backref="messages")


class PrivateQqccBot(Base):
    __tablename__ = "private_qqcc_bots"
    __table_args__ = (
        CheckConstraint(
            "runtime_status in ('provisioning', 'active', 'paused', 'disabled', 'error')",
            name="ck_private_qqcc_bots_runtime_status",
        ),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    owner_user_id = Column(
        BigInteger,
        ForeignKey("users.id"),
        unique=True,
        index=True,
        nullable=False,
    )
    telegram_bot_id = Column(
        BigInteger,
        unique=True,
        index=True,
        nullable=False,
    )
    telegram_username = Column(String(64), nullable=True)
    telegram_display_name = Column(String(255), nullable=True)
    token_ciphertext = Column(Text, nullable=False)
    token_key_version = Column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    token_fingerprint = Column(String(64), unique=True, nullable=False)
    webhook_public_id = Column(String(64), unique=True, nullable=False)
    webhook_secret_hash = Column(String(64), nullable=True)
    config = Column(
        JSON,
        nullable=False,
        default=dict,
        server_default=text("'{}'::json"),
    )
    config_version = Column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    owner_enabled = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    admin_enabled = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    runtime_status = Column(
        String(32),
        nullable=False,
        default="provisioning",
        server_default=text("'provisioning'"),
    )
    last_error_code = Column(String(64), nullable=True)
    last_error_message = Column(String(500), nullable=True)
    last_webhook_at = Column(DateTime, nullable=True)
    last_update_at = Column(DateTime, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.now,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
        server_default=func.now(),
    )

    owner = relationship("User", back_populates="private_qqcc_bot")
    audit_logs = relationship(
        "PrivateQqccBotAuditLog",
        back_populates="private_bot",
        passive_deletes="all",
    )


class PrivateQqccBotAuditLog(Base):
    __tablename__ = "private_qqcc_bot_audit_logs"
    __table_args__ = (
        CheckConstraint(
            "actor_type in ('owner', 'admin', 'system')",
            name="ck_private_qqcc_bot_audit_logs_actor_type",
        ),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    private_bot_id = Column(
        BigInteger,
        ForeignKey("private_qqcc_bots.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    owner_user_id = Column(BigInteger, nullable=False, index=True)
    telegram_bot_id = Column(BigInteger, nullable=False, index=True)
    actor_type = Column(String(32), nullable=False)
    actor_identifier = Column(String(128), nullable=True)
    action = Column(String(64), nullable=False)
    before_status = Column(String(32), nullable=True)
    after_status = Column(String(32), nullable=True)
    details = Column(
        JSON,
        nullable=False,
        default=dict,
        server_default=text("'{}'::json"),
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.now,
        server_default=func.now(),
    )

    private_bot = relationship("PrivateQqccBot", back_populates="audit_logs")


class PrivateBotTaskSubmission(Base):
    """Durable idempotency outcome for one task spawned by a private Bot update."""

    __tablename__ = "private_bot_task_submissions"
    __table_args__ = (
        CheckConstraint(
            "status in ('reserved', 'dispatching', 'submitted', 'failed')",
            name="ck_private_bot_task_submissions_status",
        ),
        CheckConstraint(
            "compensation_status in ('not_required', 'pending', 'processing', 'completed')",
            name="ck_private_bot_task_submissions_compensation_status",
        ),
        UniqueConstraint(
            "submission_key",
            name="uq_private_bot_task_submissions_submission_key",
        ),
        UniqueConstraint(
            "registry_task_id",
            name="uq_private_bot_task_submissions_registry_task_id",
        ),
        Index(
            "ix_private_bot_task_submissions_reconcile_due",
            "status",
            "reconcile_not_before_at",
            "id",
        ),
        Index(
            "ix_private_bot_task_submissions_compensation_due",
            "compensation_status",
            "compensation_lease_until",
            "id",
        ),
        Index(
            "ix_private_bot_task_submissions_retention",
            "status",
            "compensation_status",
            "updated_at",
            "id",
        ),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    submission_key = Column(String(128), nullable=False)
    private_bot_id = Column(BigInteger, nullable=False, index=True)
    update_id = Column(BigInteger, nullable=False)
    submission_sequence = Column(Integer, nullable=False)
    internal_user_id = Column(BigInteger, nullable=False, index=True)
    client_type = Column(String(128), nullable=False)
    task_type = Column(String(64), nullable=False)
    request_sha256 = Column(String(64), nullable=False)
    registry_task_id = Column(String(64), nullable=False)
    dispatch_task_id = Column(String(64), nullable=False)
    dispatch_started_at = Column(DateTime, nullable=True)
    submission_owner_token = Column(String(64), nullable=True)
    submission_owner_deadline_at = Column(DateTime, nullable=True)
    reconcile_not_before_at = Column(DateTime, nullable=True)
    submission_owner_fence = Column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    backend_task_id = Column(String(128), nullable=True)
    status = Column(
        String(32),
        nullable=False,
        default="reserved",
        server_default=text("'reserved'"),
    )
    actual_cost = Column(Integer, nullable=True)
    debit_confirmed_at = Column(DateTime, nullable=True)
    saved_inputs = Column(
        JSON,
        nullable=False,
        default=list,
        server_default=text("'[]'::json"),
    )
    error_code = Column(String(64), nullable=True)
    error_message = Column(String(500), nullable=True)
    compensation_status = Column(
        String(32),
        nullable=False,
        default="not_required",
        server_default=text("'not_required'"),
    )
    compensation_lease_token = Column(String(64), nullable=True)
    compensation_lease_until = Column(DateTime, nullable=True)
    compensation_attempts = Column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    compensation_last_error = Column(String(500), nullable=True)
    compensation_completed_at = Column(DateTime, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.now,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
        server_default=func.now(),
    )


class Referral(Base):
    __tablename__ = "referrals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    inviter_id = Column(BigInteger, ForeignKey("users.id"), index=True)
    invitee_id = Column(BigInteger, ForeignKey("users.id"), unique=True)
    channel_reward_claimed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)

    inviter = relationship(
        "User", foreign_keys=[inviter_id], back_populates="referrals_made"
    )
    invitee = relationship(
        "User", foreign_keys=[invitee_id], back_populates="referred_by"
    )


class UserFollow(Base):
    __tablename__ = "user_follows"
    __table_args__ = (
        UniqueConstraint(
            "follower_id", "followee_id", name="uq_user_follows_follower_followee"
        ),
        Index("ix_user_follows_follower_created_at", "follower_id", "created_at"),
        Index("ix_user_follows_followee_created_at", "followee_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    follower_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    followee_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    follower = relationship(
        "User", foreign_keys=[follower_id], backref="following_links"
    )
    followee = relationship(
        "User", foreign_keys=[followee_id], backref="follower_links"
    )


class History(Base):
    __tablename__ = "history"
    __table_args__ = (
        Index("idx_history_user_favorite", "user_id", "is_favorited"),
        Index("ix_history_created_at", "created_at"),
        Index("ix_history_created_at_type", "created_at", "type"),
        Index("ix_history_created_at_user_id", "created_at", "user_id"),
        Index(
            "ix_history_source_created_at_user_id", "source", "created_at", "user_id"
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"))
    task_id = Column(String(64), nullable=True)
    type = Column(
        String(64), nullable=True
    )  # generation task type, e.g. image/video/scail2_action_transfer
    prompt = Column(Text, nullable=True)
    input_file = Column(Text, nullable=True)
    output_file = Column(Text, nullable=True)
    extra_outputs = Column(JSON, nullable=True)
    billing_resolution = Column(String(32), nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    duration = Column(Integer, nullable=True)
    requested_duration = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    is_public = Column(Boolean, default=False)
    is_visible = Column(Boolean, default=True, server_default=text("true"))
    is_favorited = Column(Boolean, default=False)
    rating = Column(Integer, default=0)
    allow_contribute = Column(Boolean, default=True)
    source = Column(String(20), server_default="bot", nullable=False)

    user = relationship("User", back_populates="history")


class CharacterReference(Base):
    __tablename__ = "character_references"
    __table_args__ = (
        CheckConstraint(
            "status in ('draft', 'pending', 'ready', 'failed', 'deleted')",
            name="ck_character_references_status",
        ),
        Index("ix_character_references_user_status", "user_id", "status"),
        Index("ix_character_references_task_id", "task_id", unique=True),
    )

    id = Column(String(36), primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(60), nullable=False)
    description = Column(String(500), nullable=True)
    source_object_key = Column(String(1024), nullable=False)
    sheet_object_key = Column(String(1024), nullable=True)
    task_id = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False, default="pending")
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )
    deleted_at = Column(DateTime, nullable=True)

    user = relationship("User", backref="character_references")
    views = relationship(
        "CharacterReferenceView",
        back_populates="character",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class CharacterReferenceView(Base):
    __tablename__ = "character_reference_views"
    __table_args__ = (
        CheckConstraint(
            "view_type in ('face_front', 'face_side', 'face_three_quarter', "
            "'body_front', 'body_side', 'body_back')",
            name="ck_character_reference_views_type",
        ),
        CheckConstraint(
            "status in ('pending', 'ready', 'failed')",
            name="ck_character_reference_views_status",
        ),
        UniqueConstraint(
            "character_id",
            "view_type",
            name="uq_character_reference_views_character_type",
        ),
        Index("ix_character_reference_views_task_id", "task_id", unique=True),
    )

    id = Column(String(36), primary_key=True)
    character_id = Column(
        String(36),
        ForeignKey("character_references.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    view_type = Column(String(32), nullable=False)
    prompt = Column(Text, nullable=False)
    object_key = Column(String(1024), nullable=True)
    task_id = Column(String(64), nullable=True)
    status = Column(String(16), nullable=False, default="pending")
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

    character = relationship("CharacterReference", back_populates="views")


class CharacterModelAsset(Base):
    __tablename__ = "character_model_assets"
    __table_args__ = (
        CheckConstraint(
            "status in ('queued', 'preparing_views', 'reconstructing', "
            "'rigging', 'ready', 'failed')",
            name="ck_character_model_assets_status",
        ),
        UniqueConstraint(
            "character_id",
            "version",
            name="uq_character_model_assets_character_version",
        ),
        Index("ix_character_model_assets_user_status", "user_id", "status"),
        Index(
            "ix_character_model_assets_character_created",
            "character_id",
            "created_at",
        ),
    )

    id = Column(String(36), primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    character_id = Column(
        String(36),
        ForeignKey("character_references.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version = Column(Integer, nullable=False)
    provider = Column(String(32), nullable=False, default="local_fixture")
    status = Column(String(24), nullable=False, default="queued")
    error_code = Column(String(64), nullable=True)
    model_object_key = Column(String(1024), nullable=True)
    render_source_object_key = Column(String(1024), nullable=True)
    thumbnail_object_key = Column(String(1024), nullable=True)
    rig_type = Column(String(32), nullable=True)
    animation_ids = Column(JSON, nullable=False, default=list)
    model_metadata = Column(JSON, nullable=False, default=dict)
    lease_owner = Column(String(128), nullable=True)
    lease_expires_at = Column(DateTime, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

    character = relationship("CharacterReference", backref="model_assets")
    input_views = relationship(
        "CharacterModelInputView",
        back_populates="asset",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class CharacterModelInputView(Base):
    __tablename__ = "character_model_input_views"
    __table_args__ = (
        CheckConstraint(
            "view_type in ('model_front', 'model_back', 'model_left', 'model_right')",
            name="ck_character_model_input_views_type",
        ),
        CheckConstraint(
            "status in ('pending', 'ready', 'failed')",
            name="ck_character_model_input_views_status",
        ),
        UniqueConstraint(
            "asset_id",
            "view_type",
            name="uq_character_model_input_views_asset_type",
        ),
    )

    id = Column(String(36), primary_key=True)
    asset_id = Column(
        String(36),
        ForeignKey("character_model_assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    view_type = Column(String(24), nullable=False)
    status = Column(String(16), nullable=False, default="pending")
    object_key = Column(String(1024), nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

    asset = relationship("CharacterModelAsset", back_populates="input_views")


class CharacterRenderJob(Base):
    __tablename__ = "character_render_jobs"
    __table_args__ = (
        CheckConstraint(
            "status in ('queued', 'rendering', 'ready', 'failed', 'cancelled')",
            name="ck_character_render_jobs_status",
        ),
        Index("ix_character_render_jobs_user_status", "user_id", "status"),
        Index("ix_character_render_jobs_status_created", "status", "created_at"),
    )

    id = Column(String(36), primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    asset_id = Column(
        String(36),
        ForeignKey("character_model_assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(String(16), nullable=False, default="queued")
    render_recipe = Column(JSON, nullable=False)
    output_object_key = Column(String(1024), nullable=True)
    error_code = Column(String(64), nullable=True)
    lease_owner = Column(String(128), nullable=True)
    lease_expires_at = Column(DateTime, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

    asset = relationship("CharacterModelAsset", backref="render_jobs")


class TemplateContribution(Base):
    __tablename__ = "template_contributions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), index=True)
    file_path = Column(String(255), nullable=False)
    file_type = Column(String(20), nullable=True)  # 'photo', 'video', 'document'
    is_reviewed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)

    user = relationship("User", backref="contributions")


class CheckinHistory(Base):
    __tablename__ = "checkin_history"
    __table_args__ = (Index("ix_checkin_history_checkin_date", "checkin_date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), index=True)
    checkin_date = Column(Date, default=func.current_date)
    created_at = Column(DateTime, default=datetime.now)

    user = relationship("User", backref="checkin_history")


class UserLog(Base):
    __tablename__ = "user_logs"
    __table_args__ = (
        Index("ix_user_logs_user_created_at_id", "user_id", "created_at", "id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    username = Column(String(100), nullable=True)
    operation_type = Column(
        String(50), nullable=False, index=True
    )  # checkin, generate, invite, etc.
    credit_change = Column(Integer, nullable=False, default=0)
    current_balance = Column(
        Integer, nullable=False
    )  # Snapshot of balance after operation
    created_at = Column(DateTime, default=datetime.now, index=True)
    extra_info = Column(Text, nullable=True)  # Stored as JSON string for compatibility

    user = relationship("User", backref="logs")


class MembershipPlan(Base):
    __tablename__ = "membership_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    identity_name = Column(String(50), nullable=False)
    price_ton = Column(DECIMAL(10, 2), nullable=False)
    price_usdt = Column(DECIMAL(10, 2), nullable=False, default=0.00)
    price_stars = Column(Integer, nullable=False, default=0)
    price_rmb = Column(DECIMAL(10, 2), nullable=False, default=0.00)
    reward_credits = Column(Integer, nullable=False)
    duration_days = Column(Integer, default=30)
    is_active = Column(Boolean, default=True)


class SiteNotice(Base):
    __tablename__ = "site_notices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False, default="", server_default=text("''"))
    content = Column(Text, nullable=False, default="")
    is_active = Column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    is_pinned = Column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    target_groups = Column(
        JSON, nullable=False, default=list, server_default=text("'[]'::json")
    )
    target_identities = Column(
        JSON, nullable=False, default=list, server_default=text("'[]'::json")
    )
    published_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(64), index=True)  # Unique payload for TON transaction
    business_order_id = Column(String(64), nullable=True, unique=True, index=True)
    internal_user_id = Column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    plan_id = Column(Integer, ForeignKey("membership_plans.id"), nullable=False)
    original_price = Column(DECIMAL(10, 2), nullable=False)
    final_price = Column(DECIMAL(10, 2), nullable=False)
    settlement_schema_version = Column(String(32), nullable=True)
    settlement_snapshot = Column(JSON, nullable=True)
    status = Column(String(20), default="PENDING")  # PENDING, SUCCESS, FAILED
    tx_hash = Column(String(100), nullable=True, unique=True)
    commission_usdt = Column(
        DECIMAL(10, 4), nullable=False, default=0, server_default=text("0")
    )
    payment_channel = Column(String(20), nullable=True, index=True)
    paid_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    user = relationship("User", backref="orders")
    plan = relationship("MembershipPlan")


class RMBPaymentReconciliationJob(Base):
    __tablename__ = "rmb_payment_reconciliation_jobs"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'processing', 'completed', 'exhausted')",
            name="ck_rmb_payment_reconciliation_jobs_status",
        ),
        Index(
            "ix_rmb_payment_reconciliation_jobs_due",
            "status",
            "next_attempt_at",
        ),
        Index(
            "ix_rmb_payment_reconciliation_jobs_lease",
            "status",
            "lease_until",
        ),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    order_id = Column(
        Integer,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status = Column(
        String(20),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )
    attempt_count = Column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    next_attempt_at = Column(DateTime, nullable=False)
    lease_token = Column(String(64), nullable=True)
    lease_until = Column(DateTime, nullable=True)
    last_error_code = Column(String(100), nullable=True)
    last_outcome = Column(String(100), nullable=True)
    last_checked_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.now,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
        server_default=func.now(),
    )


class AffiliateTransaction(Base):
    __tablename__ = "affiliate_transactions"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key", name="uq_affiliate_transactions_idempotency_key"
        ),
        Index(
            "ix_affiliate_transactions_user_status_direction",
            "user_id",
            "status",
            "direction",
        ),
        Index(
            "ix_affiliate_transactions_reference_type_reference_id",
            "reference_type",
            "reference_id",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    amount_usdt = Column(DECIMAL(10, 4), nullable=False)
    transaction_type = Column(String(50), nullable=False)
    direction = Column(String(10), nullable=False)
    reference_type = Column(String(50), nullable=False)
    reference_id = Column(String(64), nullable=False)
    idempotency_key = Column(String(128), nullable=False)
    status = Column(String(20), default="PENDING")
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    user = relationship("User", backref="affiliate_transactions")


class AffiliateRedeem(Base):
    __tablename__ = "affiliate_redeems"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_affiliate_redeems_user_idempotency_key",
        ),
        Index("ix_affiliate_redeems_user_created_at", "user_id", "created_at"),
        Index(
            "uq_affiliate_redeems_user_pending_usdt",
            "user_id",
            unique=True,
            postgresql_where=text(
                "redeem_type = 'USDT' AND status = 'PENDING'"
            ),
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    redeem_type = Column(String(50), nullable=False)
    redeem_option_key = Column(String(64), nullable=False)
    requested_amount_usdt = Column(DECIMAL(10, 4), nullable=False)
    amount_usdt = Column(DECIMAL(10, 4), nullable=False)
    credits_granted = Column(Integer, nullable=False)
    target_plan_id = Column(Integer, nullable=True)
    target_identity = Column(String(50), nullable=True)
    duration_days = Column(Integer, nullable=True)
    grant_reward_credits = Column(Boolean, nullable=True)
    settlement_reason = Column(String(50), nullable=True)
    exchange_rate_snapshot = Column(String(64), nullable=True)
    rounding_mode = Column(String(32), nullable=True)
    status = Column(String(20), nullable=False, default="SUCCESS")
    idempotency_key = Column(String(128), nullable=False)
    payout_network = Column(String(20), nullable=True)
    payout_address = Column(String(128), nullable=True)
    payout_tx_hash = Column(String(128), nullable=True, unique=True)
    admin_note = Column(String(500), nullable=True)
    rejection_reason = Column(String(500), nullable=True)
    processed_by = Column(String(255), nullable=True)
    processed_at = Column(DateTime, nullable=True)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    user = relationship("User", backref="affiliate_redeems")


class RuntimeCheckpoint(Base):
    __tablename__ = "runtime_checkpoints"

    key = Column(String(128), primary_key=True)
    value = Column(
        JSON, nullable=False, default=dict, server_default=text("'{}'::json")
    )
    updated_at = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )


class WorkerLog(Base):
    __tablename__ = "worker_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    worker_id = Column(String(100), nullable=False, index=True)
    task_id = Column(String(64), nullable=False, index=True)
    task_type = Column(String(50), nullable=True)
    status = Column(String(20), nullable=False)  # 'success', 'failed'
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    duration = Column(Integer, nullable=False)  # in seconds
    error_message = Column(Text, nullable=True)


class GalleryPost(Base):
    __tablename__ = "gallery_posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(64), index=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), index=True)  # internal_user_id

    # 元数据
    media_type = Column(String(20))  # 'image' 或 'video'
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    duration = Column(Integer, nullable=True)  # 视频时长(秒)

    # 标签 (JSON 格式存储列表)
    tags = Column(Text, default="[]")

    # 统计数据
    likes_count = Column(Integer, default=0)
    dislikes_count = Column(Integer, default=0)
    applied_count = Column(Integer, default=0)
    comments_count = Column(Integer, default=0, server_default="0", nullable=False)

    # Telegram File ID 缓存（用于秒发零流量）
    telegram_file_id = Column(String(255), nullable=True)

    is_active = Column(Boolean, default=True)  # 审核/下架控制
    created_at = Column(DateTime, default=datetime.now)

    user = relationship("User", backref="gallery_posts")
    comments = relationship(
        "GalleryComment",
        back_populates="post",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    reports = relationship("GalleryReport", back_populates="post", passive_deletes=True)
    histories = relationship(
        "History",
        primaryjoin="foreign(GalleryPost.task_id) == History.task_id",
        uselist=True,
        backref="gallery_post",
    )


class UserInteraction(Base):
    __tablename__ = "user_interactions"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "post_id", "action_type", name="uix_user_post_action"
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), index=True)
    post_id = Column(Integer, ForeignKey("gallery_posts.id"), index=True)
    action_type = Column(String(20))  # 'like', 'dislike', 'apply'
    created_at = Column(DateTime, default=datetime.now)

    user = relationship("User", backref="interactions")
    post = relationship("GalleryPost", backref="interactions")


class GalleryPromptUnlock(Base):
    __tablename__ = "gallery_prompt_unlocks"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "post_id",
            name="uq_gallery_prompt_unlocks_user_post",
        ),
        Index(
            "ix_gallery_prompt_unlocks_user_created_at",
            "user_id",
            "created_at",
        ),
        Index(
            "ix_gallery_prompt_unlocks_post_created_at",
            "post_id",
            "created_at",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    post_id = Column(
        Integer, ForeignKey("gallery_posts.id"), nullable=False, index=True
    )
    author_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    cost_credits = Column(Integer, nullable=False, default=1, server_default=text("1"))
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    user = relationship("User", foreign_keys=[user_id], backref="prompt_unlocks")
    author = relationship(
        "User",
        foreign_keys=[author_id],
        backref="prompt_unlock_sales",
    )
    post = relationship("GalleryPost", backref="prompt_unlocks")


class GalleryComment(Base):
    __tablename__ = "gallery_comments"
    __table_args__ = (
        Index("ix_gallery_comments_post_created_at", "post_id", "created_at"),
        Index(
            "ix_gallery_comments_active_post_created_at",
            "post_id",
            "created_at",
            postgresql_where=text("is_active = true"),
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(
        Integer, ForeignKey("gallery_posts.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(BigInteger, ForeignKey("users.id"), index=True, nullable=False)
    content = Column(String(500), nullable=False)  # 限制评论长度
    is_active = Column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )  # 软删除与审核控制
    created_at = Column(
        DateTime, default=datetime.now, server_default=func.now(), nullable=False
    )

    user = relationship("User")
    post = relationship("GalleryPost", back_populates="comments")


class GalleryReport(Base):
    __tablename__ = "gallery_reports"
    __table_args__ = (
        UniqueConstraint(
            "reporter_user_id",
            "post_id",
            name="uq_gallery_reports_reporter_post",
        ),
        CheckConstraint(
            "reason in ('children', 'gore', 'gross', 'other')",
            name="ck_gallery_reports_reason",
        ),
        CheckConstraint(
            "status in ('pending', 'resolved')",
            name="ck_gallery_reports_status",
        ),
        Index("ix_gallery_reports_status_created_at", "status", "created_at"),
        Index("ix_gallery_reports_post_created_at", "post_id", "created_at"),
        Index("ix_gallery_reports_reason_created_at", "reason", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(
        Integer,
        ForeignKey("gallery_posts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reporter_user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    post_author_user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    post_task_id = Column(String(64), nullable=True, index=True)
    reason = Column(String(20), nullable=False)
    status = Column(
        String(20),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )
    created_at = Column(
        DateTime, default=datetime.now, server_default=func.now(), nullable=False
    )
    resolved_at = Column(DateTime, nullable=True)
    resolution_action = Column(String(32), nullable=True)

    post = relationship("GalleryPost", back_populates="reports")
    reporter = relationship("User", foreign_keys=[reporter_user_id])
    post_author = relationship("User", foreign_keys=[post_author_user_id])
