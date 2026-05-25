import logging

from fastapi import HTTPException

from src.constants import MODE_VIDEO_LORA
from src.database.models import History
from src.web_api.presenters.media_presenter import (
    resolve_gallery_media_urls as presenter_resolve_gallery_media_urls,
)
from src.web_api.services.gallery_media_resolver import (
    build_gallery_media_url,
    build_gallery_thumbnail_url,
    pick_gallery_media_urls,
    resolve_gallery_post_media_urls,
)
from src.web_api.services.gallery_response_builder import (
    build_gallery_post_responses,
    build_post_responses,
    resolve_gallery_author_name,
)

logger = logging.getLogger(__name__)

__all__ = [
    "APPLY_CONTEXT_ALLOW_INPUT_REUSE_TASK_TYPES",
    "DEFAULT_GALLERY_ALLOWED_TYPE_CONFIGS",
    "build_gallery_config_payload",
    "submit_gallery_post_payload",
    "should_return_gallery_apply_input_file",
    "default_should_return_gallery_apply_input_file",
    "build_gallery_media_url",
    "build_gallery_thumbnail_url",
    "pick_gallery_media_urls",
    "presenter_resolve_gallery_media_urls",
    "resolve_gallery_post_media_urls",
    "resolve_gallery_author_name",
    "build_post_responses",
    "build_gallery_post_responses",
    "call_gallery_service_with_optional_db",
]

DEFAULT_GALLERY_ALLOWED_TYPE_CONFIGS = [
    ("i2i_pro", "task.mode_i2i_pro"),
    ("i2i_draw", "task.mode_i2i_draw"),
    ("edit", "task.mode_edit"),
    ("img2img_lora", "task.mode_img2img_lora"),
    ("custom_video", "task.mode_custom_video"),
    (MODE_VIDEO_LORA, "task.mode_video_lora"),
    ("ltx_video", "task.mode_ltx_video"),
]

APPLY_CONTEXT_ALLOW_INPUT_REUSE_TASK_TYPES = {
    "face_swap",
    "face_video",
}


def build_gallery_config_payload(
    *,
    allowed_type_configs: list[tuple[str, str]],
    mode_name_map: dict[str, str],
    video_lora_models: dict[str, str],
    image_lora_models: dict[str, str],
) -> dict[str, list[dict[str, str]]]:
    return {
        "allowed_types": [
            {"id": task_type, "name": mode_name_map.get(task_type, fallback_name)}
            for task_type, fallback_name in allowed_type_configs
        ],
        "lora_models": [{"id": key, "name": value} for key, value in video_lora_models.items()],
        "img2img_lora_models": [
            {"id": key, "name": value}
            for key, value in image_lora_models.items()
            if key
        ],
    }


async def submit_gallery_post_payload(
    *,
    task_id: str,
    schedule_background_task=None,
    request,
    current_user,
    process_submit_to_gallery_fn=None,
) -> dict:
    try:
        if process_submit_to_gallery_fn is None:
            from src.core.gallery_core import process_submit_to_gallery_result

            process_submit_to_gallery_fn = process_submit_to_gallery_result
        width = request.width if request else None
        height = request.height if request else None
        duration = request.duration if request else None
        outcome = await process_submit_to_gallery_fn(
            user_id=current_user.id,
            task_id=task_id,
            width=width,
            height=height,
            duration=duration,
        )
        if isinstance(outcome, dict):
            return outcome
        if schedule_background_task is not None:
            for effect_func, effect_args in outcome.side_effects:
                schedule_background_task(effect_func, *effect_args)
        return outcome.payload
    except HTTPException:
        raise
    except Exception as exc:
        if exc.__class__.__name__ == "GalleryCoreError":
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        logger.error(
            "Unexpected error submitting to gallery for user_id=%s task_id=%s: %s",
            getattr(current_user, "id", None),
            task_id,
            exc,
        )
        raise HTTPException(status_code=500, detail="Internal server error") from exc


def should_return_gallery_apply_input_file(
    history: History,
    *,
    allow_input_reuse_task_types: set[str],
) -> bool:
    return (history.type or "") in allow_input_reuse_task_types


def default_should_return_gallery_apply_input_file(history: History) -> bool:
    return should_return_gallery_apply_input_file(
        history,
        allow_input_reuse_task_types=APPLY_CONTEXT_ALLOW_INPUT_REUSE_TASK_TYPES,
    )
