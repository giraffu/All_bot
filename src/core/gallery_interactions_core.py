import logging
from typing import Any, Callable

from src.gallery_core_dependencies import (
    GalleryInteractionDependencies,
    get_default_gallery_interaction_dependencies,
)
from src.core.gallery_core_errors import DuplicateInteractionError, GalleryCoreError

logger = logging.getLogger(__name__)


async def toggle_like_impl(
    user_id: int,
    post_id: int,
    action: str,
    *,
    session_factory: Callable[[], Any] | None = None,
    dependencies: GalleryInteractionDependencies | None = None,
) -> dict:
    dependencies = dependencies or get_default_gallery_interaction_dependencies()
    session_factory = session_factory or dependencies.session_factory
    if action not in ["like", "dislike"]:
        raise GalleryCoreError("无效的操作类型")

    async with session_factory() as session:
        post = await dependencies.get_gallery_post_by_id_func(session, post_id)
        if not post:
            raise GalleryCoreError("帖子不存在")

        inter = await dependencies.get_gallery_reaction_interaction_func(
            session,
            user_id=user_id,
            post_id=post_id,
        )
        action_state = ""

        if inter:
            if inter.action_type == action:
                deleted_rowcount = await dependencies.remove_gallery_reaction_func(
                    session,
                    user_id=user_id,
                    post_id=post_id,
                    action=action,
                )
                if deleted_rowcount > 0:
                    updated = await dependencies.decrement_gallery_reaction_counter_func(
                        session,
                        post_id=post_id,
                        action=action,
                    )
                    post.likes_count = updated[0]
                    post.dislikes_count = updated[1]
                action_state = "canceled"
            else:
                updated = await dependencies.switch_gallery_reaction_func(
                    session,
                    post_id=post_id,
                    previous_action=inter.action_type,
                )
                post.likes_count = updated[0]
                post.dislikes_count = updated[1]
                inter.action_type = action
                action_state = "switched"
        else:
            inserted_rowcount = await dependencies.insert_gallery_reaction_if_absent_func(
                session,
                user_id=user_id,
                post_id=post_id,
                action=action,
            )
            if inserted_rowcount > 0:
                updated = await dependencies.increment_gallery_reaction_counter_func(
                    session,
                    post_id=post_id,
                    action=action,
                )
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
    dependencies: GalleryInteractionDependencies | None = None,
):
    dependencies = dependencies or get_default_gallery_interaction_dependencies()
    session_factory = session_factory or dependencies.session_factory

    async with session_factory() as session:
        try:
            inserted_rowcount = await dependencies.insert_gallery_apply_interaction_if_absent_func(
                session,
                user_id=user_id,
                post_id=post_id,
            )
            if inserted_rowcount > 0:
                await dependencies.increment_gallery_apply_counter_func(
                    session,
                    post_id=post_id,
                )
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.error(
                "Failed to record apply interaction for post %s: %s", post_id, exc
            )
