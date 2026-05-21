import asyncio
import re
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import desc, func, select

from src.core.media_paths import get_media_type_from_history
from src.database.models import GalleryPost, History
from src.web_api.routers.utils import build_history_apply_context_response
from src.web_api.schemas.gallery_schema import GalleryPostResponse, PaginatedGalleryResponse
from src.web_api.schemas.user_schema import HistoryItem, PaginatedHistory


async def pick_history_media_urls(
    *,
    resolve_history_media_urls,
    task_id: str | None,
    output_file: str | None,
    history_type: str | None,
) -> tuple[str, str]:
    return await resolve_history_media_urls(
        task_id=task_id,
        output_file=output_file,
        history_type=history_type,
    )


def gallery_post_sort_key(post: GalleryPost) -> tuple[int, datetime, int]:
    created_at = getattr(post, "created_at", None) or datetime.min
    return (
        1 if getattr(post, "is_active", False) else 0,
        created_at,
        getattr(post, "id", 0) or 0,
    )


def pick_preferred_gallery_post(
    posts: list[GalleryPost] | tuple[GalleryPost, ...],
) -> GalleryPost | None:
    preferred: GalleryPost | None = None
    for post in posts:
        if post is None:
            continue
        if preferred is None or gallery_post_sort_key(post) > gallery_post_sort_key(
            preferred
        ):
            preferred = post
    return preferred


def build_gallery_post_map(posts: list[GalleryPost]) -> dict[str, GalleryPost]:
    post_map: dict[str, GalleryPost] = {}
    for post in posts:
        if not post or not post.task_id:
            continue
        current = post_map.get(post.task_id)
        if current is None or gallery_post_sort_key(post) > gallery_post_sort_key(
            current
        ):
            post_map[post.task_id] = post
    return post_map


async def get_user_history_payload(
    *,
    current_user,
    db,
    resolve_history_media_urls,
    limit: int = 8,
) -> PaginatedHistory:
    subq = (
        select(History.id)
        .where(History.user_id == current_user.id)
        .order_by(History.created_at.desc())
        .limit(limit)
        .subquery()
    )

    stmt = (
        select(History)
        .where(History.id.in_(select(subq.c.id)))
        .where(History.is_visible.is_not(False))
        .order_by(History.created_at.desc())
    )
    result = await db.execute(stmt)
    items = result.scalars().all()

    task_ids_to_check = [item.task_id for item in items if item.is_public and item.task_id]
    active_task_ids = set()
    if task_ids_to_check:
        gp_stmt = select(GalleryPost.task_id).where(
            GalleryPost.task_id.in_(task_ids_to_check), GalleryPost.is_active == True
        )
        gp_result = await db.execute(gp_stmt)
        active_task_ids = set(gp_result.scalars().all())

    url_pairs = await asyncio.gather(
        *[
            pick_history_media_urls(
                resolve_history_media_urls=resolve_history_media_urls,
                task_id=item.task_id,
                output_file=item.output_file,
                history_type=item.type,
            )
            for item in items
        ]
    )

    response_items = []
    for item, (output_file_url, thumbnail_url) in zip(items, url_pairs):
        is_public = bool(item.is_public)
        if is_public and item.task_id and item.task_id not in active_task_ids:
            is_public = False

        response_items.append(
            HistoryItem(
                id=item.id,
                task_id=item.task_id,
                type=item.type,
                prompt=item.prompt,
                input_file=item.input_file,
                output_file=item.output_file,
                billing_resolution=item.billing_resolution,
                width=item.width,
                height=item.height,
                duration=item.duration,
                output_file_url=output_file_url,
                thumbnail_url=thumbnail_url,
                created_at=item.created_at,
                allow_contribute=item.allow_contribute,
                source=item.source,
                is_public=is_public,
                is_favorited=item.is_favorited,
            )
        )

    return PaginatedHistory(
        items=response_items,
        total=len(response_items),
        page=1,
        size=limit,
    )


async def get_history_apply_context_payload(
    *,
    task_id: str,
    user_id: int,
    db,
    build_input_file_url,
    probe_media_metadata,
    logger,
) -> object:
    stmt = select(History).where(History.task_id == task_id, History.user_id == user_id)
    result = await db.execute(stmt)
    history = result.scalar_one_or_none()

    if not history:
        raise HTTPException(status_code=404, detail="未找到原任务详情")

    gallery_posts = (
        await db.execute(select(GalleryPost).where(GalleryPost.task_id == history.task_id))
    ).scalars().all()
    gallery_post = pick_preferred_gallery_post(gallery_posts)

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
        build_input_file_url=build_input_file_url,
        probe_output_file=history.output_file,
        probe_media_metadata=probe_media_metadata,
        logger=logger,
    )


def _extract_history_tags(prompt: str | None) -> list[str]:
    tags: list[str] = []
    if prompt:
        match = re.search(r"\[模型:\s*(.*?)\]", prompt)
        if match:
            tags.append(f"#{match.group(1).strip()}")
    return tags


async def get_my_favorites_payload(
    *,
    page: int,
    size: int,
    task_type: str | None,
    current_user,
    db,
    resolve_history_media_urls,
    resolve_history_billing_resolution,
) -> PaginatedGalleryResponse:
    stmt = (
        select(History)
        .where(
            History.user_id == current_user.id,
            History.is_favorited == True,
            History.is_visible.is_not(False),
        )
        .order_by(desc(History.created_at))
    )

    if task_type:
        stmt = stmt.where(History.type == task_type)

    total_query = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(total_query)).scalar()

    offset = (page - 1) * size
    stmt = stmt.offset(offset).limit(size)
    result = await db.execute(stmt)
    histories = result.scalars().all()

    task_ids = [history.task_id for history in histories if history.task_id]
    gallery_post_map: dict[str, GalleryPost] = {}
    if task_ids:
        gallery_posts = (
            await db.execute(select(GalleryPost).where(GalleryPost.task_id.in_(task_ids)))
        ).scalars().all()
        gallery_post_map = build_gallery_post_map(gallery_posts)

    url_pairs = await asyncio.gather(
        *[
            pick_history_media_urls(
                resolve_history_media_urls=resolve_history_media_urls,
                task_id=history.task_id,
                output_file=history.output_file,
                history_type=history.type,
            )
            for history in histories
        ]
    )

    response_items = []
    for history, (media_url, thumbnail_url) in zip(histories, url_pairs):
        gallery_post = gallery_post_map.get(history.task_id)
        media_type = get_media_type_from_history(history.type)
        response_items.append(
            GalleryPostResponse(
                id=history.id,
                task_id=history.task_id,
                media_type=media_type,
                billing_resolution=resolve_history_billing_resolution(
                    history, gallery_post=gallery_post
                ),
                width=history.width
                if history.width is not None
                else (gallery_post.width if gallery_post else None),
                height=history.height
                if history.height is not None
                else (gallery_post.height if gallery_post else None),
                duration=history.duration
                if history.duration is not None
                else (gallery_post.duration if gallery_post else None),
                tags=_extract_history_tags(history.prompt),
                likes_count=0,
                dislikes_count=0,
                applied_count=0,
                thumbnail_url=thumbnail_url,
                media_url=media_url,
                created_at=history.created_at,
                is_active=True,
                prompt=history.prompt,
                task_type=history.type,
                has_liked=False,
                has_disliked=False,
            )
        )

    pages = (total + size - 1) // size
    return PaginatedGalleryResponse(
        items=response_items,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )
