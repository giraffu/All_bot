from dataclasses import dataclass, field
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
class TaskPersistencePostprocessPlan:
    source: str = "bot"
    record_history: bool = True
    refresh_user_group_after_log: bool = False
    warmup_web_history: bool = False


class CoreDomainError(Exception):
    pass


class InsufficientCreditsError(CoreDomainError):
    pass


class ConcurrencyLimitError(CoreDomainError):
    pass


class QueueCapacityError(ConcurrencyLimitError):
    """The target worker pool rejected a low-tier submission for capacity."""

    pass
