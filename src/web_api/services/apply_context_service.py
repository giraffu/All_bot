from collections.abc import Awaitable, Callable
from logging import Logger

from src.core.media_paths import get_media_type_from_history
from src.core.video_billing import (
    infer_billing_resolution_from_dimensions,
    is_video_billing_task_type,
    normalize_requested_billing_resolution,
    resolve_apply_prompt_and_requested_duration,
    resolve_legacy_requested_duration,
)
from src.database.models import GalleryPost, History
from src.lora_mapping import extract_prompt_lora_context
from src.web_api.schemas.gallery_schema import ApplyContextResponse


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
    lora_strength: float | None,
    lora_items: list[dict] | None,
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
        lora_strength=lora_strength,
        lora_items=lora_items,
        input_file=input_file,
        input_file_url=input_file_url,
        width=width,
        height=height,
        duration=duration,
        task_type=task_type,
    )


def resolve_history_billing_resolution(
    history: History,
    *,
    width: int | None = None,
    height: int | None = None,
    gallery_post: GalleryPost | None = None,
) -> str | None:
    if not is_video_billing_task_type(history.type):
        return None
    if history.billing_resolution:
        normalized = normalize_requested_billing_resolution(
            history.billing_resolution, history.type
        )
        if normalized is not None:
            return normalized
    return infer_billing_resolution_from_dimensions(
        width if width is not None else history.width,
        height if height is not None else history.height,
        history.type,
    ) or (
        infer_billing_resolution_from_dimensions(
            getattr(gallery_post, "width", None),
            getattr(gallery_post, "height", None),
            history.type,
        )
        if gallery_post
        else None
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


async def build_history_apply_context_response(
    *,
    history: History,
    post_id: int,
    source_post_id: int | None,
    gallery_post: GalleryPost | None = None,
    primary_media_type: str | None = None,
    primary_width: int | None = None,
    primary_height: int | None = None,
    primary_duration: int | None = None,
    fallback_width: int | None = None,
    fallback_height: int | None = None,
    fallback_duration: int | None = None,
    include_input_file: bool = True,
    build_input_file_url: Callable[[str], str] | None = None,
    probe_output_file: str | None = None,
    probe_media_metadata: Callable[
        [str, str], Awaitable[tuple[int | None, int | None, int | None]]
    ]
    | None = None,
    logger: Logger | None = None,
) -> ApplyContextResponse:
    input_file = history.input_file if include_input_file and history.input_file else None
    input_file_url = (
        build_input_file_url(input_file)
        if input_file and build_input_file_url is not None
        else None
    )

    prompt, requested_duration = resolve_apply_prompt_and_requested_duration(
        history.type,
        history.prompt,
        history.requested_duration,
    )
    prompt, lora_name, lora_strength = extract_prompt_lora_context(prompt)
    lora_items = None
    if history.type == "ltx_video" and lora_name:
        lora_items = [{"name": lora_name, "strength": lora_strength or 1.0}]

    media_type, width, height, duration = resolve_apply_context_media_metadata(
        task_type=history.type,
        primary_media_type=primary_media_type,
        primary_width=primary_width,
        primary_height=primary_height,
        primary_duration=primary_duration,
        fallback_width=fallback_width,
        fallback_height=fallback_height,
        fallback_duration=fallback_duration,
    )
    billing_resolution = resolve_history_billing_resolution(
        history,
        width=width,
        height=height,
        gallery_post=gallery_post,
    )

    if probe_media_metadata is not None:
        width, height, duration, billing_resolution = (
            await probe_apply_context_media_metadata(
                output_file=probe_output_file,
                media_type=media_type,
                width=width,
                height=height,
                duration=duration,
                billing_resolution=billing_resolution,
                task_type=history.type,
                task_id=history.task_id,
                probe_media_metadata=probe_media_metadata,
                logger=logger,
            )
        )

    requested_duration = resolve_legacy_requested_duration(
        task_type=history.type,
        requested_duration=requested_duration,
        duration=duration,
    )

    return build_apply_context_response(
        post_id=post_id,
        source_post_id=source_post_id,
        billing_resolution=billing_resolution,
        requested_duration=requested_duration,
        task_id=history.task_id,
        media_type=media_type,
        prompt=prompt,
        lora_name=lora_name,
        lora_strength=lora_strength,
        lora_items=lora_items,
        input_file=input_file,
        input_file_url=input_file_url,
        width=width,
        height=height,
        duration=duration,
        task_type=history.type,
    )


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
    needs_probe = output_file and (
        width is None or height is None or (media_type == "video" and duration is None)
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
