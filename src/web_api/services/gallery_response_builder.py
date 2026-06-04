import asyncio
import json
import logging

from sqlalchemy import select

from src.database.models import History, User, UserFollow, UserInteraction
from src.lora_mapping import translate_tags
from src.services.wan22_video_v2_extension_service import (
    extract_wan22_history_context,
    is_wan22_stitched_result,
    resolve_wan22_segment_index,
    resolve_wan22_stitched_segment_count,
)
from src.services.wan22_video_v2_config import is_wan22_chain_history_task_type
from src.web_api.common.utils import resolve_history_billing_resolution
from src.web_api.presenters.media_presenter import extract_history_result_meta
from src.web_api.schemas.gallery_schema import GalleryPostResponse
from src.web_api.services.apply_context_service import (
    resolve_history_template_apply_disabled_reason,
)
from src.web_api.services.gallery_media_resolver import resolve_gallery_post_media_urls

logger = logging.getLogger(__name__)


def _append_history_mode_tags(
    *,
    tags: list[str],
    history: History | None,
) -> list[str]:
    if not history or not is_wan22_chain_history_task_type(history.type):
        return tags
    if is_wan22_stitched_result(getattr(history, "extra_outputs", None)):
        segment_count = resolve_wan22_stitched_segment_count(
            getattr(history, "extra_outputs", None)
        )
        if segment_count:
            stitched_tag = f"task.wan22_stitched_video:{segment_count}"
            if stitched_tag not in tags:
                return [*tags, stitched_tag]
        return tags

    result_meta = extract_wan22_history_context(getattr(history, "extra_outputs", None))
    mode_tag = (
        "task.wan22_start_end_frame"
        if bool(result_meta.get("wan22_use_end_frame"))
        else "task.wan22_start_frame"
    )
    next_tags = tags if mode_tag in tags else [*tags, mode_tag]
    segment_index = resolve_wan22_segment_index(getattr(history, "extra_outputs", None))
    if segment_index:
        segment_tag = f"task.wan22_segment:{segment_index}"
        if segment_tag not in next_tags:
            next_tags = [*next_tags, segment_tag]
    return next_tags


def resolve_gallery_author_name(
    user: User | None,
    fallback_user_id: int | None = None,
) -> str:
    if user:
        return user.full_name or user.username or f"User {user.id}"
    if fallback_user_id is not None:
        return f"User {fallback_user_id}"
    return "匿名修士"


async def build_post_responses(
    *,
    session,
    posts,
    current_user,
    translate_tags_func,
    resolve_history_billing_resolution_func,
    resolve_author_name,
    pick_gallery_media_urls_func,
    logger_override,
    gallery_post_response_cls,
) -> list:
    if not posts:
        return []

    post_ids = [p.id for p in posts]
    task_ids = [p.task_id for p in posts if p.task_id]

    user_likes, user_dislikes = await _load_user_reactions(
        session=session,
        current_user=current_user,
        post_ids=post_ids,
    )
    history_map = await _load_history_map(session=session, task_ids=task_ids)
    user_ids = list({p.user_id for p in posts if p.user_id})
    user_map = await _load_user_map(session=session, user_ids=user_ids)
    following_user_ids = await _load_following_user_ids(
        session=session,
        current_user=current_user,
        user_ids=user_ids,
    )

    tasks = []
    for post in posts:
        history = history_map.get(post.task_id)
        output_file = history.output_file if history else None
        tasks.append(
            pick_gallery_media_urls_func(
                task_id=post.task_id,
                output_file=output_file,
                media_type=post.media_type,
            )
        )
    urls_results = await asyncio.gather(*tasks, return_exceptions=True)

    response_items = []
    for index, post in enumerate(posts):
        try:
            tags = json.loads(post.tags) if post.tags else []
        except Exception:
            tags = []

        history = history_map.get(post.task_id)
        tags = _append_history_mode_tags(tags=tags, history=history)
        translated_tags = translate_tags_func(tags)
        prompt = history.prompt if history else None
        task_type_from_history = history.type if history else None
        result_meta = extract_history_result_meta(
            task_type=task_type_from_history,
            extra_outputs=getattr(history, "extra_outputs", None),
        )
        template_apply_disabled_reason = (
            resolve_history_template_apply_disabled_reason(history)
        )

        url_result = urls_results[index]
        if isinstance(url_result, Exception):
            logger_override.warning(
                "Failed to build gallery media URLs for post_id=%s task_id=%s: %s",
                post.id,
                post.task_id,
                url_result,
                exc_info=url_result,
            )
            media_url = history.output_file if history and history.output_file else ""
            thumbnail_url = ""
        else:
            media_url, thumbnail_url = url_result

        billing_resolution = None
        if history:
            billing_resolution = resolve_history_billing_resolution_func(
                history,
                width=post.width if post.width is not None else history.width,
                height=post.height if post.height is not None else history.height,
                gallery_post=post,
            )

        response_items.append(
            gallery_post_response_cls(
                id=post.id,
                task_id=post.task_id,
                media_type=post.media_type,
                billing_resolution=billing_resolution,
                width=post.width,
                height=post.height,
                duration=post.duration,
                tags=translated_tags,
                likes_count=post.likes_count,
                dislikes_count=post.dislikes_count,
                applied_count=post.applied_count,
                comments_count=post.comments_count or 0,
                thumbnail_url=thumbnail_url,
                media_url=media_url,
                created_at=post.created_at,
                is_active=post.is_active,
                prompt=prompt,
                task_type=task_type_from_history,
                result_meta=result_meta,
                template_apply_supported=template_apply_disabled_reason is None,
                template_apply_disabled_reason=template_apply_disabled_reason,
                has_liked=post.id in user_likes,
                has_disliked=post.id in user_dislikes,
                author_id=post.user_id,
                author_name=resolve_author_name(user_map.get(post.user_id), post.user_id)
                if post.user_id
                else resolve_author_name(None),
                author_username=user_map.get(post.user_id).username
                if post.user_id and user_map.get(post.user_id)
                else None,
                is_following_author=post.user_id in following_user_ids
                if post.user_id
                else False,
            )
        )
    return response_items


