import logging
import asyncio
import json

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy import delete, desc, func, select, update
from sqlalchemy.orm import joinedload

from src.core.media_paths import (
    build_history_r2_media_key,
    build_history_r2_thumbnail_key,
    build_legacy_r2_key,
    build_thumbnail_object_name,
    get_media_type_from_history,
    resolve_storage_object,
)
from src.database.core import AsyncSessionLocal
from src.database.models import GalleryComment, GalleryPost, History, User, UserInteraction
from src.lora_mapping import translate_tags
from src.services.storage import storage
from src.web_api.presenters.media_presenter import (
    resolve_gallery_media_urls as presenter_resolve_gallery_media_urls,
)
from src.web_api.presenters.media_presenter import resolve_media_url, resolve_thumbnail_url
from src.web_api.routers.utils import (
    call_with_optional_db,
    build_history_apply_context_response,
    build_storage_input_file_url,
    resolve_history_billing_resolution,
)
from src.web_api.schemas.gallery_schema import (
    ApplyContextResponse,
    CommentUserResponse,
    GalleryCommentResponse,
    GalleryPostResponse,
    PaginatedCommentResponse,
    PaginatedGalleryResponse,
)

logger = logging.getLogger(__name__)

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
    background_tasks,
    request,
    current_user,
    process_submit_to_gallery_fn=None,
) -> dict:
    try:
        if process_submit_to_gallery_fn is None:
            from src.core.gallery_core import process_submit_to_gallery

            process_submit_to_gallery_fn = process_submit_to_gallery
        width = request.width if request else None
        height = request.height if request else None
        duration = request.duration if request else None
        return await process_submit_to_gallery_fn(
            current_user.id,
            task_id,
            background_tasks,
            width,
            height,
            duration,
        )
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


async def build_gallery_media_url(
    output_file: str | None,
    *,
    task_id: str | None,
    resolve_media_url_fn,
) -> str:
    return await resolve_media_url_fn(
        output_file,
        task_id=task_id,
        fallback_to_storage_path=True,
    )


async def build_gallery_thumbnail_url(
    output_file: str | None,
    media_type: str,
    *,
    task_id: str | None,
    resolve_thumbnail_url_fn,
    resolve_storage_object_fn,
    build_thumbnail_object_name_fn,
    get_presigned_url_fn,
) -> str:
    thumbnail_url = await resolve_thumbnail_url_fn(
        output_file,
        media_type,
        task_id=task_id,
    )
    if thumbnail_url:
        return thumbnail_url

    if not output_file:
        return ""

    bucket_name, object_name = resolve_storage_object_fn(output_file)
    thumb_object_name = build_thumbnail_object_name_fn(object_name, media_type)
    return get_presigned_url_fn(thumb_object_name, bucket=bucket_name) or ""


async def pick_gallery_media_urls(
    *,
    task_id: str | None,
    output_file: str | None,
    media_type: str,
    resolve_gallery_media_urls_fn,
    build_media_url_fn,
    build_thumbnail_url_fn,
    logger,
) -> tuple[str, str]:
    return await resolve_gallery_media_urls_fn(
        task_id=task_id,
        output_file=output_file,
        media_type=media_type,
        build_media_url=build_media_url_fn,
        build_thumbnail_url=build_thumbnail_url_fn,
        logger=logger,
    )


async def resolve_gallery_post_media_urls(
    *,
    task_id: str | None,
    output_file: str | None,
    media_type: str,
) -> tuple[str, str]:
    return await pick_gallery_media_urls(
        task_id=task_id,
        output_file=output_file,
        media_type=media_type,
        resolve_gallery_media_urls_fn=presenter_resolve_gallery_media_urls,
        build_media_url_fn=lambda output_file, *, task_id=None: build_gallery_media_url(
            output_file=output_file,
            task_id=task_id,
            resolve_media_url_fn=resolve_media_url,
        ),
        build_thumbnail_url_fn=lambda output_file, media_type, *, task_id=None: build_gallery_thumbnail_url(
            output_file=output_file,
            media_type=media_type,
            task_id=task_id,
            resolve_thumbnail_url_fn=resolve_thumbnail_url,
            resolve_storage_object_fn=resolve_storage_object,
            build_thumbnail_object_name_fn=build_thumbnail_object_name,
            get_presigned_url_fn=storage.get_presigned_url,
        ),
        logger=logger,
    )


def resolve_gallery_author_name(
    user: User | None,
    fallback_user_id: int | None = None,
) -> str:
    if user:
        return user.full_name or user.username or f"User {user.id}"
    if fallback_user_id is not None:
        return f"User {fallback_user_id}"
    return "匿名修士"


