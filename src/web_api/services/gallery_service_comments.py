from fastapi import HTTPException
from sqlalchemy import desc, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from src.database.core import AsyncSessionLocal
from src.database.models import GalleryComment, GalleryPost
from src.web_api.common.utils import call_with_optional_db
from src.web_api.schemas.gallery_schema import (
    CommentUserResponse,
    GalleryCommentResponse,
    PaginatedCommentResponse,
)
from src.web_api.services.gallery_service_support import (
    resolve_gallery_author_name,
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
        await redis_client.delete_comment_lock(current_user.id)
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
    return await call_with_optional_db(
        db=db,
        service_fn=service_fn or create_gallery_comment_payload,
        session_factory=session_factory or AsyncSessionLocal,
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
    for comment_item in comments:
        response_items.append(
            GalleryCommentResponse(
                id=comment_item.id,
                content=comment_item.content,
                created_at=comment_item.created_at,
                user=CommentUserResponse(
                    id=comment_item.user.id if comment_item.user else comment_item.user_id,
                    author_name=resolve_author_name(
                        comment_item.user, comment_item.user_id
                    ),
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
    return await call_with_optional_db(
        db=db,
        service_fn=service_fn or get_gallery_comments_payload,
        session_factory=session_factory or AsyncSessionLocal,
        post_id=post_id,
        page=page,
        size=size,
    )
