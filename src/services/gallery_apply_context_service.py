from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy import select

from src.database.models import GalleryPost, History
from src.services.gallery_history_link import select_gallery_history_for_post
from src.domain_config.scail2_video import is_scail2_task_type
from src.domain_config.task_type_registry import apply_input_reuse_task_types
from src.domain_config.minimax_h3 import MINIMAX_H3_REF2V, MINIMAX_H3_TASK_TYPES
from src.services.minimax_h3_history_context_service import (
    is_minimax_h3_gallery_task_type,
    resolve_valid_minimax_h3_history_context,
)
from src.services.wan22_video_v2_extension_service import is_wan22_stitched_result
from src.services.minimax_h3_extension_service import is_minimax_h3_stitched_result

TEMPLATE_APPLY_DISABLED_REASON_WAN22_STITCHED = "wan22_stitched"
TEMPLATE_APPLY_DISABLED_REASON_MISSING_SCAIL2_MOTION_VIDEO = (
    "missing_scail2_motion_video"
)
TEMPLATE_APPLY_DISABLED_REASON_I2I_DRAW_DISABLED = "i2i_draw_disabled"
TEMPLATE_APPLY_DISABLED_REASON_MINIMAX_H3_CONTEXT_MISSING = "minimax_h3_context_missing"
TEMPLATE_APPLY_DISABLED_REASON_MINIMAX_H3_MODE_NOT_SUPPORTED = (
    "minimax_h3_mode_not_supported"
)
TEMPLATE_APPLY_DISABLED_REASON_MINIMAX_H3_STITCHED = "minimax_h3_stitched"
APPLY_CONTEXT_ALLOW_INPUT_REUSE_TASK_TYPES = apply_input_reuse_task_types()
_H3_REFERENCE_AUDIO_EXTENSIONS = frozenset(
    {"mp3", "wav", "m4a", "mp4", "ogg", "oga", "opus"}
)


class GalleryApplyContextError(Exception):
    def __init__(self, *, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def split_history_input_files(input_file: str | None) -> list[str]:
    if not input_file:
        return []
    return [
        item.strip() for item in str(input_file).split("|") if item and item.strip()
    ]


def resolve_reusable_apply_input_files(history: History | None) -> list[str]:
    if history is None:
        return []

    input_files = split_history_input_files(getattr(history, "input_file", None))
    if getattr(history, "type", None) == MINIMAX_H3_REF2V:
        visual_inputs = (
            input_files[:-1]
            if input_files and _is_h3_reference_audio_key(input_files[-1])
            else input_files
        )
        return visual_inputs[1:]
    if is_scail2_task_type(getattr(history, "type", None)):
        return input_files[1:2]
    return input_files


def _is_h3_reference_audio_key(value: str) -> bool:
    extension = value.rsplit(".", 1)[-1].lower() if "." in value else ""
    return extension in _H3_REFERENCE_AUDIO_EXTENSIONS


def resolve_history_reference_audio(history: History | None) -> str | None:
    if history is None or getattr(history, "type", None) != MINIMAX_H3_REF2V:
        return None
    context = resolve_valid_minimax_h3_history_context(
        task_type=history.type,
        extra_outputs=getattr(history, "extra_outputs", None),
    )
    reference_audio = str(context.get("reference_audio") or "").strip()
    if reference_audio:
        return reference_audio
    input_files = split_history_input_files(getattr(history, "input_file", None))
    if input_files and _is_h3_reference_audio_key(input_files[-1]):
        return input_files[-1]
    return None


def resolve_history_template_apply_disabled_reason(
    history: History | None,
) -> str | None:
    task_type = str(getattr(history, "type", None) or "") if history else ""
    if task_type in MINIMAX_H3_TASK_TYPES:
        if history and is_minimax_h3_stitched_result(
            getattr(history, "extra_outputs", None)
        ):
            return TEMPLATE_APPLY_DISABLED_REASON_MINIMAX_H3_STITCHED
        if not is_minimax_h3_gallery_task_type(task_type):
            return TEMPLATE_APPLY_DISABLED_REASON_MINIMAX_H3_MODE_NOT_SUPPORTED
        if not resolve_valid_minimax_h3_history_context(
            task_type=task_type,
            extra_outputs=getattr(history, "extra_outputs", None),
        ):
            return TEMPLATE_APPLY_DISABLED_REASON_MINIMAX_H3_CONTEXT_MISSING
    if history and getattr(history, "type", None) == "i2i_draw":
        return TEMPLATE_APPLY_DISABLED_REASON_I2I_DRAW_DISABLED
    if history and is_wan22_stitched_result(getattr(history, "extra_outputs", None)):
        return TEMPLATE_APPLY_DISABLED_REASON_WAN22_STITCHED
    if history and is_scail2_task_type(getattr(history, "type", None)):
        if not resolve_reusable_apply_input_files(history):
            return TEMPLATE_APPLY_DISABLED_REASON_MISSING_SCAIL2_MOTION_VIDEO
    return None


def is_history_template_apply_supported(history: History | None) -> bool:
    return resolve_history_template_apply_disabled_reason(history) is None


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


async def fetch_gallery_apply_context_entities(*, db, post_id: int):
    post = (
        await db.execute(select(GalleryPost).where(GalleryPost.id == post_id))
    ).scalar_one_or_none()
    if not post:
        return None, None

    history = (
        (await db.execute(select_gallery_history_for_post(post)))
        .scalars()
        .first()
    )
    return post, history


async def build_gallery_apply_context_payload(
    *,
    post_id: int,
    db,
    build_history_apply_context_response_fn: Callable[..., Awaitable[object]],
    should_return_apply_input_file: Callable[[History], bool],
    build_input_file_url: Callable[[str | None], str | None],
    release_read_transaction_fn: Callable[[object], Awaitable[None]] | None = None,
    current_user_id: int | None = None,
    post: GalleryPost | None = None,
    history: History | None = None,
) -> object:
    if post is None and history is None:
        post, history = await fetch_gallery_apply_context_entities(
            db=db, post_id=post_id
        )

    if not post or post.is_active is False:
        raise GalleryApplyContextError(status_code=404, detail="帖子不存在或已失效")
    if not history:
        raise GalleryApplyContextError(status_code=404, detail="未找到原任务详情")
    disabled_reason = resolve_history_template_apply_disabled_reason(history)
    if disabled_reason:
        raise GalleryApplyContextError(status_code=400, detail=disabled_reason)
    if release_read_transaction_fn is not None:
        await release_read_transaction_fn(db)

    return await build_history_apply_context_response_fn(
        history=history,
        post_id=post.id,
        source_post_id=post.id,
        gallery_post=post,
        primary_media_type=post.media_type,
        primary_width=post.width,
        primary_height=post.height,
        primary_duration=post.duration,
        fallback_width=history.width,
        fallback_height=history.height,
        fallback_duration=history.duration,
        include_input_file=should_return_apply_input_file(history),
        build_input_file_url=build_input_file_url,
    )
