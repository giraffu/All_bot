import logging

from fastapi import HTTPException
from sqlalchemy import desc, func, select, update
from sqlalchemy.orm import joinedload

from dashboard.backend.presenters.gallery_admin_presenter import (
    build_dashboard_comment_item,
    build_gallery_post_item,
)
from src.database.models import GalleryComment, GalleryPost
from src.services.storage import storage

logger = logging.getLogger("dashboard.gallery")


async def get_all_gallery_posts_payload(
    *,
    page: int,
    page_size: int,
    is_active,
    media_type,
    task_type,
    sort_by,
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
    logger_override: logging.Logger | None = None,
) -> dict:
    active_logger = logger_override or logger
    try:
        result = await db.execute(select(GalleryPost).where(GalleryPost.id == post_id))
        post = result.scalar_one_or_none()
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        await db.delete(post)
        await db.commit()
        return {"success": True, "message": "Post deleted successfully"}
    except HTTPException:
        raise
    except Exception as exc:
        active_logger.error(f"Failed to delete gallery post: {exc}")
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

        total_stmt = select(func.count(GalleryComment.id)).where(GalleryComment.post_id == post_id)
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
