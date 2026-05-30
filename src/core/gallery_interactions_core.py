import logging
from typing import Any, Callable

from src.core.gallery_core_dependencies import get_gallery_session_factory
from src.core.gallery_core_errors import DuplicateInteractionError, GalleryCoreError
from src.services.gallery_repository import (
    decrement_gallery_reaction_counter,
    get_gallery_post_by_id,
    get_gallery_reaction_interaction,
    increment_gallery_apply_counter,
    increment_gallery_reaction_counter,
    insert_gallery_apply_interaction_if_absent,
    insert_gallery_reaction_if_absent,
    remove_gallery_reaction,
    switch_gallery_reaction,
)

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
        post = await get_gallery_post_by_id(session, post_id)
        if not post:
            raise GalleryCoreError("帖子不存在")

        inter = await get_gallery_reaction_interaction(
            session,
            user_id=user_id,
            post_id=post_id,
        )
        action_state = ""

        if inter:
            if inter.action_type == action:
                deleted_rowcount = await remove_gallery_reaction(
                    session,
                    user_id=user_id,
                    post_id=post_id,
                    action=action,
                )
                if deleted_rowcount > 0:
                    updated = await decrement_gallery_reaction_counter(
                        session,
                        post_id=post_id,
                        action=action,
                    )
                    post.likes_count = updated[0]
                    post.dislikes_count = updated[1]
                action_state = "canceled"
            else:
                updated = await switch_gallery_reaction(
                    session,
                    post_id=post_id,
                    previous_action=inter.action_type,
                    next_action=action,
                )
                post.likes_count = updated[0]
                post.dislikes_count = updated[1]
                inter.action_type = action
                action_state = "switched"
        else:
            inserted_rowcount = await insert_gallery_reaction_if_absent(
                session,
                user_id=user_id,
                post_id=post_id,
                action=action,
            )
            if inserted_rowcount > 0:
                updated = await increment_gallery_reaction_counter(
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
):
    session_factory = session_factory or get_gallery_session_factory()

    async with session_factory() as session:
        try:
            inserted_rowcount = await insert_gallery_apply_interaction_if_absent(
                session,
                user_id=user_id,
                post_id=post_id,
            )
            if inserted_rowcount > 0:
                await increment_gallery_apply_counter(session, post_id=post_id)
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.error(
                "Failed to record apply interaction for post %s: %s", post_id, exc
            )
