from datetime import datetime

from sqlalchemy import (
    DECIMAL,
    JSON,
    BigInteger,
    Boolean,
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


class History(Base):
    __tablename__ = "history"
    __table_args__ = (Index("idx_history_user_favorite", "user_id", "is_favorited"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"))
    task_id = Column(String(64), nullable=True)
    type = Column(
        String(20), nullable=True
    )  # 'image', 'video', 'video_pro', 'face_swap', etc.
    prompt = Column(Text, nullable=True)
    input_file = Column(Text, nullable=True)
    output_file = Column(Text, nullable=True)
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

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), index=True)
    checkin_date = Column(Date, default=func.current_date)
    created_at = Column(DateTime, default=datetime.now)

    user = relationship("User", backref="checkin_history")


class UserLog(Base):
    __tablename__ = "user_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
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
    price_stars = Column(Integer, nullable=False, default=0)
    price_rmb = Column(DECIMAL(10, 2), nullable=False, default=0.00)
    reward_credits = Column(Integer, nullable=False)
    duration_days = Column(Integer, default=30)
    is_active = Column(Boolean, default=True)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(64), index=True)  # Unique payload for TON transaction
    telegram_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    plan_id = Column(Integer, ForeignKey("membership_plans.id"), nullable=False)
    original_price = Column(DECIMAL(10, 2), nullable=False)
    final_price = Column(DECIMAL(10, 2), nullable=False)
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
    comments = relationship("GalleryComment", back_populates="post", cascade="all, delete-orphan", passive_deletes=True)
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
    post_id = Column(Integer, ForeignKey("gallery_posts.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.id"), index=True, nullable=False)
    content = Column(String(500), nullable=False)  # 限制评论长度
    is_active = Column(Boolean, default=True, server_default=text("true"), nullable=False)  # 软删除与审核控制
    created_at = Column(DateTime, default=datetime.now, server_default=func.now(), nullable=False)

    user = relationship("User")
    post = relationship("GalleryPost", back_populates="comments")
