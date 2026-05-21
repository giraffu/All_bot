from collections.abc import Awaitable, Callable
from logging import Logger

from fastapi import APIRouter

from src.core.media_paths import get_media_type_from_history
from src.core.video_billing import infer_billing_resolution_from_dimensions
from src.web_api.schemas.gallery_schema import ApplyContextResponse

router = APIRouter()


def _pick_first_non_none(*values):
    for value in values:
        if value is not None:
            return value
    return None


def build_apply_context_response(
    *,
    post_id: int,
    source_post_id: int | None,
    billing_resolution: str | None,
    requested_duration: int | None,
    task_id: str,
    media_type: str,
    prompt: str | None,
    lora_name: str | None,
    input_file: str | None,
    input_file_url: str | None,
    width: int | None,
    height: int | None,
    duration: int | None,
    task_type: str,
) -> ApplyContextResponse:
    return ApplyContextResponse(
        post_id=post_id,
        source_post_id=source_post_id,
        billing_resolution=billing_resolution,
        requested_duration=requested_duration,
        task_id=task_id,
        media_type=media_type,
        prompt=prompt,
        lora_name=lora_name,
        input_file=input_file,
        input_file_url=input_file_url,
        width=width,
        height=height,
        duration=duration,
        task_type=task_type,
    )


def resolve_apply_context_media_metadata(
    *,
    task_type: str | None,
    primary_media_type: str | None = None,
    primary_width: int | None = None,
    primary_height: int | None = None,
    primary_duration: int | None = None,
    fallback_width: int | None = None,
    fallback_height: int | None = None,
    fallback_duration: int | None = None,
) -> tuple[str, int | None, int | None, int | None]:
    media_type = primary_media_type or get_media_type_from_history(task_type)
    width = _pick_first_non_none(primary_width, fallback_width)
    height = _pick_first_non_none(primary_height, fallback_height)
    duration = _pick_first_non_none(primary_duration, fallback_duration)
    return media_type, width, height, duration


async def probe_apply_context_media_metadata(
    *,
    output_file: str | None,
    media_type: str,
    width: int | None,
    height: int | None,
    duration: int | None,
    billing_resolution: str | None,
    task_type: str | None,
    task_id: str,
    probe_media_metadata: Callable[
        [str, str], Awaitable[tuple[int | None, int | None, int | None]]
    ],
    logger: Logger | None = None,
) -> tuple[int | None, int | None, int | None, str | None]:
    needs_probe = (
        output_file
        and (width is None or height is None or (media_type == "video" and duration is None))
    )
    if not needs_probe:
        return width, height, duration, billing_resolution

    try:
        probed_width, probed_height, probed_duration = await probe_media_metadata(
            output_file, media_type
        )
        width = probed_width if probed_width is not None else width
        height = probed_height if probed_height is not None else height
        duration = probed_duration if probed_duration is not None else duration
        if billing_resolution is None:
            billing_resolution = infer_billing_resolution_from_dimensions(
                width, height, task_type
            )
    except Exception as exc:
        if logger is not None:
            logger.warning(
                "Failed to probe media metadata for task %s: %s",
                task_id,
                exc,
            )

    return width, height, duration, billing_resolution
