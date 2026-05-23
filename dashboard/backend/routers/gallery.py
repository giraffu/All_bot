import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.database.core import get_db
from src.database.models import GalleryComment, GalleryPost
from src.services.storage import storage

router = APIRouter(prefix="/api/gallery", tags=["gallery"])
logger = logging.getLogger("dashboard.gallery")


def _build_dashboard_comment_item(comment: GalleryComment) -> dict:
    return {
        "id": comment.id,
        "post_id": comment.post_id,
        "post_task_id": comment.post.task_id if comment.post else None,
        "post_is_active": comment.post.is_active if comment.post else None,
        "user_id": comment.user_id,
        "author_name": (
            comment.user.full_name
            or comment.user.username
            or f"User {comment.user_id}"
        )
        if comment.user
        else f"User {comment.user_id}",
        "content": comment.content,
        "is_active": comment.is_active,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
    }


class GalleryPostUpdate(BaseModel):
    is_active: Optional[bool] = None
    likes_count: Optional[int] = Field(default=None, ge=0)
    dislikes_count: Optional[int] = Field(default=None, ge=0)
    applied_count: Optional[int] = Field(default=None, ge=0)
    comments_count: Optional[int] = Field(default=None, ge=0)
    tags: Optional[str] = None


@router.get("/all")
async def get_all_gallery_posts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_active: Optional[bool] = None,
    media_type: Optional[str] = None,
    task_type: Optional[str] = None,
    sort_by: Optional[str] = None,
):
    try:
        from src.core.gallery_core import get_gallery_feed

        posts, total_count = await get_gallery_feed(
            page=page,
            size=page_size,
            media_type=media_type,
            task_type=task_type,
            sort_by=sort_by or "latest",
            time_range="all",
            is_active=is_active,
        )

        formatted_posts = []
        for p in posts:
            # We might have multiple histories, use the first one if available
            first_history = p.histories[0] if p.histories else None
            output_file = first_history.output_file if first_history else None
            media_url = None
            if output_file:
                # Dashboard API serves files from proxy or direct S3 link
                # Try to use get_file_url if it exists, otherwise generate presigned URL or use static proxy
                if hasattr(storage, "get_file_url"):
                    media_url = storage.get_file_url(output_file)
                else:
                    # In this system, files might be served via /api/history/media/ (if proxy)
                    # or direct S3 presigned URL
                    if hasattr(storage, "get_presigned_url"):
                        media_url = storage.get_presigned_url(output_file)
                    elif hasattr(storage, "get_presigned_download_url"):
                        media_url = storage.get_presigned_download_url(output_file)
                    else:
                        # Fallback: Let frontend know it needs to fetch via standard history endpoint
                        media_url = f"/api/history/media/{p.task_id}"

            formatted_posts.append(
                {
                    "id": p.id,
                    "task_id": p.task_id,
                    "user_id": p.user_id,
                    "username": p.user.username if p.user else None,
                    "media_type": p.media_type,
                    "task_type": first_history.type if first_history else "unknown",
                    "width": p.width,
                    "height": p.height,
                    "duration": p.duration,
                    "tags": p.tags,
                    "likes_count": p.likes_count,
                    "dislikes_count": p.dislikes_count,
                    "applied_count": p.applied_count,
                    "comments_count": p.comments_count,
                    "is_active": p.is_active,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "media_url": media_url,
                    "prompt": first_history.prompt if first_history else None,
                }
            )

        return {
            "total": total_count,
            "page": page,
            "page_size": page_size,
            "items": formatted_posts,
        }
    except Exception as e:
        logger.error(f"Failed to get gallery posts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{post_id:int}")
async def update_gallery_post(
    post_id: int, update_data: GalleryPostUpdate, db: AsyncSession = Depends(get_db)
):
    try:
        stmt = select(GalleryPost).where(GalleryPost.id == post_id)
        result = await db.execute(stmt)
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
    except Exception as e:
        logger.error(f"Failed to update gallery post: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{post_id}")
async def delete_gallery_post(post_id: int, db: AsyncSession = Depends(get_db)):
    try:
        stmt = select(GalleryPost).where(GalleryPost.id == post_id)
        result = await db.execute(stmt)
        post = result.scalar_one_or_none()

        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        await db.delete(post)
        await db.commit()
        return {"success": True, "message": "Post deleted successfully"}
    except Exception as e:
        logger.error(f"Failed to delete gallery post: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class CommentUpdate(BaseModel):
    is_active: bool


@router.get("/comments/all")
async def get_all_gallery_comments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    post_id: Optional[int] = Query(None, ge=1),
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
):
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
            .options(
                joinedload(GalleryComment.user),
                joinedload(GalleryComment.post),
            )
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
            "items": [_build_dashboard_comment_item(comment) for comment in comments],
        }
    except Exception as e:
        logger.error(f"Failed to get all gallery comments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/comments")
async def get_gallery_comments(
    post_id: int = Query(..., ge=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
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
            "items": [_build_dashboard_comment_item(comment) for comment in comments],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get gallery comments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/comments/{comment_id}")
async def update_gallery_comment(
    comment_id: int, update_data: CommentUpdate, db: AsyncSession = Depends(get_db)
):
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
                .values(
                    comments_count=func.greatest(GalleryPost.comments_count - 1, 0)
                )
            )

        await db.execute(stmt)
        await db.commit()
        return {"success": True, "message": "Comment updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to update gallery comment: {e}")
        raise HTTPException(status_code=500, detail=str(e))
