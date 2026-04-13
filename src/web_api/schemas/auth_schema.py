from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class TelegramLoginRequest(BaseModel):
    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str

class Token(BaseModel):
    access_token: str
    token_type: str

class InvitationRechargeStats(BaseModel):
    recharged_invitees_count: int = 0
    total_recharge_count: int = 0
    total_ton: float = 0.0
    total_rmb: float = 0.0
    total_stars: int = 0

class UserResponse(BaseModel):
    id: int
    telegram_id: Optional[int]
    username: Optional[str]
    full_name: Optional[str]
    credits: int
    user_group: str
    current_identity: str
    identity_expire_at: Optional[datetime] = None
    total_contributions: int = 0
    generation_count: int = 0
    checkin_count: int = 0
    invitation_count: int = 0
    invitation_recharge: Optional[InvitationRechargeStats] = None
    
    class Config:
        from_attributes = True
