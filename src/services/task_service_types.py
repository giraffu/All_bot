from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class BotTaskRuntimeState:
    registry_task_id: Optional[str] = None
    backend_task_id: Optional[str] = None
    task_submitted: bool = False
    actual_cost: int = 0
    terminal_state_finalized: bool = False


@dataclass(frozen=True)
class BotTaskSubmissionContext:
    runtime_state: BotTaskRuntimeState
    internal_user_id: int
    username: Optional[str]
    task_type: str
    inputs: dict
    source_post_id: Optional[int] = None
    deduct_quota: bool = True


@dataclass(frozen=True)
class BotTaskMessageSpec:
    initial_status_text: str
    submitted_status_text: Optional[str] = None
    progress_wait_text: Optional[str] = None
    completion_caption: Optional[str] = None
    missing_output_message: str = "生成完成但未获取到文件路径，已退还灵石"
    cancellation_message_template: str = "任务已撤销，预扣的 {cost} 灵石已全额退回。"


@dataclass(frozen=True)
class BotTaskCompletionContext:
    context: Any
    chat_id: int
    status_msg: Any
    runtime_state: BotTaskRuntimeState
    internal_user_id: int
    username: Optional[str]
    prompt: str
    task_type: str
    registry_task_id: str
    backend_task_id: str
    saved_input_images: list[str]
    final_info: Any
    is_video: bool
    message_spec: BotTaskMessageSpec
    user_logger: Any = None
    send_result: bool = True
    reply_markup: Any = None
    delete_status: bool = True
    caption: Optional[str] = None
    allow_contribute: bool = True
    result_meta: dict[str, Any] | None = None
    billing_resolution: Optional[str] = None
    requested_duration: Optional[int] = None
    missing_output_should_refund: bool = True


@dataclass(frozen=True)
class BotTaskRequestContext:
    context: Any
    chat_id: int
    internal_user_id: int
    username: Optional[str]
    task_type: str
    inputs: dict
    prompt: str
    is_video: bool
    update: Any = None
    status_msg_id: Optional[int] = None
    source_post_id: Optional[int] = None
    deduct_quota: bool = True


@dataclass(frozen=True)
class BotTaskPresentationContext:
    message_spec: BotTaskMessageSpec
    submitted_status_builder: Any = None
    send_result: bool = True
    reply_markup: Any = None
    result_meta: dict[str, Any] | None = None
    delete_status: bool = True
    allow_contribute: bool = True
    billing_resolution: Optional[str] = None
    prefer_edit_status: bool = False


@dataclass(frozen=True)
class BotTaskBillingContext:
    billing_resolution: Optional[str] = None
    requested_duration: Optional[int] = None
    missing_output_should_refund: bool = True


@dataclass(frozen=True)
class BotTaskFailurePolicy:
    unexpected_should_refund: Any = None
    unexpected_error_log_message: str = "Bot task failed: {error}"
    unexpected_error_prefix: str = "出错了"
    refund_suffix_mode: str = "if_refunded"


@dataclass(frozen=True)
class BotTaskCleanupPolicy:
    cleanup_paths: Optional[list[str]] = None
    cleanup_enabled: bool = True
    cleanup_files_func: Any = None


@dataclass(frozen=True)
class BotTaskFlowContext:
    runtime_state: BotTaskRuntimeState
    request: BotTaskRequestContext
    presentation: BotTaskPresentationContext
    billing: BotTaskBillingContext = field(default_factory=BotTaskBillingContext)
    failure_policy: BotTaskFailurePolicy = field(default_factory=BotTaskFailurePolicy)
    cleanup_policy: BotTaskCleanupPolicy = field(default_factory=BotTaskCleanupPolicy)


class BotTaskCancelled(Exception):
    """Dedicated bot-task cancellation signal used across monitor/finalize stages."""


@dataclass(frozen=True)
class BotFinalizationPresentationPolicy:
    message_prefix: str
    prefer_edit_status: bool = False
    fallback_to_send_message: bool = True


@dataclass(frozen=True)
class BotTaskFailureContext:
    internal_user_id: int
    username: Optional[str]
    cost: int
    should_refund: bool
    registry_task_id: Optional[str]
    release_lock: bool
    explicit_user_message: Optional[str] = None
    error: Any = None
    generic_error_prefix: Optional[str] = None
    refund_suffix_mode: str = "if_refunded"
