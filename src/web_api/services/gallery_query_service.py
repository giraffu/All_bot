from sqlalchemy import desc, exists, func, select

from src.database.models import GalleryPost, GalleryPromptUnlock, History, UserInteraction


async def fetch_my_gallery_posts_page(
    *,
    db,
    current_user_id: int,
    page: int,
    size: int,
    task_type: str | None,
):
    query = (
        select(GalleryPost)
        .outerjoin(History, GalleryPost.task_id == History.task_id)
        .where(GalleryPost.user_id == current_user_id, History.is_visible.is_not(False))
        .distinct()
    )

    if task_type:
        query = query.where(History.type == task_type)

    query = query.order_by(desc(GalleryPost.id))
    total_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(total_query)).scalar()

    offset = (page - 1) * size
    posts = (await db.execute(query.offset(offset).limit(size))).scalars().all()
    return posts, total


async def fetch_my_favorite_posts_page(
    *,
    db,
    current_user_id: int,
    page: int,
    size: int,
    filter_type: str,
    task_type: str | None,
):
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
            UserInteraction.user_id == current_user_id,
            UserInteraction.action_type.in_(action_types),
            GalleryPost.is_active.is_(True),
        )
        .distinct()
        .order_by(desc(GalleryPost.id))
    )

    if task_type:
        query = query.where(History.type == task_type)

    total_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(total_query)).scalar()
    offset = (page - 1) * size
    posts = (await db.execute(query.offset(offset).limit(size))).scalars().all()
    return posts, total


async def fetch_my_prompt_unlocked_posts_page(
    *,
    db,
    current_user_id: int,
    page: int,
    size: int,
    task_type: str | None,
):
    query = (
        select(GalleryPost)
        .join(GalleryPromptUnlock, GalleryPost.id == GalleryPromptUnlock.post_id)
        .where(
            GalleryPromptUnlock.user_id == current_user_id,
            GalleryPost.is_active.is_(True),
        )
        .order_by(desc(GalleryPromptUnlock.created_at), desc(GalleryPost.id))
    )

    if task_type:
        query = query.where(
            exists(
                select(1).where(
                    History.task_id == GalleryPost.task_id,
                    History.type == task_type,
                )
            )
        )

    total_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(total_query)).scalar()
    offset = (page - 1) * size
    posts = (await db.execute(query.offset(offset).limit(size))).scalars().all()
    return posts, total


async def fetch_gallery_apply_context_entities(*, db, post_id: int):
    post = (
        await db.execute(select(GalleryPost).where(GalleryPost.id == post_id))
    ).scalar_one_or_none()
    if not post:
        return None, None

    history = (
        await db.execute(select(History).where(History.task_id == post.task_id))
    ).scalars().first()
    return post, history