async def _load_user_reactions(*, session, current_user, post_ids: list[int]) -> tuple[set[int], set[int]]:
    user_likes: set[int] = set()
    user_dislikes: set[int] = set()
    if not current_user or not post_ids:
        return user_likes, user_dislikes

    interactions = (
        (
            await session.execute(
                select(UserInteraction)
                .where(UserInteraction.user_id == current_user.id)
                .where(UserInteraction.post_id.in_(post_ids))
                .where(UserInteraction.action_type.in_(["like", "dislike"]))
            )
        )
        .scalars()
        .all()
    )
    for interaction in interactions:
        if interaction.action_type == "like":
            user_likes.add(interaction.post_id)
        elif interaction.action_type == "dislike":
            user_dislikes.add(interaction.post_id)
    return user_likes, user_dislikes


async def _load_history_map(*, session, task_ids: list[str]) -> dict[str, History]:
    if not task_ids:
        return {}
    histories = (
        (await session.execute(select(History).where(History.task_id.in_(task_ids))))
        .scalars()
        .all()
    )
    return {history.task_id: history for history in histories}


async def _load_user_map(*, session, user_ids: list[int]) -> dict[int, User]:
    if not user_ids:
        return {}
    users = (
        (await session.execute(select(User).where(User.id.in_(user_ids))))
        .scalars()
        .all()
    )
    return {user.id: user for user in users}


async def _load_following_user_ids(
    *,
    session,
    current_user,
    user_ids: list[int],
) -> set[int]:
    if not current_user or not user_ids:
        return set()
    follow_links = (
        (
            await session.execute(
                select(UserFollow.followee_id).where(
                    UserFollow.follower_id == current_user.id,
                    UserFollow.followee_id.in_(user_ids),
                )
            )
        )
        .scalars()
        .all()
    )
    return set(follow_links)


async def build_gallery_post_responses(
    *,
    session,
    posts,
    current_user,
    gallery_post_response_cls=GalleryPostResponse,
    pick_gallery_media_urls=resolve_gallery_post_media_urls,
) -> list:
    return await build_post_responses(
        session=session,
        posts=posts,
        current_user=current_user,
        translate_tags_func=translate_tags,
        resolve_history_billing_resolution_func=resolve_history_billing_resolution,
        resolve_author_name=resolve_gallery_author_name,
        pick_gallery_media_urls_func=pick_gallery_media_urls,
        logger_override=logger,
        gallery_post_response_cls=gallery_post_response_cls,
    )
