from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Boolean, ForeignKey, Text, Date, func, DECIMAL
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True)  # Telegram User ID
    username = Column(String(100), nullable=True)
    full_name = Column(String(200), nullable=True)
    credits = Column(Integer, default=20)
    temporary_ingot = Column(Integer, default=0)
    temp_credits = Column(Integer, default=0)
    last_checkin = Column(Date, nullable=True)
    is_channel_member = Column(Boolean, default=False)
    user_group = Column(String(20), default="凡人") # 凡人, 练气期, 筑基期
    current_identity = Column(String(20), default="凡人") # 凡人, 内门弟子, 核心弟子, 真传弟子
    identity_expire_at = Column(DateTime, nullable=True)
    is_first_charge = Column(Boolean, default=True)
    total_contributions = Column(Integer, default=0) # 累计贡献次数
    approved_contributions = Column(Integer, default=0) # 累计被采纳次数
    
    # Denormalized counts for performance
    referral_count = Column(Integer, default=0)
    generation_count = Column(Integer, default=0)
    checkin_count = Column(Integer, default=0)
    last_activity = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.now)
    invited_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)

    # Relationships
    inviter_user = relationship("User", remote_side=[id], backref="invited_users")
    referrals_made = relationship("Referral", foreign_keys="Referral.inviter_id", back_populates="inviter")
    referred_by = relationship("Referral", foreign_keys="Referral.invitee_id", back_populates="invitee")
    history = relationship("History", back_populates="user")

class Referral(Base):
    __tablename__ = "referrals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    inviter_id = Column(BigInteger, ForeignKey("users.id"))
    invitee_id = Column(BigInteger, ForeignKey("users.id"), unique=True)
    channel_reward_claimed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)

    inviter = relationship("User", foreign_keys=[inviter_id], back_populates="referrals_made")
    invitee = relationship("User", foreign_keys=[invitee_id], back_populates="referred_by")

class History(Base):
    __tablename__ = "history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"))
    task_id = Column(String(64), nullable=True)
    type = Column(String(20), nullable=True) # 'image', 'video', 'video_pro', 'face_swap', etc.
    prompt = Column(Text, nullable=True)
    input_file = Column(String(255), nullable=True)
    output_file = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    user = relationship("User", back_populates="history")

class TemplateContribution(Base):
    __tablename__ = "template_contributions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), index=True)
    file_path = Column(String(255), nullable=False)
    file_type = Column(String(20), nullable=True) # 'photo', 'video', 'document'
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
    operation_type = Column(String(50), nullable=False, index=True)  # checkin, generate, invite, etc.
    credit_change = Column(Integer, nullable=False, default=0)
    current_balance = Column(Integer, nullable=False)  # Snapshot of balance after operation
    created_at = Column(DateTime, default=datetime.now, index=True)
    extra_info = Column(Text, nullable=True)  # Stored as JSON string for compatibility

    user = relationship("User", backref="logs")

class MembershipPlan(Base):
    __tablename__ = "membership_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    identity_name = Column(String(50), nullable=False)
    price_ton = Column(DECIMAL(10, 2), nullable=False)
    reward_credits = Column(Integer, nullable=False)
    duration_days = Column(Integer, default=30)
    is_active = Column(Boolean, default=True)

class DiscountRule(Base):
    __tablename__ = "discount_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_type = Column(String(50), nullable=False) # e.g., FIRST_CHARGE, LEVEL_DISCOUNT
    target_level = Column(String(50), nullable=True) # e.g., 化神期
    discount_rate = Column(DECIMAL(3, 2), nullable=False) # e.g., 0.85
    is_active = Column(Boolean, default=True)

class Order(Base):
    __tablename__ = "orders"

    order_id = Column(String(64), primary_key=True) # Unique payload for TON transaction
    telegram_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    plan_id = Column(Integer, ForeignKey("membership_plans.id"), nullable=False)
    original_price = Column(DECIMAL(10, 2), nullable=False)
    final_price = Column(DECIMAL(10, 2), nullable=False)
    status = Column(String(20), default="PENDING") # PENDING, SUCCESS, FAILED
    tx_hash = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    user = relationship("User", backref="orders")
    plan = relationship("MembershipPlan")
