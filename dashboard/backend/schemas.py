from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from datetime import datetime

class UpdateCreditsRequest(BaseModel):
    credits: int
    checkin_count: Optional[int] = None

class MembershipPlanCreate(BaseModel):
    name: str
    identity_name: str
    price_ton: float
    reward_credits: int
    duration_days: int = 30
    is_active: bool = True

class MembershipPlanUpdate(BaseModel):
    name: Optional[str] = None
    identity_name: Optional[str] = None
    price_ton: Optional[float] = None
    reward_credits: Optional[int] = None
    duration_days: Optional[int] = None
    is_active: Optional[bool] = None

class MembershipPlanResponse(BaseModel):
    id: int
    name: str
    identity_name: str
    price_ton: float
    reward_credits: int
    duration_days: Optional[int] = 30
    is_active: Optional[bool] = True

    class Config:
        from_attributes = True

class OrderResponse(BaseModel):
    id: int
    order_id: str
    telegram_id: int
    plan_id: int
    original_price: Optional[float] = None
    final_price: Optional[float] = None
    status: Optional[str] = "PENDING"
    tx_hash: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    username: Optional[str] = None
    plan_name: Optional[str] = None

    class Config:
        from_attributes = True

class OrderListResponse(BaseModel):
    items: List[OrderResponse]
    total: int

class AdminGiftRequest(BaseModel):
    plan_id: int
    note: Optional[str] = "后台手动赠送"

class HistoryResponse(BaseModel):
    id: int
    user_id: int
    task_id: Optional[str]
    type: Optional[str]
    prompt: Optional[str]
    input_file: Optional[str]
    output_file: Optional[str]
    input_file_url: Optional[str] = None
    output_file_url: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class HistoryWithUserResponse(HistoryResponse):
    username: Optional[str] = None
    full_name: Optional[str] = None

class HistoryListResponse(BaseModel):
    items: List[HistoryWithUserResponse]
    total: int

class TemplateContributionResponse(BaseModel):
    id: int
    user_id: int
    username: Optional[str]
    full_name: Optional[str]
    file_path: str
    file_type: str
    is_reviewed: bool
    created_at: datetime
    preview_url: str

    class Config:
        from_attributes = True

class LogResponse(BaseModel):
    id: int
    user_id: int
    username: Optional[str] = None
    operation_type: str
    credit_change: int
    current_balance: int
    created_at: str
    extra_info: Optional[Dict[str, Any]] = None

class LogListResponse(BaseModel):
    items: List[LogResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
