from dataclasses import dataclass, replace
from typing import Any, Callable

from src.gallery_core_dependencies import (
    get_default_gallery_submission_dependencies,
    get_gallery_feed_query_func,
    get_gallery_session_factory,
)
from src.core.gallery_core_errors import (
    DuplicateInteractionError,
    GalleryCoreError,
    GalleryPostNotFoundError,
)
from src.core.gallery_interactions_core import (
    record_apply_interaction_impl,
    toggle_like_impl,
)
from src.core.gallery_submission_core import (
    ALLOWED_WEB_SUBMIT_TYPES,
    process_submit_to_gallery_result_impl,
)
# Stable facade only: keep submission/query/interaction implementations in submodules.

__all__ = [
    "ALLOWED_WEB_SUBMIT_TYPES",
    "DuplicateInteractionError",
    "GalleryCoreError",
    "GalleryPostNotFoundError",
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
    dependencies = None
    if gallery_submission_outbox is not None:
        default_dependencies = get_default_gallery_submission_dependencies()
        dependencies = replace(
            default_dependencies,
            check_gallery_submit_limit_func=gallery_submission_outbox.check_gallery_submit_limit,
            increment_gallery_submit_func=gallery_submission_outbox.increment_gallery_submit,
        )

    return await process_submit_to_gallery_result_impl(
        gallery_submit_outcome_cls=GallerySubmitOutcome,
        user_id=user_id,
        task_id=task_id,
        width=width,
        height=height,
        duration=duration,
        session_factory=session_factory,
        dependencies=dependencies,
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
    username: str = None,
    prompt_contains: str = None,
    prompt_max_length: int = None,
    author_user_id: int = None,
    session_factory: Callable[[], Any] | None = None,
    fetch_gallery_feed_page_func: Callable[..., Any] | None = None,
) -> tuple[list, int]:
    """
    Core logic to fetch paginated gallery feed.
    Returns (posts, total_count).
    """
    session_factory = session_factory or get_gallery_session_factory()
    fetch_gallery_feed_page_func = (
        fetch_gallery_feed_page_func or get_gallery_feed_query_func()
    )

    async with session_factory() as session:
        return await fetch_gallery_feed_page_func(
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
            username=username,
            prompt_contains=prompt_contains,
            prompt_max_length=prompt_max_length,
            author_user_id=author_user_id,
        )
