from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy import select

from src.database.models import GalleryPost, History
from src.domain_config.scail2_video import is_scail2_task_type
from src.domain_config.task_type_registry import apply_input_reuse_task_types
from src.services.wan22_video_v2_extension_service import is_wan22_stitched_result

TEMPLATE_APPLY_DISABLED_REASON_WAN22_STITCHED = "wan22_stitched"
TEMPLATE_APPLY_DISABLED_REASON_MISSING_SCAIL2_MOTION_VIDEO = (
    "missing_scail2_motion_video"
)
TEMPLATE_APPLY_DISABLED_REASON_I2I_DRAW_DISABLED = "i2i_draw_disabled"
APPLY_CONTEXT_ALLOW_INPUT_REUSE_TASK_TYPES = apply_input_reuse_task_types()


class GalleryApplyContextError(Exception):
    def __init__(self, *, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def split_history_input_files(input_file: str | None) -> list[str]:
    if not input_file:
        return []
    return [
        item.strip()
        for item in str(input_file).split("|")
        if item and item.strip()
    ]


def resolve_reusable_apply_input_files(history: History | None) -> list[str]:
    if history is None:
        return []

    input_files = split_history_input_files(getattr(history, "input_file", None))
    if is_scail2_task_type(getattr(history, "type", None)):
        return input_files[1:2]
    return input_files


def resolve_history_template_apply_disabled_reason(
    history: History | None,
) -> str | None:
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
        await db.execute(select(History).where(History.task_id == post.task_id))
    ).scalars().first()
    return post, history


async def build_gallery_apply_context_payload(
    *,
    post_id: int,
    db,
    build_history_apply_context_response_fn: Callable[..., Awaitable[object]],
    should_return_apply_input_file: Callable[[History], bool],
    build_input_file_url: Callable[[str | None], str | None],
    release_read_transaction_fn: Callable[[object], Awaitable[None]] | None = None,
    post: GalleryPost | None = None,
    history: History | None = None,
) -> object:
    if post is None and history is None:
        post, history = await fetch_gallery_apply_context_entities(db=db, post_id=post_id)

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
