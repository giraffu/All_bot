from fastapi import HTTPException

from src.database.core import AsyncSessionLocal
from src.web_api.common.utils import call_with_optional_db
from src.web_api.common.utils import (
    build_history_apply_context_response,
    build_storage_input_file_url,
)
from src.web_api.services.apply_context_service import (
    resolve_history_template_apply_disabled_reason,
)
from src.web_api.services.gallery_response_builder import build_gallery_post_responses
from src.web_api.schemas.gallery_schema import ApplyContextResponse, PaginatedGalleryResponse
from src.web_api.services.gallery_query_service import (
    fetch_gallery_apply_context_entities,
    fetch_my_favorite_posts_page,
    fetch_my_gallery_posts_page,
    fetch_my_prompt_unlocked_posts_page,
)
from src.web_api.services.gallery_service_support import (
    default_should_return_gallery_apply_input_file,
)


def _build_paginated_gallery_response(
    *,
    items,
    total: int,
    page: int,
    size: int,
) -> PaginatedGalleryResponse:
    pages = (total + size - 1) // size
    return PaginatedGalleryResponse(
        items=items,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


async def get_my_gallery_posts_payload(
    *,
    current_user,
    db,
    page: int,
    size: int,
    task_type: str | None,
    build_post_responses_fn=build_gallery_post_responses,
) -> PaginatedGalleryResponse:
    posts, total = await fetch_my_gallery_posts_page(
        db=db,
        current_user_id=current_user.id,
        page=page,
        size=size,
        task_type=task_type,
    )
    response_items = await build_post_responses_fn(
        session=db,
        posts=posts,
        current_user=current_user,
    )
    return _build_paginated_gallery_response(
        items=response_items,
        total=total,
        page=page,
        size=size,
    )


async def get_my_gallery_posts_api_payload(
    *,
    current_user,
    page: int,
    size: int,
    task_type: str | None,
    db=None,
    session_factory=None,
    service_fn=None,
) -> PaginatedGalleryResponse:
    return await call_with_optional_db(
        db=db,
        service_fn=service_fn or get_my_gallery_posts_payload,
        session_factory=session_factory or AsyncSessionLocal,
        current_user=current_user,
        page=page,
        size=size,
        task_type=task_type,
    )


async def get_my_favorite_posts_payload(
    *,
    current_user,
    db,
    page: int,
    size: int,
    filter_type: str,
    task_type: str | None,
    build_post_responses_fn=build_gallery_post_responses,
) -> PaginatedGalleryResponse:
    posts, total = await fetch_my_favorite_posts_page(
        db=db,
        current_user_id=current_user.id,
        page=page,
        size=size,
        filter_type=filter_type,
        task_type=task_type,
    )
    response_items = await build_post_responses_fn(
        session=db,
        posts=posts,
        current_user=current_user,
    )
    return _build_paginated_gallery_response(
        items=response_items,
        total=total,
        page=page,
        size=size,
    )


async def get_my_favorite_posts_api_payload(
    *,
    current_user,
    page: int,
    size: int,
    filter_type: str,
    task_type: str | None,
    db=None,
    session_factory=None,
    service_fn=None,
) -> PaginatedGalleryResponse:
    return await call_with_optional_db(
        db=db,
        service_fn=service_fn or get_my_favorite_posts_payload,
        session_factory=session_factory or AsyncSessionLocal,
        current_user=current_user,
        page=page,
        size=size,
        filter_type=filter_type,
        task_type=task_type,
    )


async def get_my_prompt_unlocked_posts_payload(
    *,
    current_user,
    db,
    page: int,
    size: int,
    task_type: str | None,
    build_post_responses_fn=build_gallery_post_responses,
) -> PaginatedGalleryResponse:
    posts, total = await fetch_my_prompt_unlocked_posts_page(
        db=db,
        current_user_id=current_user.id,
        page=page,
        size=size,
        task_type=task_type,
    )
    response_items = await build_post_responses_fn(
        session=db,
        posts=posts,
        current_user=current_user,
    )
    return _build_paginated_gallery_response(
        items=response_items,
        total=total,
        page=page,
        size=size,
    )


async def get_my_prompt_unlocked_posts_api_payload(
    *,
    current_user,
    page: int,
    size: int,
    task_type: str | None,
    db=None,
    session_factory=None,
    service_fn=None,
) -> PaginatedGalleryResponse:
    return await call_with_optional_db(
        db=db,
        service_fn=service_fn or get_my_prompt_unlocked_posts_payload,
        session_factory=session_factory or AsyncSessionLocal,
        current_user=current_user,
        page=page,
        size=size,
        task_type=task_type,
    )


async def get_gallery_posts_payload(
    *,
    page: int,
    size: int,
    media_type: str | None,
    task_type: str | None,
    lora_model: str | None,
    sort_by: str,
    time_range: str,
    current_user,
    db,
    fetch_gallery_feed=None,
    build_post_responses_fn=build_gallery_post_responses,
) -> PaginatedGalleryResponse:
    if fetch_gallery_feed is None:
        from src.core.gallery_core import get_gallery_feed

        fetch_gallery_feed = get_gallery_feed
    posts, total = await fetch_gallery_feed(
        page=page,
        size=size,
        media_type=media_type if media_type != "all" else None,
        task_type=task_type if task_type != "all" else None,
        lora_model=lora_model,
        sort_by=sort_by,
        time_range=time_range,
        user_id=current_user.id if current_user else None,
    )
    response_items = await build_post_responses_fn(
        session=db,
        posts=posts,
        current_user=current_user,
    )
    return _build_paginated_gallery_response(
        items=response_items,
        total=total,
        page=page,
        size=size,
    )


async def get_gallery_posts_api_payload(
    *,
    page: int,
    size: int,
    media_type: str | None,
    task_type: str | None,
    lora_model: str | None,
    sort_by: str,
    time_range: str,
    current_user,
    db=None,
    session_factory=None,
    service_fn=None,
) -> PaginatedGalleryResponse:
    return await call_with_optional_db(
        db=db,
        service_fn=service_fn or get_gallery_posts_payload,
        session_factory=session_factory or AsyncSessionLocal,
        page=page,
        size=size,
        media_type=media_type,
        task_type=task_type,
        lora_model=lora_model,
        sort_by=sort_by,
        time_range=time_range,
        current_user=current_user,
    )


async def build_apply_context_payload(
    *,
    post_id: int,
    db,
    build_history_apply_context_response_fn,
    should_return_apply_input_file,
    build_input_file_url,
) -> ApplyContextResponse:
    post, history = await fetch_gallery_apply_context_entities(db=db, post_id=post_id)
    if not post or post.is_active is False:
        raise HTTPException(status_code=404, detail="帖子不存在或已失效")
    if not history:
        raise HTTPException(status_code=404, detail="未找到原任务详情")
    disabled_reason = resolve_history_template_apply_disabled_reason(history)
    if disabled_reason:
        raise HTTPException(status_code=400, detail=disabled_reason)

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


async def get_gallery_apply_context_payload(
    *,
    post_id: int,
    db,
    build_history_apply_context_response_fn=build_history_apply_context_response,
    should_return_apply_input_file=default_should_return_gallery_apply_input_file,
    build_input_file_url=build_storage_input_file_url,
) -> ApplyContextResponse:
    return await build_apply_context_payload(
        post_id=post_id,
        db=db,
        build_history_apply_context_response_fn=build_history_apply_context_response_fn,
        should_return_apply_input_file=should_return_apply_input_file,
        build_input_file_url=build_input_file_url,
    )


async def get_gallery_apply_context_api_payload(
    *,
    post_id: int,
    current_user,
    db=None,
    session_factory=None,
    service_fn=None,
) -> ApplyContextResponse:
    _ = current_user
    return await call_with_optional_db(
        db=db,
        service_fn=service_fn or get_gallery_apply_context_payload,
        session_factory=session_factory or AsyncSessionLocal,
        post_id=post_id,
    )
