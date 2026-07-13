from datetime import datetime

from sqlalchemy import desc, func, select

from src.database.models import GalleryPost, History
from src.services.gallery_feed_queries import resolve_gallery_task_type_filter_values


def gallery_post_sort_key(post):
    created_at = getattr(post, "created_at", None) or datetime.min
    return (
        1 if getattr(post, "is_active", False) else 0,
        created_at,
        getattr(post, "id", 0) or 0,
    )


def pick_preferred_gallery_post(posts):
    preferred = None
    for post in posts:
        if post is None:
            continue
        if preferred is None or gallery_post_sort_key(post) > gallery_post_sort_key(
            preferred
        ):
            preferred = post
    return preferred


def build_gallery_post_map(posts):
    posts_by_task_id: dict[str, list] = {}
    for post in posts:
        posts_by_task_id.setdefault(post.task_id, []).append(post)
    return {
        task_id: pick_preferred_gallery_post(task_posts)
        for task_id, task_posts in posts_by_task_id.items()
    }


def history_sort_key(history):
    created_at = getattr(history, "created_at", None) or datetime.min
    return (
        1 if getattr(history, "is_visible", True) else 0,
        1 if getattr(history, "output_file", None) else 0,
        1 if getattr(history, "is_favorited", False) else 0,
        created_at,
        getattr(history, "id", 0) or 0,
    )


def pick_preferred_history(histories):
    preferred = None
    for history in histories:
        if history is None:
            continue
        if preferred is None or history_sort_key(history) > history_sort_key(preferred):
            preferred = history
    return preferred


async def fetch_recent_user_history(*, db, current_user_id: int, limit: int):
    result = await db.execute(
        select(History)
        .where(History.user_id == current_user_id)
        .order_by(desc(History.id))
        .limit(limit)
    )
    # 闪回瓶容量按“最近 N 条原始记录”计算；已删除项只是不展示，不用更旧记录补位。
    histories = [history for history in result.scalars().all() if history.is_visible]
    task_ids = [h.task_id for h in histories]
    return histories, task_ids


async def fetch_active_public_gallery_task_ids(*, db, task_ids: list[str]):
    if not task_ids:
        return set()
    gallery_post_result = await db.execute(
        select(GalleryPost.task_id).where(
            GalleryPost.task_id.in_(task_ids),
            GalleryPost.is_active.is_(True),
        )
    )
    return set(gallery_post_result.scalars().all())


async def fetch_owned_histories_by_task_id(*, db, task_id: str, current_user_id: int):
    history_result = await db.execute(
        select(History)
        .where(History.task_id == task_id, History.user_id == current_user_id)
        .order_by(desc(History.id))
    )
    return history_result.scalars().all()


async def fetch_history_apply_context_entities(*, db, task_id: str, current_user_id: int):
    histories = await fetch_owned_histories_by_task_id(
        db=db,
        task_id=task_id,
        current_user_id=current_user_id,
    )
    history = pick_preferred_history(histories)
    if not history:
        return None, None

    gallery_post_result = await db.execute(
        select(GalleryPost).where(GalleryPost.task_id == task_id)
    )
    posts = gallery_post_result.scalars().all()
    gallery_post = pick_preferred_gallery_post(posts)
    return history, gallery_post


async def fetch_favorite_gallery_histories(
    *,
    db,
    current_user_id: int,
    page: int,
    size: int,
    task_type: str | None,
):
    query = (
        select(History)
        .where(
            History.user_id == current_user_id,
            History.is_favorited.is_(True),
            History.is_visible.is_(True),
        )
        .order_by(desc(History.id))
    )

    if task_type:
        task_type_values = resolve_gallery_task_type_filter_values(task_type)
        if task_type_values:
            if len(task_type_values) == 1:
                query = query.where(History.type == task_type_values[0])
            else:
                query = query.where(History.type.in_(task_type_values))

    total_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(total_query)).scalar()
    offset = (page - 1) * size
    result = await db.execute(query.offset(offset).limit(size))
    histories = result.scalars().all()
    return histories, total


async def fetch_gallery_posts_for_task_ids(*, db, task_ids: list[str]):
    if not task_ids:
        return {}
    result = await db.execute(select(GalleryPost).where(GalleryPost.task_id.in_(task_ids)))
    return build_gallery_post_map(result.scalars().all())


async def fetch_owned_histories_by_task_ids(
    *,
    db,
    task_ids: list[str],
    current_user_id: int,
):
    if not task_ids:
        return []
    result = await db.execute(
        select(History).where(
            History.task_id.in_(task_ids),
            History.user_id == current_user_id,
        )
    )
    return [history for history in result.scalars().all() if history.is_visible]
