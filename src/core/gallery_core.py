from dataclasses import dataclass
from typing import Any, Callable

from src.core.gallery_core_dependencies import get_gallery_session_factory
from src.core.gallery_core_errors import DuplicateInteractionError, GalleryCoreError
from src.core.gallery_feed_queries import fetch_gallery_feed_page
from src.core.gallery_interactions_core import (
    record_apply_interaction_impl,
    toggle_like_impl,
)
from src.core.gallery_submission_core import (
    ALLOWED_WEB_SUBMIT_TYPES,
    process_submit_to_gallery_result_impl,
)

__all__ = [
    "ALLOWED_WEB_SUBMIT_TYPES",
    "DuplicateInteractionError",
    "GalleryCoreError",
    "GallerySubmitOutcome",
    "get_gallery_feed",
    "process_submit_to_gallery_result",
    "record_apply_interaction",
    "toggle_like",
]


@dataclass(slots=True)
class GallerySubmitOutcome:
    payload: dict
    side_effects: list[tuple[object, tuple[object, ...]]]

async def process_submit_to_gallery_result(
    user_id: int,
    task_id: str,
    width: int = None,
    height: int = None,
    duration: int = None,
    session_factory: Callable[[], Any] | None = None,
    gallery_submission_outbox=None,
    check_gallery_submit_limit_func=None,
    increment_gallery_submit_func=None,
    build_gallery_submit_side_effects_func=None,
) -> GallerySubmitOutcome:
    return await process_submit_to_gallery_result_impl(
        gallery_submit_outcome_cls=GallerySubmitOutcome,
        user_id=user_id,
        task_id=task_id,
        width=width,
        height=height,
        duration=duration,
        session_factory=session_factory,
        gallery_submission_outbox=gallery_submission_outbox,
        check_gallery_submit_limit_func=check_gallery_submit_limit_func,
        increment_gallery_submit_func=increment_gallery_submit_func,
        build_gallery_submit_side_effects_func=build_gallery_submit_side_effects_func,
    )


async def toggle_like(
    user_id: int,
    post_id: int,
    action: str,
    *,
    session_factory: Callable[[], Any] | None = None,
) -> dict:
    return await toggle_like_impl(
        user_id=user_id,
        post_id=post_id,
        action=action,
        session_factory=session_factory,
    )


async def record_apply_interaction(
    user_id: int,
    post_id: int,
    *,
    session_factory: Callable[[], Any] | None = None,
):
    await record_apply_interaction_impl(
        user_id=user_id,
        post_id=post_id,
        session_factory=session_factory,
    )


async def get_gallery_feed(
    page: int = 1,
    size: int = 20,
    media_type: str = None,
    task_type: str = None,
    lora_model: str = None,
    sort_by: str = "latest",
    time_range: str = "all",
    user_id: int = None,
    category: str = None,
    is_active: bool = True,
    session_factory: Callable[[], Any] | None = None,
) -> tuple[list, int]:
    """
    Core logic to fetch paginated gallery feed.
    Returns (posts, total_count).
    """
    session_factory = session_factory or get_gallery_session_factory()

    async with session_factory() as session:
        return await fetch_gallery_feed_page(
            session=session,
            page=page,
            size=size,
            media_type=media_type,
            task_type=task_type,
            lora_model=lora_model,
            sort_by=sort_by,
            time_range=time_range,
            user_id=user_id,
            category=category,
            is_active=is_active,
        )
