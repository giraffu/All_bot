from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class BotTaskRuntimeState:
    registry_task_id: Optional[str] = None
    task_submitted: bool = False
    actual_cost: int = 0
    terminal_state_finalized: bool = False


@dataclass(frozen=True)
class BotTaskSubmissionContext:
    runtime_state: BotTaskRuntimeState
    internal_user_id: int
    username: str
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
    username: str
    prompt: str
    task_type: str
    task_id: str
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
    billing_resolution: Optional[str] = None
    requested_duration: Optional[int] = None
    missing_output_should_refund: bool = True


@dataclass(frozen=True)
class BotFinalizationPresentationPolicy:
    message_prefix: str
    prefer_edit_status: bool = False
    fallback_to_send_message: bool = True


@dataclass(frozen=True)
class BotTaskFailureContext:
    internal_user_id: int
    username: str
    cost: int
    should_refund: bool
    registry_task_id: Optional[str]
    release_lock: bool
    explicit_user_message: Optional[str] = None
    error: Any = None
    generic_error_prefix: Optional[str] = None
    refund_suffix_mode: str = "if_refunded"
