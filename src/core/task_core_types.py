from dataclasses import dataclass, field
from typing import Any, Tuple

from src.core.video_billing import (
    normalize_requested_billing_resolution,
    normalize_requested_duration_seconds,
)
from src.logger import UserLogger


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
    user_logger: UserLogger
    prompt: str
    saved_inputs: list[str]
    metadata: dict[str, Any]
    allow_contribute: bool
    final_priority: int
    video_request: VideoTaskRequest = field(default_factory=VideoTaskRequest)

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


class CoreDomainError(Exception):
    pass


class InsufficientCreditsError(CoreDomainError):
    pass


class ConcurrencyLimitError(CoreDomainError):
    pass


def normalize_terminal_status(status: str | None) -> str | None:
    if status == "success":
        return "done"
    if status == "failed":
        return "error"
    return status


def infer_requested_output_metadata(
    inputs: dict,
) -> Tuple[int | None, int | None, int | None]:
    output_width = None
    output_height = None
    output_duration = None

    resolution = inputs.get("resolution")
    if resolution is not None:
        res_text = str(resolution).replace("p", "")
        if "x" in res_text:
            try:
                width_text, height_text = res_text.split("x", 1)
                output_width = int(width_text)
                output_height = int(height_text)
            except ValueError:
                output_width = None
                output_height = None
        else:
            try:
                output_width = int(res_text)
            except ValueError:
                output_width = None

    duration_value = inputs.get("duration")
    if duration_value is not None:
        try:
            output_duration = int(str(duration_value).replace("s", ""))
        except ValueError:
            output_duration = None

    return output_width, output_height, output_duration


def infer_requested_billing_resolution(inputs: dict, task_type: str) -> str | None:
    return normalize_requested_billing_resolution(inputs.get("resolution"), task_type)


def parse_resolution_edge(resolution: object) -> int:
    res_str = str(resolution or "512p").replace("p", "")
    if "x" in res_str:
        try:
            width, height = map(int, res_str.split("x", 1))
            return max(width, height)
        except ValueError:
            return 512
    try:
        return int(res_str)
    except ValueError:
        return 512


def parse_duration_seconds(duration: object) -> int:
    dur_str = str(duration or "5s").replace("s", "")
    try:
        return int(dur_str)
    except ValueError:
        return 5


def build_video_task_request(task_type: str, inputs: dict) -> VideoTaskRequest:
    if not task_type:
        return VideoTaskRequest()

    requested_duration = normalize_requested_duration_seconds(
        inputs.get("duration", "5s")
    )
    resolution_edge = parse_resolution_edge(inputs.get("resolution", "512p"))
    duration_seconds = parse_duration_seconds(inputs.get("duration", "5s"))

    if task_type != "ltx_video" and resolution_edge >= 1024 and duration_seconds >= 10:
        raise CoreDomainError(
            "Cannot select 1024p resolution and 10s duration simultaneously due to high resource usage."
        )

    output_width, output_height, output_duration = infer_requested_output_metadata(
        inputs
    )
    billing_resolution = infer_requested_billing_resolution(inputs, task_type)
    return VideoTaskRequest(
        requested_duration=requested_duration,
        output_width=output_width,
        output_height=output_height,
        output_duration=output_duration,
        billing_resolution=billing_resolution,
    )


TASK_BUSY_ERROR_KEYWORDS = (
    "Circuit is open",
    "All connection attempts failed",
    "Connection refused",
    "timeout",
    "ConnectError",
)


def is_task_backend_busy_error(error: Exception | str) -> bool:
    error_msg = error if isinstance(error, str) else str(error)
    error_type = "" if isinstance(error, str) else str(type(error))
    return any(keyword in error_msg for keyword in TASK_BUSY_ERROR_KEYWORDS) or (
        "CircuitBreaker" in error_type
    )


def build_failed_task_user_message(
    *,
    error: Exception,
    generic_error_prefix: str,
    refunded: bool,
    refund_suffix_mode: str = "if_refunded",
) -> str:
    error_msg = str(error)
    if is_task_backend_busy_error(error):
        user_msg = "当前服务器繁忙，请稍后再试"
    else:
        user_msg = f"{generic_error_prefix}：{error_msg}"

    if refund_suffix_mode == "always":
        user_msg += "，已退还灵石"
    elif refund_suffix_mode == "if_refunded" and refunded:
        user_msg += "，已退还灵石"
    return user_msg
