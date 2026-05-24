import re

from src.web_api.common.utils import resolve_history_billing_resolution
from src.web_api.presenters.media_presenter import resolve_history_media_urls
from src.web_api.schemas.gallery_schema import GalleryPostResponse
from src.web_api.schemas.user_schema import HistoryItem


def extract_history_tags(prompt: str | None) -> list[str]:
    tags: list[str] = []
    if prompt:
        match = re.search(r"\\[模型:\\s*(.*?)\\]", prompt)
        if match:
            tags.append(f"#{match.group(1).strip()}")
    return tags


async def build_user_history_payload(
    *,
    histories,
    gallery_task_ids: set[str],
    resolve_history_media_urls_func=resolve_history_media_urls,
):
    items = []
    for history in histories:
        media_url, thumbnail_url = await resolve_history_media_urls_func(history)
        items.append(
            HistoryItem(
                task_id=history.task_id,
                type=history.type,
                prompt=history.prompt,
                id=history.id,
                input_file=history.input_file,
                output_file=history.output_file,
                output_file_url=media_url,
                thumbnail_url=thumbnail_url,
                created_at=history.created_at,
                is_public=history.task_id in gallery_task_ids,
                billing_resolution=resolve_history_billing_resolution(history),
                width=history.width,
                height=history.height,
                duration=history.duration,
                allow_contribute=history.allow_contribute,
                source=history.source,
                is_favorited=history.is_favorited,
            )
        )
    return items


async def build_favorite_gallery_payload(
    *,
    histories,
    gallery_post_map: dict[str, object],
    resolve_history_media_urls_func=resolve_history_media_urls,
):
    items = []
    for history in histories:
        gallery_post = gallery_post_map.get(history.task_id)
        media_url, thumbnail_url = await resolve_history_media_urls_func(history)
        items.append(
            GalleryPostResponse(
                id=gallery_post.id if gallery_post else 0,
                task_id=history.task_id,
                media_type=(gallery_post.media_type if gallery_post else "image"),
                billing_resolution=resolve_history_billing_resolution(
                    history,
                    width=gallery_post.width if gallery_post else None,
                    height=gallery_post.height if gallery_post else None,
                    gallery_post=gallery_post,
                ),
                width=gallery_post.width if gallery_post else history.width,
                height=gallery_post.height if gallery_post else history.height,
                duration=gallery_post.duration if gallery_post else history.duration,
                tags=extract_history_tags(history),
                likes_count=gallery_post.likes_count if gallery_post else 0,
                dislikes_count=gallery_post.dislikes_count if gallery_post else 0,
                applied_count=gallery_post.applied_count if gallery_post else 0,
                comments_count=gallery_post.comments_count if gallery_post else 0,
                thumbnail_url=thumbnail_url,
                media_url=media_url,
                created_at=history.created_at,
                is_active=gallery_post.is_active if gallery_post else False,
                prompt=history.prompt,
                task_type=history.type,
                has_liked=False,
                has_disliked=False,
                author_name="我",
            )
        )
    return items
