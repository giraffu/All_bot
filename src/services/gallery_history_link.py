from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import and_, or_, select

from src.database.models import GalleryPost, History
from src.services.compat_telemetry import record_compat_hit


def gallery_history_join_condition():
    """Return the canonical ownership-safe GalleryPost -> History join."""

    return and_(
        GalleryPost.user_id == History.user_id,
        or_(
            and_(
                GalleryPost.history_id.is_not(None),
                GalleryPost.history_id == History.id,
            ),
            and_(
                GalleryPost.history_id.is_(None),
                GalleryPost.task_id == History.task_id,
            ),
        ),
    )


def gallery_history_condition_for_post(post):
    """Match one post to its History without crossing an owner boundary."""

    history_id = getattr(post, "history_id", None)
    if history_id is not None:
        return and_(History.id == history_id, History.user_id == post.user_id)

    record_compat_hit(
        "compat.gallery.history_owner_fallback",
        entrypoint="gallery history lookup",
    )
    return and_(History.task_id == post.task_id, History.user_id == post.user_id)


def select_gallery_history_for_post(post):
    return (
        select(History)
        .where(gallery_history_condition_for_post(post))
        .order_by(History.id.desc())
    )


async def load_gallery_history_map(*, session, posts: Iterable) -> dict[int, History]:
    """Load the preferred History for each post, keyed by GalleryPost.id."""

    posts = list(posts)
    if not posts:
        return {}

    direct_pairs = {
        (post.history_id, post.user_id)
        for post in posts
        if getattr(post, "history_id", None) is not None
        and getattr(post, "user_id", None) is not None
    }
    legacy_pairs = {
        (post.task_id, post.user_id)
        for post in posts
        if getattr(post, "history_id", None) is None
        and getattr(post, "task_id", None)
        and getattr(post, "user_id", None) is not None
    }

    conditions = []
    if direct_pairs:
        conditions.extend(
            and_(History.id == history_id, History.user_id == user_id)
            for history_id, user_id in direct_pairs
        )
    if legacy_pairs:
        record_compat_hit(
            "compat.gallery.history_owner_fallback",
            entrypoint="gallery bulk history lookup",
        )
        conditions.extend(
            and_(History.task_id == task_id, History.user_id == user_id)
            for task_id, user_id in legacy_pairs
        )
    if not conditions:
        return {}

    histories = (
        (
            await session.execute(
                select(History).where(or_(*conditions)).order_by(History.id.desc())
            )
        )
        .scalars()
        .all()
    )
    by_id = {history.id: history for history in histories}
    by_owner_task: dict[tuple[str, int], History] = {}
    for history in histories:
        by_owner_task.setdefault((history.task_id, history.user_id), history)

    resolved: dict[int, History] = {}
    for post in posts:
        history_id = getattr(post, "history_id", None)
        history = by_id.get(history_id) if history_id is not None else None
        if history is not None and history.user_id != post.user_id:
            history = None
        if history is None and history_id is None:
            history = by_owner_task.get((post.task_id, post.user_id))
        if history is not None:
            resolved[post.id] = history
    return resolved