async def build_post_responses(
    *,
    session,
    posts,
    current_user,
    translate_tags,
    resolve_history_billing_resolution,
    resolve_author_name,
    pick_gallery_media_urls,
    logger,
) -> list[GalleryPostResponse]:
    if not posts:
        return []

    post_ids = [p.id for p in posts]
    task_ids = [p.task_id for p in posts if p.task_id]

    user_likes = set()
    user_dislikes = set()
    if current_user and post_ids:
        interactions = (
            (
                await session.execute(
                    select(UserInteraction)
                    .where(UserInteraction.user_id == current_user.id)
                    .where(UserInteraction.post_id.in_(post_ids))
                    .where(UserInteraction.action_type.in_(["like", "dislike"]))
                )
            )
            .scalars()
            .all()
        )
        for inter in interactions:
            if inter.action_type == "like":
                user_likes.add(inter.post_id)
            elif inter.action_type == "dislike":
                user_dislikes.add(inter.post_id)

    history_map = {}
    if task_ids:
        histories = (
            (
                await session.execute(
                    select(History).where(History.task_id.in_(task_ids))
                )
            )
            .scalars()
            .all()
        )
        history_map = {h.task_id: h for h in histories}

    user_ids = list(set([p.user_id for p in posts if p.user_id]))
    user_map = {}
    if user_ids:
        users = (
            (await session.execute(select(User).where(User.id.in_(user_ids))))
            .scalars()
            .all()
        )
        for u in users:
            name = u.full_name if u.full_name else (u.username or f"User {u.id}")
            user_map[u.id] = name

    tasks = []
    for post in posts:
        history = history_map.get(post.task_id)
        output_file = history.output_file if history else None
        tasks.append(
            pick_gallery_media_urls(
                task_id=post.task_id,
                output_file=output_file,
                media_type=post.media_type,
            )
        )
    urls_results = await asyncio.gather(*tasks, return_exceptions=True)

    response_items = []
    for i, post in enumerate(posts):
        try:
            tags = json.loads(post.tags) if post.tags else []
        except Exception:
            tags = []
        translated_tags = translate_tags(tags)

        history = history_map.get(post.task_id)
        prompt = history.prompt if history else None
        task_type_from_history = history.type if history else None

        url_result = urls_results[i]
        if isinstance(url_result, Exception):
            logger.warning(
                "Failed to build gallery media URLs for post_id=%s task_id=%s: %s",
                post.id,
                post.task_id,
                url_result,
                exc_info=url_result,
            )
            media_url = history.output_file if history and history.output_file else ""
            thumbnail_url = ""
        else:
            media_url, thumbnail_url = url_result

        billing_resolution = None
        if history:
            billing_resolution = resolve_history_billing_resolution(
                history,
                width=post.width if post.width is not None else history.width,
                height=post.height if post.height is not None else history.height,
                gallery_post=post,
            )

        response_items.append(
            GalleryPostResponse(
                id=post.id,
                task_id=post.task_id,
                media_type=post.media_type,
                billing_resolution=billing_resolution,
                width=post.width,
                height=post.height,
                duration=post.duration,
                tags=translated_tags,
                likes_count=post.likes_count,
                dislikes_count=post.dislikes_count,
                applied_count=post.applied_count,
                comments_count=post.comments_count or 0,
                thumbnail_url=thumbnail_url,
                media_url=media_url,
                created_at=post.created_at,
                is_active=post.is_active,
                prompt=prompt,
                task_type=task_type_from_history,
                has_liked=post.id in user_likes,
                has_disliked=post.id in user_dislikes,
                author_name=user_map.get(post.user_id)
                if post.user_id
                else resolve_author_name(None),
            )
        )
    return response_items


async def build_gallery_post_responses(
    *,
    session,
    posts,
    current_user,
    pick_gallery_media_urls=resolve_gallery_post_media_urls,
) -> list[GalleryPostResponse]:
    return await build_post_responses(
        session=session,
        posts=posts,
        current_user=current_user,
        translate_tags=translate_tags,
        resolve_history_billing_resolution=resolve_history_billing_resolution,
        resolve_author_name=resolve_gallery_author_name,
        pick_gallery_media_urls=pick_gallery_media_urls,
        logger=logger,
    )


