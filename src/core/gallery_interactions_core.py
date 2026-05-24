import logging
from typing import Any, Callable

from sqlalchemy import delete, func, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select

from src.database.models import GalleryPost, UserInteraction
from src.core.gallery_core_dependencies import get_gallery_session_factory
from src.core.gallery_core_errors import DuplicateInteractionError, GalleryCoreError

logger = logging.getLogger(__name__)


async def toggle_like_impl(
    user_id: int,
    post_id: int,
    action: str,
    *,
    session_factory: Callable[[], Any] | None = None,
) -> dict:
    session_factory = session_factory or get_gallery_session_factory()
    if action not in ["like", "dislike"]:
        raise GalleryCoreError("无效的操作类型")

    async with session_factory() as session:
        post = await session.get(GalleryPost, post_id)
        if not post:
            raise GalleryCoreError("帖子不存在")

        existing_inter = await session.execute(
            select(UserInteraction).where(
                UserInteraction.user_id == user_id,
                UserInteraction.post_id == post_id,
                UserInteraction.action_type.in_(["like", "dislike"]),
            )
        )
        inter = existing_inter.scalars().first()
        action_state = ""

        if inter:
            if inter.action_type == action:
                stmt_del = delete(UserInteraction).where(
                    UserInteraction.user_id == user_id,
                    UserInteraction.post_id == post_id,
                    UserInteraction.action_type == action,
                )
                res_del = await session.execute(stmt_del)
                if res_del.rowcount > 0:
                    counter_field = (
                        GalleryPost.likes_count
                        if action == "like"
                        else GalleryPost.dislikes_count
                    )
                    res = await session.execute(
                        update(GalleryPost)
                        .where(GalleryPost.id == post_id)
                        .values(likes_count=GalleryPost.likes_count, dislikes_count=GalleryPost.dislikes_count)
                        .values(
                            **{
                                (
                                    "likes_count"
                                    if action == "like"
                                    else "dislikes_count"
                                ): func.greatest(counter_field - 1, 0)
                            }
                        )
                        .returning(GalleryPost.likes_count, GalleryPost.dislikes_count)
                    )
                    updated = res.fetchone()
                    post.likes_count = updated[0]
                    post.dislikes_count = updated[1]
                action_state = "canceled"
            else:
                stmt = (
                    update(GalleryPost)
                    .where(GalleryPost.id == post_id)
                    .values(
                        likes_count=(
                            func.greatest(GalleryPost.likes_count - 1, 0)
                            if inter.action_type == "like"
                            else GalleryPost.likes_count + 1
                        ),
                        dislikes_count=(
                            GalleryPost.dislikes_count + 1
                            if inter.action_type == "like"
                            else func.greatest(GalleryPost.dislikes_count - 1, 0)
                        ),
                    )
                    .returning(GalleryPost.likes_count, GalleryPost.dislikes_count)
                )
                res = await session.execute(stmt)
                updated = res.fetchone()
                post.likes_count = updated[0]
                post.dislikes_count = updated[1]
                inter.action_type = action
                action_state = "switched"
        else:
            result = await session.execute(
                insert(UserInteraction)
                .values(user_id=user_id, post_id=post_id, action_type=action)
                .on_conflict_do_nothing()
            )
            if result.rowcount > 0:
                counter_name = "likes_count" if action == "like" else "dislikes_count"
                res = await session.execute(
                    update(GalleryPost)
                    .where(GalleryPost.id == post_id)
                    .values(
                        **{
                            counter_name: getattr(GalleryPost, counter_name) + 1,
                        }
                    )
                    .returning(GalleryPost.likes_count, GalleryPost.dislikes_count)
                )
                updated = res.fetchone()
                post.likes_count = updated[0]
                post.dislikes_count = updated[1]
                action_state = "added"
            else:
                raise DuplicateInteractionError("您已经进行过此操作啦！")

        await session.commit()
        return {
            "likes_count": post.likes_count,
            "dislikes_count": post.dislikes_count,
            "action_state": action_state,
        }


async def record_apply_interaction_impl(
    user_id: int,
    post_id: int,
    *,
    session_factory: Callable[[], Any] | None = None,
):
    session_factory = session_factory or get_gallery_session_factory()

    async with session_factory() as session:
        try:
            result = await session.execute(
                insert(UserInteraction)
                .values(user_id=user_id, post_id=post_id, action_type="apply")
                .on_conflict_do_nothing()
            )
            if result.rowcount > 0:
                await session.execute(
                    update(GalleryPost)
                    .where(GalleryPost.id == post_id)
                    .values(applied_count=GalleryPost.applied_count + 1)
                )
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.error(
                "Failed to record apply interaction for post %s: %s", post_id, exc
            )
