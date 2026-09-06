import logging

from fastapi import HTTPException

from src.media_processor import extract_media_metadata_from_storage
from src.web_api.common.utils import build_storage_input_file_url, release_read_transaction
from src.web_api.schemas.gallery_schema import PaginatedGalleryResponse
from src.web_api.schemas.user_schema import PaginatedHistory
from src.web_api.services.apply_context_service import (
    build_history_apply_context_response,
    resolve_history_template_apply_disabled_reason,
)
from src.web_api.services.history_query_service import (
    build_gallery_post_map,
    fetch_active_public_gallery_task_ids,
    fetch_favorite_gallery_histories,
    fetch_gallery_posts_for_task_ids,
    fetch_history_apply_context_entities,
    fetch_recent_user_history,
    pick_preferred_gallery_post,
)
from src.web_api.services.history_response_builder import (
    build_favorite_gallery_payload,
    build_user_history_payload,
)
from src.services.user_tier_policy_service import (
    load_user_tier_policy_config,
    resolve_effective_identity,
    resolve_flashback_limit,
)

logger = logging.getLogger(__name__)

__all__ = [
    "pick_preferred_gallery_post",
    "build_gallery_post_map",
    "get_user_history_payload",
    "get_default_user_history_payload",
    "get_history_apply_context_payload",
    "get_history_apply_context_for_current_user",
    "get_my_favorites_payload",
]


async def get_user_history_payload(
    *,
    current_user,
    db,
    limit: int = 8,
) -> PaginatedHistory:
    histories, task_ids = await fetch_recent_user_history(
        db=db,
        current_user_id=current_user.id,
        limit=limit,
    )
    active_task_ids = await fetch_active_public_gallery_task_ids(
        db=db,
        task_ids=task_ids,
        current_user_id=current_user.id,
    )
    await release_read_transaction(db)
    response_items = await build_user_history_payload(
        histories=histories,
        gallery_task_ids=active_task_ids,
    )
    return PaginatedHistory(
        items=response_items,
        total=len(response_items),
        page=1,
        size=limit,
    )


async def get_default_user_history_payload(
    *,
    current_user,
    db,
) -> PaginatedHistory:
    policy = await load_user_tier_policy_config()
    limit = resolve_flashback_limit(
        policy,
        getattr(current_user, "user_group", None),
        resolve_effective_identity(current_user),
    )
    return await get_user_history_payload(
        current_user=current_user,
        db=db,
        limit=limit,
    )


async def get_history_apply_context_payload(
    *,
    task_id: str,
    user_id: int,
    db,
) -> object:
    history, gallery_post = await fetch_history_apply_context_entities(
        db=db,
        task_id=task_id,
        current_user_id=user_id,
    )
    if not history:
        raise HTTPException(status_code=404, detail="未找到原任务详情")
    disabled_reason = resolve_history_template_apply_disabled_reason(history)
    if disabled_reason:
        raise HTTPException(status_code=400, detail=disabled_reason)
    await release_read_transaction(db)

    return await build_history_apply_context_response(
        history=history,
        post_id=gallery_post.id if gallery_post else history.id,
        source_post_id=gallery_post.id if gallery_post else None,
        gallery_post=gallery_post,
        primary_width=history.width,
        primary_height=history.height,
        primary_duration=history.duration,
        fallback_width=gallery_post.width if gallery_post else None,
        fallback_height=gallery_post.height if gallery_post else None,
        fallback_duration=gallery_post.duration if gallery_post else None,
        build_input_file_url=build_storage_input_file_url,
        probe_output_file=history.output_file,
        probe_media_metadata=extract_media_metadata_from_storage,
        logger=logger,
    )


async def get_history_apply_context_for_current_user(
    *,
    task_id: str,
    current_user,
    db,
) -> object:
    return await get_history_apply_context_payload(
        task_id=task_id,
        user_id=current_user.id,
        db=db,
    )


async def get_my_favorites_payload(
    *,
    page: int,
    size: int,
    task_type: str | None,
    current_user,
    db,
) -> PaginatedGalleryResponse:
    histories, total = await fetch_favorite_gallery_histories(
        db=db,
        current_user_id=current_user.id,
        page=page,
        size=size,
        task_type=task_type,
    )
    gallery_post_map = await fetch_gallery_posts_for_task_ids(
        db=db,
        task_ids=[history.task_id for history in histories if history.task_id],
        current_user_id=current_user.id,
    )
    await release_read_transaction(db)
    response_items = await build_favorite_gallery_payload(
        histories=histories,
        gallery_post_map=gallery_post_map,
    )
    pages = (total + size - 1) // size
    return PaginatedGalleryResponse(
        items=response_items,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )
