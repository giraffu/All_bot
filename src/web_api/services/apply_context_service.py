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
from src.domain_config.scail2_video import (
    SCAIL2_DEFAULT_NEGATIVE_PROMPT,
    is_scail2_task_type,
)
from src.lora_catalog import normalize_ltx_video_lora_items
from src.domain_config.wan22_aio_video import is_wan22_chain_history_task_type
from src.services.ltx_video_extension_service import (
    extract_ltx_history_context,
    is_ltx_video_history_task_type,
)
from src.services.gallery_apply_context_service import (
    TEMPLATE_APPLY_DISABLED_REASON_I2I_DRAW_DISABLED,
    TEMPLATE_APPLY_DISABLED_REASON_MISSING_SCAIL2_MOTION_VIDEO,
    TEMPLATE_APPLY_DISABLED_REASON_WAN22_STITCHED,
    is_history_template_apply_supported,
    resolve_history_template_apply_disabled_reason,
    resolve_reusable_apply_input_files,
    split_history_input_files,
)
from src.services.wan22_video_v2_extension_service import (
    extract_wan22_history_context,
)
from src.web_api.schemas.gallery_schema import ApplyContextResponse
from src.services.user_visible_generation_presenter import (
    present_user_prompt,
    resolve_prompt_generation_context,
)

SCAIL2_HISTORY_CONTEXT_KEY = "scail2_context"

__all__ = [
    "TEMPLATE_APPLY_DISABLED_REASON_I2I_DRAW_DISABLED",
    "TEMPLATE_APPLY_DISABLED_REASON_MISSING_SCAIL2_MOTION_VIDEO",
    "TEMPLATE_APPLY_DISABLED_REASON_WAN22_STITCHED",
    "build_apply_context_response",
    "build_history_apply_context_response",
    "is_history_template_apply_supported",
    "probe_apply_context_media_metadata",
    "resolve_apply_context_media_metadata",
    "resolve_history_billing_resolution",
    "resolve_history_template_apply_disabled_reason",
    "resolve_reusable_apply_input_files",
    "split_history_input_files",
]


def _pick_first_non_none(*values):
    for value in values:
        if value is not None:
            return value
    return None


def _coerce_positive_int(value) -> int | None:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return normalized if normalized > 0 else None


def resolve_wan22_apply_context_metadata(history: History) -> dict[str, object]:
    if not is_wan22_chain_history_task_type(history.type):
        return {}
    return extract_wan22_history_context(getattr(history, "extra_outputs", None))


def resolve_ltx_apply_context_metadata(history: History) -> dict[str, object]:
    if not is_ltx_video_history_task_type(history.type):
        return {}
    return extract_ltx_history_context(getattr(history, "extra_outputs", None))


def resolve_wan22_apply_negative_prompt(history: History) -> str | None:
    context = resolve_wan22_apply_context_metadata(history)
    negative_prompt = str(context.get("wan22_negative_prompt") or "").strip()
    return negative_prompt or None


def resolve_scail2_apply_context_metadata(history: History) -> dict[str, object]:
    if not is_scail2_task_type(history.type):
        return {}
    extra_outputs = getattr(history, "extra_outputs", None)
    if not isinstance(extra_outputs, dict):
        return {}
    context = extra_outputs.get(SCAIL2_HISTORY_CONTEXT_KEY)
    return context if isinstance(context, dict) else {}


def resolve_scail2_apply_negative_prompt(history: History) -> str | None:
    if not is_scail2_task_type(history.type):
        return None
    context = resolve_scail2_apply_context_metadata(history)
    negative_prompt = str(context.get("scail2_negative_prompt") or "").strip()
    return negative_prompt or SCAIL2_DEFAULT_NEGATIVE_PROMPT


def resolve_wan22_apply_requested_duration(history: History) -> object:
    if not is_wan22_chain_history_task_type(history.type):
        if is_scail2_task_type(history.type):
            context = resolve_scail2_apply_context_metadata(history)
            return _pick_first_non_none(
                history.requested_duration,
                context.get("scail2_duration_seconds"),
            )
        if is_ltx_video_history_task_type(history.type):
            context = resolve_ltx_apply_context_metadata(history)
            return _pick_first_non_none(
                history.requested_duration,
                context.get("ltx_duration_seconds"),
            )
        return history.requested_duration
    context = resolve_wan22_apply_context_metadata(history)
    return _pick_first_non_none(
        history.requested_duration,
        context.get("wan22_duration_seconds"),
    )


