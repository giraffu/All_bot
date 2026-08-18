from __future__ import annotations

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert

from src.database.core import AsyncSessionLocal
from src.database.models import GalleryPost, History, User, UserInteraction
from src.services.media_archive_service import enqueue_history_media_restore


async def get_gallery_post_by_id(session, post_id: int):
    return await session.get(GalleryPost, post_id)


async def acquire_gallery_reaction_lock(session, *, user_id: int, post_id: int) -> None:
    bind = session.get_bind() if hasattr(session, "get_bind") else None
    if getattr(getattr(bind, "dialect", None), "name", None) != "postgresql":
        return
    await session.execute(
        text(
            "SELECT pg_advisory_xact_lock("
            "hashtextextended(:reaction_owner, 0))"
        ),
        {"reaction_owner": f"gallery-reaction:{user_id}:{post_id}"},
    )


async def acquire_gallery_submission_lock(
    session,
    *,
    user_id: int,
    task_id: str,
) -> None:
    bind = session.get_bind() if hasattr(session, "get_bind") else None
    if getattr(getattr(bind, "dialect", None), "name", None) != "postgresql":
        return
    await session.execute(
        text(
            "SELECT pg_advisory_xact_lock("
            "hashtextextended(:submission_owner, 0))"
        ),
        {"submission_owner": f"gallery-submit:{user_id}:{task_id}"},
    )


async def get_gallery_post_by_task_id(session, task_id: str):
    return (
        (
            await session.execute(select(GalleryPost).where(GalleryPost.task_id == task_id))
        )
        .scalars()
        .first()
    )


async def get_gallery_history_for_user_task(session, *, task_id: str, user_id: int):
    return (
        (
            await session.execute(
                select(History).where(History.task_id == task_id).where(History.user_id == user_id)
            )
        )
        .scalars()
        .first()
    )


async def get_gallery_user(session, user_id: int):
    return (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()


async def reactivate_gallery_post_for_owner(
    session,
    *,
    existing_post,
    history,
    user,
):
    existing_post.is_active = True
    if history:
        history.is_public = True
        await enqueue_history_media_restore(session, history, priority=0)
    if user:
        user.total_contributions = (user.total_contributions or 0) + 1
    await session.commit()


async def create_gallery_post_from_history(
    session,
    *,
    task_id: str,
    user_id: int,
    media_type: str,
    width: int | None,
    height: int | None,
    duration: int | None,
    tags_json: str,
    history,
    user,
):
    result = await session.execute(
        insert(GalleryPost)
        .values(
            task_id=task_id,
            user_id=user_id,
            media_type=media_type,
            width=width,
            height=height,
            duration=duration,
            tags=tags_json,
        )
        .on_conflict_do_nothing(
            index_elements=[GalleryPost.task_id, GalleryPost.user_id]
        )
        .returning(GalleryPost.id)
    )
    created_post_id = result.scalar_one_or_none()
    if created_post_id is None:
        await session.rollback()
        return "duplicate"
    if user:
        user.total_contributions = (user.total_contributions or 0) + 1
    history.is_public = True
    await enqueue_history_media_restore(session, history, priority=0)
    await session.commit()
    return "created"


async def get_gallery_reaction_interaction(session, *, user_id: int, post_id: int):
    existing_inter = await session.execute(
        select(UserInteraction).where(
            UserInteraction.user_id == user_id,
            UserInteraction.post_id == post_id,
            UserInteraction.action_type.in_(["like", "dislike"]),
        )
    )
    return existing_inter.scalars().first()


async def remove_gallery_reaction(session, *, user_id: int, post_id: int, action: str):
    res_del = await session.execute(
        delete(UserInteraction).where(
            UserInteraction.user_id == user_id,
            UserInteraction.post_id == post_id,
            UserInteraction.action_type == action,
        )
    )
    return res_del.rowcount


async def decrement_gallery_reaction_counter(
    session,
    *,
    post_id: int,
    action: str,
):
    counter_field = GalleryPost.likes_count if action == "like" else GalleryPost.dislikes_count
    counter_name = "likes_count" if action == "like" else "dislikes_count"
    res = await session.execute(
        update(GalleryPost)
        .where(GalleryPost.id == post_id)
        .values(likes_count=GalleryPost.likes_count, dislikes_count=GalleryPost.dislikes_count)
        .values(**{counter_name: func.greatest(counter_field - 1, 0)})
        .returning(GalleryPost.likes_count, GalleryPost.dislikes_count)
    )
    return res.fetchone()


async def switch_gallery_reaction(
    session,
    *,
    post_id: int,
    previous_action: str,
):
    res = await session.execute(
        update(GalleryPost)
        .where(GalleryPost.id == post_id)
        .values(
            likes_count=(
                func.greatest(GalleryPost.likes_count - 1, 0)
                if previous_action == "like"
                else GalleryPost.likes_count + 1
            ),
            dislikes_count=(
                GalleryPost.dislikes_count + 1
                if previous_action == "like"
                else func.greatest(GalleryPost.dislikes_count - 1, 0)
            ),
        )
        .returning(GalleryPost.likes_count, GalleryPost.dislikes_count)
    )
    return res.fetchone()


async def insert_gallery_reaction_if_absent(
    session,
    *,
    user_id: int,
    post_id: int,
    action: str,
):
    result = await session.execute(
        insert(UserInteraction)
        .values(user_id=user_id, post_id=post_id, action_type=action)
        .on_conflict_do_nothing(
            index_elements=[UserInteraction.user_id, UserInteraction.post_id],
            index_where=UserInteraction.action_type.in_(["like", "dislike"]),
        )
    )
    return result.rowcount


async def increment_gallery_reaction_counter(
    session,
    *,
    post_id: int,
    action: str,
):
    counter_name = "likes_count" if action == "like" else "dislikes_count"
    res = await session.execute(
        update(GalleryPost)
        .where(GalleryPost.id == post_id)
        .values(**{counter_name: getattr(GalleryPost, counter_name) + 1})
        .returning(GalleryPost.likes_count, GalleryPost.dislikes_count)
    )
    return res.fetchone()


async def insert_gallery_apply_interaction_if_absent(
    session,
    *,
    user_id: int,
    post_id: int,
):
    result = await session.execute(
        insert(UserInteraction)
        .values(user_id=user_id, post_id=post_id, action_type="apply")
        .on_conflict_do_nothing(
            index_elements=[UserInteraction.user_id, UserInteraction.post_id],
            index_where=UserInteraction.action_type == "apply",
        )
    )
    return result.rowcount


async def increment_gallery_apply_counter(session, *, post_id: int):
    await session.execute(
        update(GalleryPost)
        .where(GalleryPost.id == post_id)
        .values(applied_count=GalleryPost.applied_count + 1)
    )


async def mark_history_public_by_task_id(
    task_id: str,
    *,
    session_factory=None,
) -> None:
    if session_factory is None:
        session_factory = AsyncSessionLocal
    async with session_factory() as session:
        await session.execute(
            update(History).where(History.task_id == task_id).values(is_public=True)
        )
        await session.commit()


async def update_history_rating_by_task_id(
    task_id: str,
    rating_value: int,
    *,
    session_factory=None,
) -> None:
    if session_factory is None:
        session_factory = AsyncSessionLocal
    async with session_factory() as session:
        await session.execute(
            update(History).where(History.task_id == task_id).values(rating=rating_value)
        )
        await session.commit()
