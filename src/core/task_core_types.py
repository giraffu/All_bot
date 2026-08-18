from dataclasses import dataclass, field
from collections.abc import Awaitable
from typing import Any

from src.core.user_logger_protocol import UserLoggerProtocol


@dataclass(frozen=True, slots=True)
class VideoTaskRequest:
    requested_duration: int | None = None
    output_width: int | None = None
    output_height: int | None = None
    output_duration: int | None = None
    billing_resolution: str | None = None


@dataclass(slots=True)
class TaskSubmissionContext:
    task_type: str
    is_video_task: bool
    user_logger: UserLoggerProtocol
    prompt: str
    saved_inputs: list[str]
    metadata: dict[str, Any]
    allow_contribute: bool
    final_priority: int
    video_request: VideoTaskRequest = field(default_factory=VideoTaskRequest)
    client_type: str = "web"
    delivery_context: dict[str, Any] = field(default_factory=dict)
    user_cancel_allowed: bool = True
    concurrency_acquisition_key: str | None = None

    @property
    def log_prompt(self) -> str:
        return self.prompt

    @property
    def billing_resolution(self) -> str | None:
        return self.video_request.billing_resolution

    @property
    def output_width(self) -> int | None:
        return self.video_request.output_width

    @property
    def output_height(self) -> int | None:
        return self.video_request.output_height

    @property
    def output_duration(self) -> int | None:
        return self.video_request.output_duration

    @property
    def requested_duration(self) -> int | None:
        return self.video_request.requested_duration

    def apply_to_inputs(self, inputs: dict):
        inputs["saved_input_images"] = self.saved_inputs
        inputs["prompt"] = self.prompt

    def registry_saved_inputs(self) -> list[str]:
        metadata_saved_inputs = self.metadata.get("saved_inputs")
        if isinstance(metadata_saved_inputs, list):
            return metadata_saved_inputs
        return self.saved_inputs


@dataclass(frozen=True, slots=True)
class TaskSuccessPersistenceResult:
    media_bytes: bytes | None
    output_file: str
    width: int | None
    height: int | None
    duration: int | None
    extra_outputs: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class TaskSuccessPersistenceCommand:
    backend_task_id: str
    registry_task_id: str
    internal_user_id: int
    username: str
    prompt: str
    task_type: str
    input_images: list[str]
    allow_contribute: bool
    is_video: bool
    billing_resolution: str | None
    requested_duration: int | None
    output_width: int | None = None
    output_height: int | None = None
    output_duration: int | None = None
    result_path: str | None = None
    result_asset: dict[str, object] | None = None
    extra_outputs: dict[str, object] | None = None
    source: str = "bot"
    refresh_user_group_after_log: bool = False
    warmup_web_history: bool = False
    postprocess_plan: "TaskPersistencePostprocessPlan | None" = None


@dataclass(frozen=True, slots=True)
class TaskFinalizationResult:
    refunded: bool
    user_message: str | None = None


@dataclass(frozen=True, slots=True)
class TaskFailureFinalizationResult(TaskFinalizationResult):
    pass


@dataclass(frozen=True, slots=True)
class TaskCancellationFinalizationResult(TaskFinalizationResult):
    pass


@dataclass(frozen=True, slots=True)
class TaskTerminationFinalizationResult(TaskFinalizationResult):
    terminated: bool = True


@dataclass(frozen=True, slots=True)
class TaskFinalizationContext:
    internal_user_id: int
    username: str
    cost: int
    registry_task_id: str | None
    release_lock: bool = True


@dataclass(frozen=True, slots=True)
class TaskSubmissionExecutionResult:
    registry_task_id: str
    backend_task_id: str
    submission_context: TaskSubmissionContext


@dataclass(frozen=True, slots=True)
class TaskSubmissionSideEffectPlan:
    attach_web_monitor: bool = False
    source_post_id: int | None = None


@dataclass(frozen=True, slots=True)
class TaskSubmissionCommand:
    internal_user_id: int
    username: str
    task_type: str
    inputs: dict[str, Any]
    task_id: str
    source_post_id: int | None = None
    delivery_context: dict[str, Any] | None = None
    registry_metadata: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class TaskSubmissionPolicy:
    base_priority: int = 0
    is_template: bool = False
    client_type: str = "web"
    deduct_quota: bool = True
    check_lock: bool = True
    side_effect_plan: TaskSubmissionSideEffectPlan | None = None
    cost_override: int | None = None
    user_cancel_allowed: bool = True
    concurrency_idempotency_key: str | None = None
    debit_idempotency_key: str | None = None
    allow_contribute_override: bool | None = None
    prepare_timeout_seconds: float | None = None
    debit_timeout_seconds: float | None = None
    dispatch_timeout_seconds: float | None = None
    refund_idempotency_key: str | None = None
    refund_task_type: str | None = None
    release_idempotency_key: str | None = None


class SubmissionJournal:
    """Application seam for durable submission state owned by each entrypoint."""

    async def before_debit(self, **_event: Any) -> None:
        return None

    async def after_debit(self, **_event: Any) -> None:
        return None

    async def before_dispatch(self, **_event: Any) -> None:
        return None

    def should_compensate(self, _error: Exception) -> bool | Awaitable[bool]:
        return True

    async def before_compensation(self, **_event: Any) -> None:
        return None


@dataclass(frozen=True, slots=True)
class TaskPersistencePostprocessPlan:
    source: str = "bot"
    record_history: bool = True
    refresh_user_group_after_log: bool = False
    warmup_web_history: bool = False


class CoreDomainError(Exception):
    pass


class DispatchRejectedError(CoreDomainError):
    """Central definitively rejected a dispatch request."""


class DispatchOutcomeUnknownError(CoreDomainError):
    """Central may have accepted the deterministic task before the error."""


class SubmissionReconciliationPending(CoreDomainError):
    """A durable submission intent must be reconciled instead of compensated."""

    def __init__(self, *, registry_task_id: str, cost: int):
        super().__init__(
            "任务已进入派发确认阶段，系统不会重复派发或自动退款，请稍后重试"
        )
        self.registry_task_id = registry_task_id
        self.cost = int(cost)


class InsufficientCreditsError(CoreDomainError):
    pass


class ConcurrencyLimitError(CoreDomainError):
    pass


class QueueCapacityError(ConcurrencyLimitError):
    """The target worker pool rejected a low-tier submission for capacity."""

    pass
