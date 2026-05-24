import logging

from src.core.media_paths import build_thumbnail_object_name, resolve_storage_object
from src.services.storage import storage
from src.web_api.presenters.media_presenter import (
    resolve_gallery_media_urls as presenter_resolve_gallery_media_urls,
)
from src.web_api.presenters.media_presenter import resolve_media_url, resolve_thumbnail_url

logger = logging.getLogger(__name__)


async def build_gallery_media_url(
    output_file: str | None,
    *,
    task_id: str | None,
    resolve_media_url_fn=resolve_media_url,
) -> str:
    return await resolve_media_url_fn(
        output_file,
        task_id=task_id,
        fallback_to_storage_path=True,
    )


async def build_gallery_thumbnail_url(
    output_file: str | None,
    media_type: str,
    *,
    task_id: str | None,
    resolve_thumbnail_url_fn=resolve_thumbnail_url,
    resolve_storage_object_fn=resolve_storage_object,
    build_thumbnail_object_name_fn=build_thumbnail_object_name,
    async_object_exists_fn=storage.async_object_exists,
    get_presigned_url_fn=storage.get_presigned_url,
) -> str:
    thumbnail_url = await resolve_thumbnail_url_fn(
        output_file,
        media_type,
        task_id=task_id,
    )
    if thumbnail_url:
        return thumbnail_url

    if not output_file:
        return ""

    bucket_name, object_name = resolve_storage_object_fn(output_file)
    thumb_object_name = build_thumbnail_object_name_fn(object_name, media_type)
    if not await async_object_exists_fn(bucket_name, thumb_object_name):
        return ""
    return get_presigned_url_fn(thumb_object_name, bucket=bucket_name) or ""


async def pick_gallery_media_urls(
    *,
    task_id: str | None,
    output_file: str | None,
    media_type: str,
    resolve_gallery_media_urls_fn=presenter_resolve_gallery_media_urls,
    build_media_url_fn=build_gallery_media_url,
    build_thumbnail_url_fn=build_gallery_thumbnail_url,
    logger=None,
) -> tuple[str, str]:
    return await resolve_gallery_media_urls_fn(
        task_id=task_id,
        output_file=output_file,
        media_type=media_type,
        build_media_url=build_media_url_fn,
        build_thumbnail_url=build_thumbnail_url_fn,
        logger=logger or globals()["logger"],
    )


async def resolve_gallery_post_media_urls(
    *,
    task_id: str | None,
    output_file: str | None,
    media_type: str,
) -> tuple[str, str]:
    return await pick_gallery_media_urls(
        task_id=task_id,
        output_file=output_file,
        media_type=media_type,
    )