def resolve_ltx_apply_lora_items(
    *,
    history: History,
    prompt_lora_name: str | None,
    prompt_lora_strength: float | None,
) -> list[dict] | None:
    if not is_ltx_video_history_task_type(history.type):
        return None

    context = resolve_ltx_apply_context_metadata(history)
    normalized_context_items = normalize_ltx_video_lora_items(
        context.get("lora_items") if isinstance(context.get("lora_items"), list) else []
    )
    if normalized_context_items:
        return normalized_context_items

    context_lora_name = str(context.get("lora_name") or "").strip()
    if context_lora_name:
        return normalize_ltx_video_lora_items(
            [
                {
                    "name": context_lora_name,
                    "strength": context.get("lora_strength"),
                }
            ]
        ) or None

    if prompt_lora_name:
        return [
            {
                "name": prompt_lora_name,
                "strength": prompt_lora_strength or 1.0,
            }
        ]
    return None


def build_apply_context_response(
    *,
    post_id: int,
    source_post_id: int | None,
    billing_resolution: str | None,
    requested_duration: int | None,
    required_image_count: int | None,
    task_id: str,
    media_type: str,
    prompt: str | None,
    negative_prompt: str | None,
    lora_name: str | None,
    lora_strength: float | None,
    lora_items: list[dict] | None,
    prompt_model: dict | None = None,
    input_file: str | None,
    input_file_url: str | None,
    width: int | None,
    height: int | None,
    duration: int | None,
    task_type: str,
    input_files: list[str] | None = None,
    input_file_urls: list[str] | None = None,
) -> ApplyContextResponse:
    return ApplyContextResponse(
        post_id=post_id,
        source_post_id=source_post_id,
        billing_resolution=billing_resolution,
        requested_duration=requested_duration,
        required_image_count=required_image_count,
        task_id=task_id,
        media_type=media_type,
        prompt=prompt,
        prompt_model=prompt_model,
        negative_prompt=negative_prompt,
        lora_name=lora_name,
        lora_strength=lora_strength,
        lora_items=lora_items,
        input_file=input_file,
        input_file_url=input_file_url,
        input_files=input_files or [],
        input_file_urls=input_file_urls or [],
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
    wan22_context = resolve_wan22_apply_context_metadata(history)
    wan22_resolution_preset = str(
        wan22_context.get("wan22_resolution_preset") or ""
    ).strip()
    if wan22_resolution_preset:
        normalized = normalize_requested_billing_resolution(
            wan22_resolution_preset,
            history.type,
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
    input_files = resolve_reusable_apply_input_files(history) if include_input_file else []
    input_file = input_files[0] if input_files else None
    input_file_urls = [
        build_input_file_url(input_file_item) or input_file_item
        for input_file_item in input_files
        if build_input_file_url is not None
    ]
    input_file_url = input_file_urls[0] if input_file_urls else None

    prompt, requested_duration = resolve_apply_prompt_and_requested_duration(
        history.type,
        history.prompt,
        resolve_wan22_apply_requested_duration(history),
    )
    presented_prompt = present_user_prompt(
        prompt,
        extra_outputs=getattr(history, "extra_outputs", None),
    )
    prompt, lora_name, lora_strength = resolve_prompt_generation_context(
        prompt,
        extra_outputs=getattr(history, "extra_outputs", None),
    )
    prompt_model = presented_prompt.prompt_model
    negative_prompt = (
        resolve_wan22_apply_negative_prompt(history)
        or resolve_scail2_apply_negative_prompt(history)
    )
    lora_items = resolve_ltx_apply_lora_items(
        history=history,
        prompt_lora_name=lora_name,
        prompt_lora_strength=lora_strength,
    )

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
    ltx_context = resolve_ltx_apply_context_metadata(history)
    if ltx_context:
        width = _pick_first_non_none(width, _coerce_positive_int(ltx_context.get("ltx_width")))
        height = _pick_first_non_none(height, _coerce_positive_int(ltx_context.get("ltx_height")))
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
    if (
        history.type in {"custom_video", "video_lora", "wan22_video_v2"}
        and requested_duration is not None
    ):
        duration = requested_duration

    required_image_count = None
    if history.type == "free_edit_v2_5":
        required_image_count = (
            2 if len(split_history_input_files(history.input_file)) >= 2 else 1
        )

    return build_apply_context_response(
        post_id=post_id,
        source_post_id=source_post_id,
        billing_resolution=billing_resolution,
        requested_duration=requested_duration,
        required_image_count=required_image_count,
        task_id=history.task_id,
        media_type=media_type,
        prompt=prompt,
        negative_prompt=negative_prompt,
        lora_name=lora_name,
        lora_strength=lora_strength,
        lora_items=lora_items,
        prompt_model=prompt_model,
        input_file=input_file,
        input_file_url=input_file_url,
        input_files=input_files,
        input_file_urls=input_file_urls,
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