async def get_my_gallery_posts_payload(
    *,
    current_user,
    db,
    page: int,
    size: int,
    task_type: str | None,
    build_post_responses_fn=None,
) -> PaginatedGalleryResponse:
    if build_post_responses_fn is None:
        build_post_responses_fn = build_gallery_post_responses
    query = (
        select(GalleryPost)
        .outerjoin(History, GalleryPost.task_id == History.task_id)
        .where(
            GalleryPost.user_id == current_user.id, History.is_visible.is_not(False)
        )
        .distinct()
    )

    if task_type:
        query = query.where(History.type == task_type)

    query = query.order_by(desc(GalleryPost.id))

    total_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(total_query)).scalar()

    offset = (page - 1) * size
    query = query.offset(offset).limit(size)

    result = await db.execute(query)
    posts = result.scalars().all()

    response_items = await build_post_responses_fn(
        session=db,
        posts=posts,
        current_user=current_user,
    )

    pages = (total + size - 1) // size
    return PaginatedGalleryResponse(
        items=response_items, total=total, page=page, size=size, pages=pages
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
    if session_factory is None:
        session_factory = AsyncSessionLocal
    if service_fn is None:
        service_fn = get_my_gallery_posts_payload
    return await call_with_optional_db(
        db=db,
        service_fn=service_fn,
        session_factory=session_factory,
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
    build_post_responses_fn=None,
) -> PaginatedGalleryResponse:
    if build_post_responses_fn is None:
        build_post_responses_fn = build_gallery_post_responses
    action_types = ["like", "apply"]
    if filter_type == "like":
        action_types = ["like"]
    elif filter_type == "apply":
        action_types = ["apply"]

    query = (
        select(GalleryPost)
        .join(UserInteraction, GalleryPost.id == UserInteraction.post_id)
        .outerjoin(History, GalleryPost.task_id == History.task_id)
        .where(
            UserInteraction.user_id == current_user.id,
            UserInteraction.action_type.in_(action_types),
            GalleryPost.is_active == True,
        )
        .distinct()
        .order_by(desc(GalleryPost.id))
    )

    if task_type:
        query = query.where(History.type == task_type)

    total_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(total_query)).scalar()

    offset = (page - 1) * size
    query = query.offset(offset).limit(size)

    result = await db.execute(query)
    posts = result.scalars().all()

    response_items = await build_post_responses_fn(
        session=db,
        posts=posts,
        current_user=current_user,
    )

    pages = (total + size - 1) // size
    return PaginatedGalleryResponse(
        items=response_items, total=total, page=page, size=size, pages=pages
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
    if session_factory is None:
        session_factory = AsyncSessionLocal
    if service_fn is None:
        service_fn = get_my_favorite_posts_payload
    return await call_with_optional_db(
        db=db,
        service_fn=service_fn,
        session_factory=session_factory,
        current_user=current_user,
        page=page,
        size=size,
        filter_type=filter_type,
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
    build_post_responses_fn=None,
) -> PaginatedGalleryResponse:
    if fetch_gallery_feed is None:
        from src.core.gallery_core import get_gallery_feed

        fetch_gallery_feed = get_gallery_feed
    if build_post_responses_fn is None:
        build_post_responses_fn = build_gallery_post_responses
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
    pages = (total + size - 1) // size
    return PaginatedGalleryResponse(
        items=response_items,
        total=total,
        page=page,
        size=size,
        pages=pages,
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
    if session_factory is None:
        session_factory = AsyncSessionLocal
    if service_fn is None:
        service_fn = get_gallery_posts_payload
    return await call_with_optional_db(
        db=db,
        service_fn=service_fn,
        session_factory=session_factory,
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
    post = (
        await db.execute(select(GalleryPost).where(GalleryPost.id == post_id))
    ).scalar_one_or_none()
    if not post or post.is_active is False:
        raise HTTPException(status_code=404, detail="帖子不存在或已失效")

    hist_res = await db.execute(
        select(History).where(History.task_id == post.task_id)
    )
    history = hist_res.scalars().first()

    if not history:
        raise HTTPException(status_code=404, detail="未找到原任务详情")

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
    if session_factory is None:
        session_factory = AsyncSessionLocal
    if service_fn is None:
        service_fn = get_gallery_apply_context_payload
    return await call_with_optional_db(
        db=db,
        service_fn=service_fn,
        session_factory=session_factory,
        post_id=post_id,
    )


async def update_gallery_post_status(
    *,
    post_id: int,
    current_user,
    db,
    is_active: bool,
) -> dict:
    post = (
        await db.execute(select(GalleryPost).where(GalleryPost.id == post_id))
    ).scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="帖子不存在")
    if post.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作此帖子")

    await db.execute(
        update(GalleryPost)
        .where(GalleryPost.id == post_id)
        .values(is_active=is_active)
    )
    await db.commit()
    return {"status": "success", "message": f"已{'上架' if is_active else '下架'}"}


async def update_gallery_post_status_api_payload(
    *,
    post_id: int,
    current_user,
    db,
    is_active: bool,
    service_fn=None,
) -> dict:
    if service_fn is None:
        service_fn = update_gallery_post_status
    return await service_fn(
        post_id=post_id,
        current_user=current_user,
        db=db,
        is_active=is_active,
    )


async def delete_gallery_post(
    *,
    post_id: int,
    current_user,
    db,
    storage=storage,
    logger=logger,
) -> dict:
    r2_cleanup_keys: set[str] = set()
    post = (
        await db.execute(select(GalleryPost).where(GalleryPost.id == post_id))
    ).scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="帖子不存在")
    if post.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作此帖子")

    history = None
    if post.task_id:
        history = (
            await db.execute(
                select(History).where(
                    History.task_id == post.task_id, History.user_id == current_user.id
                )
            )
        ).scalar_one_or_none()

    if post.is_active:
        user_record = await db.execute(
            select(User).where(User.id == current_user.id)
        )
        user_obj = user_record.scalar_one_or_none()
        if user_obj:
            user_obj.total_contributions = max(
                (user_obj.total_contributions or 0) - 1, 0
            )

    if history:
        history.is_public = False
        if history.output_file:
            media_type = get_media_type_from_history(history.type)
            _, object_name = resolve_storage_object(history.output_file)
            thumb_object_name = build_thumbnail_object_name(object_name, media_type)
            r2_cleanup_keys = {
                key
                for key in {
                    build_history_r2_media_key(post.task_id, history.output_file),
                    build_history_r2_thumbnail_key(post.task_id, media_type),
                    build_legacy_r2_key(object_name),
                    build_legacy_r2_key(thumb_object_name),
                }
                if key
            }
    elif post.task_id:
        await db.execute(
            update(History)
            .where(
                History.task_id == post.task_id, History.user_id == current_user.id
            )
            .values(is_public=False)
        )

    await db.execute(
        delete(UserInteraction).where(UserInteraction.post_id == post_id)
    )
    await db.execute(
        delete(GalleryComment).where(GalleryComment.post_id == post_id)
    )
    await db.execute(delete(GalleryPost).where(GalleryPost.id == post_id))

    await db.commit()

    if r2_cleanup_keys:
        try:
            await storage.async_delete_r2_objects(list(r2_cleanup_keys))
        except Exception:
            logger.warning(
                "Failed to clean R2 cache after deleting gallery post %s",
                post_id,
                exc_info=True,
            )

    return {"status": "success", "message": "删除成功"}


async def delete_gallery_post_api_payload(
    *,
    post_id: int,
    current_user,
    db=None,
    session_factory=None,
    service_fn=None,
) -> dict:
    if session_factory is None:
        session_factory = AsyncSessionLocal
    if service_fn is None:
        service_fn = delete_gallery_post
    return await call_with_optional_db(
        db=db,
        service_fn=service_fn,
        session_factory=session_factory,
        post_id=post_id,
        current_user=current_user,
    )


async def interact_with_gallery_post(
    *,
    post_id: int,
    action: str,
    current_user,
    toggle_like=None,
    gallery_core_error_cls=None,
    duplicate_interaction_error_cls=None,
    logger=logger,
) -> dict:
    try:
        if (
            toggle_like is None
            or gallery_core_error_cls is None
            or duplicate_interaction_error_cls is None
        ):
            from src.core.gallery_core import (
                DuplicateInteractionError,
                GalleryCoreError,
                toggle_like as core_toggle_like,
            )

            toggle_like = toggle_like or core_toggle_like
            gallery_core_error_cls = gallery_core_error_cls or GalleryCoreError
            duplicate_interaction_error_cls = (
                duplicate_interaction_error_cls or DuplicateInteractionError
            )
        result = await toggle_like(current_user.id, post_id, action)
        action_state = result.get("action_state")
        if action_state == "canceled":
            message = "已取消点赞" if action == "like" else "已取消点踩"
        else:
            message = "点赞成功" if action == "like" else "点踩成功"
        return {"status": "success", "message": message, "data": result}
    except duplicate_interaction_error_cls as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except gallery_core_error_cls as exc:
        if "不存在" in str(exc):
            raise HTTPException(status_code=404, detail=str(exc))
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.error("发生未捕获异常", exc_info=True)
        raise HTTPException(status_code=500, detail="服务器内部错误")


async def interact_with_gallery_post_api_payload(
    *,
    post_id: int,
    action: str,
    current_user,
    service_fn=None,
) -> dict:
    if service_fn is None:
        service_fn = interact_with_gallery_post
    return await service_fn(
        post_id=post_id,
        action=action,
        current_user=current_user,
    )


async def create_gallery_comment_payload(
    *,
    post_id: int,
    comment,
    current_user,
    db,
    redis_client=None,
    resolve_author_name=resolve_gallery_author_name,
) -> GalleryCommentResponse:
    if redis_client is None:
        from src.services.redis_client import redis_client as default_redis_client

        redis_client = default_redis_client
    unavailable_comment_error = "帖子已下架或已删除，无法发布评论"

    post = await db.get(GalleryPost, post_id)
    if not post or not post.is_active:
        raise HTTPException(status_code=404, detail="帖子不存在或已下架")

    lock_acquired = await redis_client.set_comment_lock(current_user.id, ttl=5)
    if not lock_acquired:
        raise HTTPException(status_code=429, detail="操作过于频繁，请稍后再试")

    new_comment = GalleryComment(
        post_id=post_id,
        user_id=current_user.id,
        content=comment.content,
    )
    try:
        db.add(new_comment)
        await db.flush()

        stmt = (
            update(GalleryPost)
            .where(GalleryPost.id == post_id, GalleryPost.is_active.is_(True))
            .values(comments_count=GalleryPost.comments_count + 1)
        )
        result = await db.execute(stmt)

        if result.rowcount == 0:
            await db.rollback()
            await redis_client.delete_comment_lock(current_user.id)
            raise HTTPException(status_code=404, detail=unavailable_comment_error)

        response_data = GalleryCommentResponse(
            id=new_comment.id,
            content=new_comment.content,
            created_at=new_comment.created_at,
            user=CommentUserResponse(
                id=current_user.id,
                author_name=resolve_author_name(current_user),
            ),
        )

        await db.commit()
        return response_data
    except HTTPException:
        raise
    except IntegrityError:
        await db.rollback()
        await redis_client.delete_comment_lock(current_user.id)
        raise HTTPException(status_code=404, detail=unavailable_comment_error)
    except Exception:
        await db.rollback()
        await redis_client.delete_comment_lock(current_user.id)
        raise HTTPException(status_code=500, detail="发布评论失败")


async def create_gallery_comment_api_payload(
    *,
    post_id: int,
    comment,
    current_user,
    db=None,
    session_factory=None,
    service_fn=None,
) -> GalleryCommentResponse:
    if session_factory is None:
        session_factory = AsyncSessionLocal
    if service_fn is None:
        service_fn = create_gallery_comment_payload
    return await call_with_optional_db(
        db=db,
        service_fn=service_fn,
        session_factory=session_factory,
        post_id=post_id,
        comment=comment,
        current_user=current_user,
    )


async def get_gallery_comments_payload(
    *,
    post_id: int,
    page: int,
    size: int,
    db,
    resolve_author_name=resolve_gallery_author_name,
) -> PaginatedCommentResponse:
    post = await db.get(GalleryPost, post_id)
    if not post or not post.is_active:
        raise HTTPException(status_code=404, detail="帖子不存在或已下架")

    count_stmt = select(func.count(GalleryComment.id)).where(
        GalleryComment.post_id == post_id,
        GalleryComment.is_active.is_(True),
    )
    total = await db.scalar(count_stmt) or 0

    stmt = (
        select(GalleryComment)
        .options(joinedload(GalleryComment.user))
        .where(
            GalleryComment.post_id == post_id,
            GalleryComment.is_active.is_(True),
        )
        .order_by(desc(GalleryComment.created_at), desc(GalleryComment.id))
        .offset((page - 1) * size)
        .limit(size)
    )
    result = await db.execute(stmt)
    comments = result.scalars().all()

    response_items = []
    for c in comments:
        response_items.append(
            GalleryCommentResponse(
                id=c.id,
                content=c.content,
                created_at=c.created_at,
                user=CommentUserResponse(
                    id=c.user.id if c.user else c.user_id,
                    author_name=resolve_author_name(c.user, c.user_id),
                ),
            )
        )

    pages = (total + size - 1) // size
    return PaginatedCommentResponse(
        items=response_items,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


async def get_gallery_comments_api_payload(
    *,
    post_id: int,
    page: int,
    size: int,
    db=None,
    session_factory=None,
    service_fn=None,
) -> PaginatedCommentResponse:
    if session_factory is None:
        session_factory = AsyncSessionLocal
    if service_fn is None:
        service_fn = get_gallery_comments_payload
    return await call_with_optional_db(
        db=db,
        service_fn=service_fn,
        session_factory=session_factory,
        post_id=post_id,
        page=page,
        size=size,
    )
