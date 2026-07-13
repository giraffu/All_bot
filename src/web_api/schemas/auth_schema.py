from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field, field_validator
import re


class UserLoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=20, description="道号 (账号)")
    password: str = Field(..., min_length=6, max_length=128, description="密咒 (密码)")


class UserBindPasswordRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=20, description="道号 (账号)")
    password: str = Field(..., min_length=6, max_length=128, description="密咒 (密码)")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        if not re.match(r"^[a-zA-Z0-9_\-\u4e00-\u9fa5]+$", v):
            raise ValueError("道号只能包含中英文、数字、下划线和连字符")
        return v


class TelegramLoginRequest(BaseModel):
    id: Optional[int] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: Optional[int] = None
    hash: Optional[str] = None

    # WebApp initData 字段
    initData: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str


class InvitationRechargeStats(BaseModel):
    recharged_invitees_count: int = 0
    total_recharge_count: int = 0
    total_ton: float = 0.0
    total_rmb: float = 0.0
    total_stars: int = 0
    commission_usdt: float = 0.0
    total_commission_usdt: float = 0.0
    spent_commission_usdt: float = 0.0
    available_balance_usdt: float = 0.0


class BreakthroughConditionDTO(BaseModel):
    type: str
    target: int
    current: int
    done: bool


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: Optional[int] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    language_code: Optional[str] = None
    credits: int
    user_group: str
    current_identity: str
    identity_expire_at: Optional[datetime] = None
    priority: int = 0
    generation_count: int = 0
    checkin_count: int = 0
    invitation_count: int = 0
    invitation_recharge: Optional[InvitationRechargeStats] = None
    breakthrough_conditions: List[BreakthroughConditionDTO] = []
    is_unlocked: bool = False
