from datetime import datetime

from sqlalchemy import desc, func, select

from src.database.models import GalleryPost, History, UserInteraction


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


async def fetch_recent_user_history(*, db, current_user_id: int, limit: int):
    result = await db.execute(
        select(History)
        .where(History.user_id == current_user_id)
        .order_by(desc(History.id))
        .limit(limit)
    )
    histories = result.scalars().all()
    task_ids = [h.task_id for h in histories]
    return histories, task_ids


async def fetch_active_public_gallery_task_ids(*, db, task_ids: list[str]):
    if not task_ids:
        return set()
    gallery_post_result = await db.execute(
        select(GalleryPost.task_id).where(
            GalleryPost.task_id.in_(task_ids),
            GalleryPost.is_active == True,
        )
    )
    return set(gallery_post_result.scalars().all())


async def fetch_history_apply_context_entities(*, db, task_id: str, current_user_id: int):
    history_result = await db.execute(
        select(History).where(
            History.task_id == task_id, History.user_id == current_user_id
        )
    )
    history = history_result.scalar_one_or_none()
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
        .join(GalleryPost, GalleryPost.task_id == History.task_id)
        .join(
            UserInteraction,
            (UserInteraction.post_id == GalleryPost.id)
            & (UserInteraction.action_type.in_(["like", "apply"])),
        )
        .where(
            UserInteraction.user_id == current_user_id,
            GalleryPost.is_active == True,
        )
        .distinct()
        .order_by(desc(History.id))
    )

    if task_type:
        query = query.where(History.type == task_type)

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
