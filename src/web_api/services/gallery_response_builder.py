import asyncio
import json
import logging

from sqlalchemy import select

from src.database.models import History, User, UserInteraction
from src.lora_mapping import translate_tags
from src.web_api.common.utils import resolve_history_billing_resolution
from src.web_api.schemas.gallery_schema import GalleryPostResponse
from src.web_api.services.gallery_media_resolver import resolve_gallery_post_media_urls

logger = logging.getLogger(__name__)


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

    user_likes = set()
    user_dislikes = set()
    if current_user and post_ids:
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
        for inter in interactions:
            if inter.action_type == "like":
                user_likes.add(inter.post_id)
            elif inter.action_type == "dislike":
                user_dislikes.add(inter.post_id)

    history_map = {}
    if task_ids:
        histories = (
            (await session.execute(select(History).where(History.task_id.in_(task_ids))))
            .scalars()
            .all()
        )
        history_map = {h.task_id: h for h in histories}

    user_ids = list(set([p.user_id for p in posts if p.user_id]))
    user_map = {}
    if user_ids:
        users = (
            (await session.execute(select(User).where(User.id.in_(user_ids))))
            .scalars()
            .all()
        )
        for user in users:
            user_map[user.id] = resolve_author_name(user, user.id)

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
        translated_tags = translate_tags_func(tags)

        history = history_map.get(post.task_id)
        prompt = history.prompt if history else None
        task_type_from_history = history.type if history else None

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
                has_liked=post.id in user_likes,
                has_disliked=post.id in user_dislikes,
                author_name=user_map.get(post.user_id)
                if post.user_id
                else resolve_author_name(None),
            )
        )
    return response_items


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
