from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


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


class UpdateSubmissionBanRequest(BaseModel):
    is_submission_banned: bool
    reason: Optional[str] = None


class AdminGiftRequest(BaseModel):
    plan_id: int
    note: Optional[str] = "后台手动赠送"


class TransferUserDataRequest(BaseModel):
    target_user_id: int = Field(..., gt=0)
    note: Optional[str] = "后台用户数据转移"
    dry_run: bool = False


class TransferUserDataResponse(BaseModel):
    status: str = "ok"
    message: str
    source_user_id: int
    target_user_id: int
    moved_counts: Dict[str, int] = Field(default_factory=dict)
    merged_profile: Dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = False
    transfer_plan: Dict[str, Any] = Field(default_factory=dict)


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
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    identity_name: str
    reward_credits: int
    duration_days: int
    price_ton: float
    price_stars: int
    price_rmb: float
    is_active: bool


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    model_config = ConfigDict(from_attributes=True)

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


class RunPodScaleItem(BaseModel):
    profile: str
    count: Optional[int] = Field(default=None, ge=1)
    # Backward compatibility for old Dashboard bundles. This is now interpreted
    # as an additive count, not a destructive target desired count.
    desired_count: Optional[int] = Field(default=None, ge=1)


class RunPodScaleRequest(BaseModel):
    items: List[RunPodScaleItem] = Field(..., min_length=1, max_length=8)
    prod_max_manual_slots: Optional[int] = Field(default=None, ge=1, le=1000)
    retry_unavailable: bool = True
    max_attempts: int = Field(default=100, ge=1, le=500)
    retry_interval_seconds: int = Field(default=30, ge=5, le=3600)


class RunPodWorkerActionRequest(BaseModel):
    prod_max_manual_slots: Optional[int] = Field(default=None, ge=1, le=1000)
    reason: Optional[str] = None


class LanAioSlotActionRequest(BaseModel):
    reason: Optional[str] = None


class RunPodAutoscalerControlRequest(BaseModel):
    enabled: bool
    reason: Optional[str] = None


class RunPodAutoscalerSettingsRequest(BaseModel):
    scale_up_wait_minutes_by_profile: Dict[str, Any] = Field(default_factory=dict)
    task_duration_seconds_by_type: Dict[str, Any] = Field(default_factory=dict)
    profile_autoscaler_paused_by_profile: Dict[str, Any] = Field(default_factory=dict)
    reason: Optional[str] = None


class GalleryPostUpdate(BaseModel):
    is_active: Optional[bool] = None
    likes_count: Optional[int] = Field(default=None, ge=0)
    dislikes_count: Optional[int] = Field(default=None, ge=0)
    applied_count: Optional[int] = Field(default=None, ge=0)
    comments_count: Optional[int] = Field(default=None, ge=0)
    tags: Optional[str] = None


class GalleryUserSubmissionModerationRequest(BaseModel):
    reason: Optional[str] = None


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


class QqccBotConfigRequest(BaseModel):
    global_enabled: Optional[bool] = None
    main_buttons: Dict[str, Any] = Field(default_factory=dict)
    photo_buttons: Dict[str, Any] = Field(default_factory=dict)
    undress_methods: Dict[str, Any] = Field(default_factory=dict)
    video_buttons: Dict[str, Any] = Field(default_factory=dict)
    video_settings: Dict[str, Any] = Field(default_factory=dict)
    prompts: Dict[str, Any] = Field(default_factory=dict)


class QqccBotConfigResponse(BaseModel):
    key: str
    config: Dict[str, Any]
    updated_at: Optional[datetime] = None


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


class PaidGroupGuardConfigRequest(BaseModel):
    enabled: bool = True
    dry_run: bool = False
    block_links: bool = True
    allowed_domains: List[str] = Field(default_factory=list, max_length=1000)
    forbidden_words: List[str] = Field(default_factory=list, max_length=1000)
    exempt_user_ids: List[int] = Field(default_factory=list, max_length=1000)


class PaidGroupGuardConfigResponse(PaidGroupGuardConfigRequest):
    config_path: str
    log_path: str


class PaidGroupGuardLogItem(BaseModel):
    timestamp: str
    chat_id: int
    message_id: int
    user_id: int
    username: Optional[str] = None
    full_name: Optional[str] = None
    reason: str
    matched_value: Optional[str] = None
    text_snippet: str = ""
    action: str
    error: Optional[str] = None


class PaidGroupGuardLogListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    items: List[PaidGroupGuardLogItem] = Field(default_factory=list)
