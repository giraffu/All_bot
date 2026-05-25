from typing import Tuple

from src.core.task_core_types import CoreDomainError, VideoTaskRequest
from src.core.video_billing import (
    normalize_requested_billing_resolution,
    normalize_requested_duration_seconds,
)


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
