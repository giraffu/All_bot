import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.core import get_db
from src.database.models import GalleryPost
from src.services.storage import storage

router = APIRouter(prefix="/api/gallery", tags=["gallery"])
logger = logging.getLogger("dashboard.gallery")

class GalleryPostUpdate(BaseModel):
    is_active: Optional[bool] = None
    likes_count: Optional[int] = None
    dislikes_count: Optional[int] = None
    applied_count: Optional[int] = None
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
            is_active=is_active
        )

        formatted_posts = []
        for p in posts:
            output_file = p.history.output_file if p.history else None
            media_url = None
            if output_file:
                # Dashboard API serves files from proxy or direct S3 link
                # Try to use get_file_url if it exists, otherwise generate presigned URL or use static proxy
                if hasattr(storage, 'get_file_url'):
                    media_url = storage.get_file_url(output_file)
                else:
                    # In this system, files might be served via /api/history/media/ (if proxy) 
                    # or direct S3 presigned URL
                    if hasattr(storage, 'get_presigned_url'):
                        media_url = storage.get_presigned_url(output_file)
                    elif hasattr(storage, 'get_presigned_download_url'):
                        media_url = storage.get_presigned_download_url(output_file)
                    else:
                        # Fallback: Let frontend know it needs to fetch via standard history endpoint
                        media_url = f"/api/history/media/{p.task_id}"
                
            formatted_posts.append({
                "id": p.id,
                "task_id": p.task_id,
                "user_id": p.user_id,
                "username": p.user.username if p.user else None,
                "media_type": p.media_type,
                "task_type": p.history.type if p.history else "unknown",
                "width": p.width,
                "height": p.height,
                "duration": p.duration,
                "tags": p.tags,
                "likes_count": p.likes_count,
                "dislikes_count": p.dislikes_count,
                "applied_count": p.applied_count,
                "is_active": p.is_active,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "media_url": media_url,
                "prompt": p.history.prompt if p.history else None
            })

        return {
            "total": total_count,
            "page": page,
            "page_size": page_size,
            "items": formatted_posts
        }
    except Exception as e:
        logger.error(f"Failed to get gallery posts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{post_id}")
async def update_gallery_post(
    post_id: int, 
    update_data: GalleryPostUpdate,
    db: AsyncSession = Depends(get_db)
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
            post.likes_count = update_data.likes_count
        if update_data.dislikes_count is not None:
            post.dislikes_count = update_data.dislikes_count
        if update_data.applied_count is not None:
            post.applied_count = update_data.applied_count
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
async def delete_gallery_post(
    post_id: int, 
    db: AsyncSession = Depends(get_db)
):
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
