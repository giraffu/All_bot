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
from src.database.models import GalleryComment, GalleryPost, History, User, UserInteraction
from src.web_api.schemas.gallery_schema import (
    ApplyContextResponse,
    CommentUserResponse,
    GalleryCommentResponse,
    GalleryPostResponse,
    PaginatedCommentResponse,
    PaginatedGalleryResponse,
)


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


async def get_my_gallery_posts_payload(
    *,
    current_user,
    db,
    page: int,
    size: int,
    task_type: str | None,
    build_post_responses_fn,
) -> PaginatedGalleryResponse:
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

    response_items = await build_post_responses_fn(db, posts, current_user)

    pages = (total + size - 1) // size
    return PaginatedGalleryResponse(
        items=response_items, total=total, page=page, size=size, pages=pages
    )


async def get_my_favorite_posts_payload(
    *,
    current_user,
    db,
    page: int,
    size: int,
    filter_type: str,
    task_type: str | None,
    build_post_responses_fn,
) -> PaginatedGalleryResponse:
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

    response_items = await build_post_responses_fn(db, posts, current_user)

    pages = (total + size - 1) // size
    return PaginatedGalleryResponse(
        items=response_items, total=total, page=page, size=size, pages=pages
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


async def delete_gallery_post(
    *,
    post_id: int,
    current_user,
    db,
    storage,
    logger,
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


async def interact_with_gallery_post(
    *,
    post_id: int,
    action: str,
    current_user,
    toggle_like,
    gallery_core_error_cls,
    duplicate_interaction_error_cls,
    logger,
) -> dict:
    try:
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


async def create_gallery_comment_payload(
    *,
    post_id: int,
    comment,
    current_user,
    db,
    redis_client,
    resolve_author_name,
) -> GalleryCommentResponse:
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


async def get_gallery_comments_payload(
    *,
    post_id: int,
    page: int,
    size: int,
    db,
    resolve_author_name,
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
