from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class UpdateCreditsRequest(BaseModel):
    credits: int
    checkin_count: Optional[int] = None


class UpdateIdentityRequest(BaseModel):
    identity: str
    expire_at: Optional[datetime] = None
    convert: bool = True


class UpdateGroupRequest(BaseModel):
    user_group: str


class UpdateChannelMemberRequest(BaseModel):
    is_channel_member: bool


class AdminGiftRequest(BaseModel):
    plan_id: int
    note: Optional[str] = "后台手动赠送"


class TransferUserDataRequest(BaseModel):
    target_user_id: int = Field(..., gt=0)
    note: Optional[str] = "后台用户数据转移"


class TransferUserDataResponse(BaseModel):
    status: str = "ok"
    message: str
    source_user_id: int
    target_user_id: int
    moved_counts: Dict[str, int] = Field(default_factory=dict)
    merged_profile: Dict[str, Any] = Field(default_factory=dict)


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
    internal_user_id: int
    plan_id: int
    original_price: float
    final_price: float
    payment_channel: Optional[str] = None
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


class WorkerHistoryItemResponse(BaseModel):
    id: int
    worker_id: Optional[str] = None
    task_id: Optional[str] = None
    task_type: Optional[str] = None
    status: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration: Optional[float] = None
    error_message: Optional[str] = None


class WorkerHistoryListResponse(BaseModel):
    total: int
    page: int
    size: int
    data: List[WorkerHistoryItemResponse]


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
    worker_id: Optional[str] = None
    input_file_url: Optional[str] = None
    output_file_url: Optional[str] = None
    source: str = "bot"

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


class RefundTaskRequest(BaseModel):
    task_id: str


class SyncLockRequest(BaseModel):
    user_id: int


class GalleryPostUpdate(BaseModel):
    is_active: Optional[bool] = None
    likes_count: Optional[int] = Field(default=None, ge=0)
    dislikes_count: Optional[int] = Field(default=None, ge=0)
    applied_count: Optional[int] = Field(default=None, ge=0)
    comments_count: Optional[int] = Field(default=None, ge=0)
    tags: Optional[str] = None


class CommentUpdate(BaseModel):
    is_active: bool


class SiteNoticeUpsertRequest(BaseModel):
    title: str = Field(default="", max_length=255)
    content: str = Field(default="", max_length=5000)
    is_active: bool = False
    is_pinned: bool = False
    target_groups: List[str] = Field(default_factory=list)
    target_identities: List[str] = Field(default_factory=list)


class SiteNoticeUpdateRequest(SiteNoticeUpsertRequest):
    pass


class SiteNoticeCreateRequest(SiteNoticeUpsertRequest):
    pass


class SiteNoticeResponse(BaseModel):
    id: Optional[int] = None
    title: str = ""
    content: str = Field(default="", max_length=5000)
    is_active: bool = False
    is_pinned: bool = False
    target_groups: List[str] = Field(default_factory=list)
    target_identities: List[str] = Field(default_factory=list)
    published_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SiteNoticeListResponse(BaseModel):
    items: List[SiteNoticeResponse] = Field(default_factory=list)
