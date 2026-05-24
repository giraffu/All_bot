from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.orm import selectinload

from src.constants import MODE_IMAGE_TO_VIDEO
from src.database.models import GalleryPost, History


def _apply_active_filter(query, *, is_active: bool | None):
    if is_active is True:
        return query.where(GalleryPost.is_active == True)
    if is_active is False:
        return query.where(GalleryPost.is_active == False)
    return query


def _apply_task_type_or_category_filter(
    query,
    *,
    task_type: str | None,
    category: str | None,
):
    if task_type and task_type != "all":
        return (
            query.join(History, GalleryPost.task_id == History.task_id).where(
                History.type == task_type
            )
        )

    if not category or category == "all":
        return query

    query = query.join(History, GalleryPost.task_id == History.task_id)
    if category == "i2ipro":
        return query.where(History.type == "i2i_pro")
    if category == "faceswap":
        return query.where(History.type.in_(["face_video"]))
    if category == "edit":
        return query.where(History.type.in_(["edit", "quick_image"]))
    if category == "imglora":
        return query.where(History.type == "img2img_lora")
    if category == "custvid":
        return query.where(History.type == "custom_video")
    if category == "vidlora":
        return query.where(History.type == MODE_IMAGE_TO_VIDEO)
    if category == "ltxvid":
        return query.where(History.type == "ltx_video")
    return query


def _apply_media_filters(
    query,
    *,
    media_type: str | None,
    task_type: str | None,
    category: str | None,
    lora_model: str | None,
    user_id: int | None,
    sort_by: str,
):
    if media_type and media_type != "all" and not task_type and not category:
        query = query.where(GalleryPost.media_type == media_type)

    if lora_model:
        lora_tag = f'"#{lora_model}"'
        query = query.where(GalleryPost.tags.like(f"%{lora_tag}%"))

    if user_id and sort_by == "mine":
        query = query.where(GalleryPost.user_id == user_id)

    return query


def _apply_time_range_filter(query, *, time_range: str):
    now = datetime.now()
    if time_range == "today":
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return query.where(GalleryPost.created_at >= start_time)
    if time_range == "week":
        return query.where(GalleryPost.created_at >= now - timedelta(days=7))
    if time_range == "month":
        return query.where(GalleryPost.created_at >= now - timedelta(days=30))
    return query


def _apply_sort(query, *, sort_by: str):
    if sort_by == "likes":
        return query.order_by(desc(GalleryPost.likes_count), desc(GalleryPost.created_at))
    if sort_by == "dislikes":
        return query.order_by(
            desc(GalleryPost.dislikes_count), desc(GalleryPost.created_at)
        )
    if sort_by == "absolute_likes":
        return query.order_by(
            desc(GalleryPost.likes_count - GalleryPost.dislikes_count),
            desc(GalleryPost.created_at),
        )
    if sort_by == "absolute_dislikes":
        return query.order_by(
            desc(GalleryPost.dislikes_count - GalleryPost.likes_count),
            desc(GalleryPost.created_at),
        )
    if sort_by == "applied":
        return query.order_by(
            desc(GalleryPost.applied_count), desc(GalleryPost.created_at)
        )
    return query.order_by(desc(GalleryPost.created_at))


def build_gallery_feed_query(
    *,
    media_type: str | None,
    task_type: str | None,
    lora_model: str | None,
    sort_by: str,
    time_range: str,
    user_id: int | None,
    category: str | None,
    is_active: bool | None,
):
    query = select(GalleryPost)
    query = _apply_active_filter(query, is_active=is_active)
    query = _apply_task_type_or_category_filter(
        query,
        task_type=task_type,
        category=category,
    )
    query = _apply_media_filters(
        query,
        media_type=media_type,
        task_type=task_type,
        category=category,
        lora_model=lora_model,
        user_id=user_id,
        sort_by=sort_by,
    )
    query = _apply_time_range_filter(query, time_range=time_range)
    query = _apply_sort(query, sort_by=sort_by)
    return query


async def fetch_gallery_feed_page(
    *,
    session,
    page: int,
    size: int,
    media_type: str | None,
    task_type: str | None,
    lora_model: str | None,
    sort_by: str,
    time_range: str,
    user_id: int | None,
    category: str | None,
    is_active: bool | None,
) -> tuple[list, int]:
    query = build_gallery_feed_query(
        media_type=media_type,
        task_type=task_type,
        lora_model=lora_model,
        sort_by=sort_by,
        time_range=time_range,
        user_id=user_id,
        category=category,
        is_active=is_active,
    )

    total_query = select(func.count()).select_from(query.subquery())
    total = (await session.execute(total_query)).scalar()

    offset = (page - 1) * size if page > 0 else 0
    paged_query = query.options(
        selectinload(GalleryPost.user), selectinload(GalleryPost.histories)
    ).offset(offset).limit(size)

    result = await session.execute(paged_query)
    return result.scalars().all(), total
