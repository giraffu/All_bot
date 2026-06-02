import logging
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import desc, func, select, update
from sqlalchemy.orm import joinedload

from dashboard.backend.presenters.gallery_admin_presenter import (
    build_dashboard_comment_item,
    build_gallery_post_item,
)
from src.database.models import GalleryComment, GalleryPost, History, User
from src.services.submission_ban_service import build_submission_ban_message
from src.services.storage import storage
from src.services.storage_r2_cleanup import build_history_r2_cleanup_keys

logger = logging.getLogger("dashboard.gallery")


async def get_all_gallery_posts_payload(
    *,
    page: int,
    page_size: int,
    is_active,
    media_type,
    task_type,
    sort_by,
    username=None,
    prompt_contains=None,
    prompt_max_length=None,
    storage_service=None,
    get_gallery_feed_func=None,
    logger_override: logging.Logger | None = None,
) -> dict:
    active_logger = logger_override or logger
    if storage_service is None:
        storage_service = storage
    if get_gallery_feed_func is None:
        from src.core.gallery_core import get_gallery_feed

        get_gallery_feed_func = get_gallery_feed

    try:
        posts, total_count = await get_gallery_feed_func(
            page=page,
            size=page_size,
            media_type=media_type,
            task_type=task_type,
            sort_by=sort_by or "latest",
            time_range="all",
            is_active=is_active,
            username=username,
            prompt_contains=prompt_contains,
            prompt_max_length=prompt_max_length,
        )
        return {
            "total": total_count,
            "page": page,
            "page_size": page_size,
            "items": [
                build_gallery_post_item(post=post, storage_service=storage_service)
                for post in posts
            ],
        }
    except Exception as exc:
        active_logger.error(f"Failed to get gallery posts: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def update_gallery_post_payload(
    *,
    post_id: int,
    update_data,
    db,
    logger_override: logging.Logger | None = None,
) -> dict:
    active_logger = logger_override or logger
    try:
        result = await db.execute(select(GalleryPost).where(GalleryPost.id == post_id))
        post = result.scalar_one_or_none()
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        if update_data.is_active is not None:
            post.is_active = update_data.is_active
        if update_data.likes_count is not None:
            post.likes_count = max(update_data.likes_count, 0)
        if update_data.dislikes_count is not None:
            post.dislikes_count = max(update_data.dislikes_count, 0)
        if update_data.applied_count is not None:
            post.applied_count = max(update_data.applied_count, 0)
        if update_data.comments_count is not None:
            post.comments_count = max(update_data.comments_count, 0)
        if update_data.tags is not None:
            post.tags = update_data.tags

        await db.commit()
        return {"success": True, "message": "Post updated successfully"}
    except HTTPException:
        raise
    except Exception as exc:
        active_logger.error(f"Failed to update gallery post: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def delete_gallery_post_payload(
    *,
    post_id: int,
    db,
    storage_service=storage,
    logger_override: logging.Logger | None = None,
) -> dict:
    active_logger = logger_override or logger
    r2_cleanup_keys: set[str] = set()
    try:
        result = await db.execute(select(GalleryPost).where(GalleryPost.id == post_id))
        post = result.scalar_one_or_none()
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        if post.task_id:
            history_result = await db.execute(
                select(History).where(
                    History.task_id == post.task_id,
                    History.user_id == post.user_id,
                )
            )
            histories = history_result.scalars().all()
            if histories:
                for history in histories:
                    history.is_public = False
                    if history.output_file:
                        r2_cleanup_keys.update(
                            build_history_r2_cleanup_keys(
                                post.task_id,
                                history.output_file,
                                history.type,
                            )
                        )
            else:
                await db.execute(
                    update(History)
                    .where(
                        History.task_id == post.task_id,
                        History.user_id == post.user_id,
                    )
                    .values(is_public=False)
                )

        await db.delete(post)
        await db.commit()

        if r2_cleanup_keys:
            try:
                await storage_service.async_delete_r2_objects(list(r2_cleanup_keys))
            except Exception:
                active_logger.warning(
                    "Failed to clean R2 cache after dashboard deleting gallery post %s",
                    post_id,
                    exc_info=True,
                )

        return {"success": True, "message": "Post deleted successfully"}
    except HTTPException:
        raise
    except Exception as exc:
        active_logger.error(f"Failed to delete gallery post: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def ban_user_submissions_and_takedown_payload(
    *,
    user_id: int,
    request,
    db,
    logger_override: logging.Logger | None = None,
) -> dict:
    active_logger = logger_override or logger
    try:
        user = (
            await db.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        old_status = bool(user.is_submission_banned)
        old_reason = user.submission_ban_reason
        ban_reason = build_submission_ban_message(getattr(request, "reason", None))

        task_id_rows = (
            await db.execute(
                select(GalleryPost.task_id).where(
                    GalleryPost.user_id == user_id,
                    GalleryPost.task_id.is_not(None),
                )
            )
        ).all()
        task_ids = sorted({row[0] for row in task_id_rows if row[0]})

        user.is_submission_banned = True
        user.submission_banned_at = datetime.now()
        user.submission_ban_reason = ban_reason

        post_result = await db.execute(
            update(GalleryPost)
            .where(
                GalleryPost.user_id == user_id,
                GalleryPost.is_active.is_(True),
            )
            .values(is_active=False)
        )
        affected_posts = max(getattr(post_result, "rowcount", 0) or 0, 0)

        affected_histories = 0
        if task_ids:
            history_result = await db.execute(
                update(History)
                .where(
                    History.user_id == user_id,
                    History.task_id.in_(task_ids),
                    History.is_public.is_(True),
                )
                .values(is_public=False)
            )
            affected_histories = max(
                getattr(history_result, "rowcount", 0) or 0,
                0,
            )

        await db.commit()

        from src.services.log_service import LogService

        await LogService.log_action(
            user_id=user_id,
            username=user.username or user.full_name,
            operation_type="admin_gallery_submission_ban_takedown",
            credit_change=0,
            current_balance=user.credits or 0,
            extra_info={
                "old_status": old_status,
                "new_status": True,
                "old_reason": old_reason,
                "new_reason": user.submission_ban_reason,
                "affected_posts": affected_posts,
                "affected_histories": affected_histories,
                "source": "dashboard_gallery_admin",
            },
        )

        return {
            "status": "ok",
            "user_id": user.id,
            "is_submission_banned": user.is_submission_banned,
            "submission_banned_at": user.submission_banned_at,
            "submission_ban_reason": user.submission_ban_reason,
            "affected_posts": affected_posts,
            "affected_histories": affected_histories,
        }
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        active_logger.error(
            "Failed to ban and takedown gallery submissions for user %s: %s",
            user_id,
            exc,
        )
        raise HTTPException(status_code=500, detail=str(exc))


async def get_all_gallery_comments_payload(
    *,
    page: int,
    page_size: int,
    post_id,
    is_active,
    db,
    logger_override: logging.Logger | None = None,
) -> dict:
    active_logger = logger_override or logger
    try:
        filters = []
        if post_id is not None:
            filters.append(GalleryComment.post_id == post_id)
        if is_active is not None:
            filters.append(GalleryComment.is_active.is_(is_active))

        total_stmt = select(func.count(GalleryComment.id))
        if filters:
            total_stmt = total_stmt.where(*filters)
        total = await db.scalar(total_stmt) or 0

        stmt = (
            select(GalleryComment)
            .options(joinedload(GalleryComment.user), joinedload(GalleryComment.post))
            .order_by(desc(GalleryComment.created_at), desc(GalleryComment.id))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        if filters:
            stmt = stmt.where(*filters)

        result = await db.execute(stmt)
        comments = result.scalars().all()
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [build_dashboard_comment_item(comment) for comment in comments],
        }
    except Exception as exc:
        active_logger.error(f"Failed to get all gallery comments: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def get_gallery_comments_payload(
    *,
    post_id: int,
    page: int,
    page_size: int,
    db,
    logger_override: logging.Logger | None = None,
) -> dict:
    active_logger = logger_override or logger
    try:
        post = await db.get(GalleryPost, post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        total_stmt = select(func.count(GalleryComment.id)).where(
            GalleryComment.post_id == post_id
        )
        total = await db.scalar(total_stmt) or 0
        active_total_stmt = select(func.count(GalleryComment.id)).where(
            GalleryComment.post_id == post_id,
            GalleryComment.is_active.is_(True),
        )
        active_total = await db.scalar(active_total_stmt) or 0

        stmt = (
            select(GalleryComment)
            .options(joinedload(GalleryComment.user))
            .where(GalleryComment.post_id == post_id)
            .order_by(desc(GalleryComment.created_at), desc(GalleryComment.id))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(stmt)
        comments = result.scalars().all()
        return {
            "total": total,
            "active_total": active_total,
            "page": page,
            "page_size": page_size,
            "items": [build_dashboard_comment_item(comment) for comment in comments],
        }
    except HTTPException:
        raise
    except Exception as exc:
        active_logger.error(f"Failed to get gallery comments: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def update_gallery_comment_payload(
    *,
    comment_id: int,
    update_data,
    db,
    logger_override: logging.Logger | None = None,
) -> dict:
    active_logger = logger_override or logger
    try:
        comment = await db.get(GalleryComment, comment_id)
        if not comment:
            raise HTTPException(status_code=404, detail="Comment not found")

        update_comment_stmt = (
            update(GalleryComment)
            .where(
                GalleryComment.id == comment_id,
                GalleryComment.is_active.is_not(update_data.is_active),
            )
            .values(is_active=update_data.is_active)
            .returning(GalleryComment.post_id)
        )
        post_id = (await db.execute(update_comment_stmt)).scalar_one_or_none()
        if post_id is None:
            return {"success": True, "message": "No change needed"}

        if update_data.is_active:
            stmt = (
                update(GalleryPost)
                .where(GalleryPost.id == post_id)
                .values(comments_count=GalleryPost.comments_count + 1)
            )
        else:
            stmt = (
                update(GalleryPost)
                .where(GalleryPost.id == post_id)
                .values(comments_count=func.greatest(GalleryPost.comments_count - 1, 0))
            )
        await db.execute(stmt)
        await db.commit()
        return {"success": True, "message": "Comment updated successfully"}
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        active_logger.error(f"Failed to update gallery comment: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
