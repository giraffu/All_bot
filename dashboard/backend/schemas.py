from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List, Dict, Any

class UpdateCreditsRequest(BaseModel):
    credits: int
    checkin_count: Optional[int] = None

class UpdateIdentityRequest(BaseModel):
    identity: str
    expire_at: Optional[datetime] = None
    convert: bool = True

class AdminGiftRequest(BaseModel):
    plan_id: int
    note: Optional[str] = "后台手动赠送"

class MembershipPlanCreate(BaseModel):
    name: str
    identity_name: str
    reward_credits: int
    duration_days: int
    price_ton: float
    price_stars: int
    price_rmb: float = 0.00
    is_active: bool = True

class MembershipPlanUpdate(BaseModel):
    name: Optional[str] = None
    identity_name: Optional[str] = None
    reward_credits: Optional[int] = None
    duration_days: Optional[int] = None
    price_ton: Optional[float] = None
    price_stars: Optional[int] = None
    price_rmb: Optional[float] = None
    is_active: Optional[bool] = None

class MembershipPlanResponse(BaseModel):
    id: int
    name: str
    identity_name: str
    reward_credits: int
    duration_days: int
    price_ton: float
    price_stars: int
    price_rmb: float
    is_active: bool

    class Config:
        from_attributes = True

class OrderResponse(BaseModel):
    id: int
    order_id: str
    telegram_id: int
    plan_id: int
    original_price: float
    final_price: float
    status: str
    tx_hash: Optional[str]
    created_at: datetime
    username: Optional[str] = None
    plan_name: Optional[str] = None

    class Config:
        from_attributes = True

class OrderListResponse(BaseModel):
    items: List[OrderResponse]
    total: int

class HistoryResponse(BaseModel):
    id: int
    user_id: int
    task_id: Optional[str] = None
    type: str
    input_file: Optional[str] = None
    output_file: Optional[str] = None
    prompt: Optional[str] = None
    created_at: datetime
    rating: Optional[int] = None
    is_public: bool = False
    username: Optional[str] = None
    full_name: Optional[str] = None
    input_file_url: Optional[str] = None
    output_file_url: Optional[str] = None

    class Config:
        from_attributes = True

class HistoryListResponse(BaseModel):
    items: List[HistoryResponse]
    total: int

class TemplateContributionResponse(BaseModel):
    id: int
    user_id: int
    username: str
    full_name: str
    file_path: str
    file_type: str
    is_reviewed: bool
    created_at: datetime
    preview_url: Optional[str] = None

class LogResponse(BaseModel):
    id: int
    user_id: int
    username: Optional[str]
    operation_type: str
    credit_change: int
    current_balance: int
    created_at: str
    extra_info: Dict[str, Any]

class LogListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    items: List[LogResponse]

class OrderRefundRequest(BaseModel):
    task_id: str
