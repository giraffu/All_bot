import asyncio

from src.core.media_paths import get_media_type_from_history, resolve_storage_object
from src.core.media_urls import build_r2_media_key_candidates, build_r2_thumbnail_info
from src.services.storage import storage


async def get_r2_url_if_exists(object_key: str) -> str:
    public_url = storage.get_r2_public_url(object_key)
    if not public_url:
        return ""
    if await storage.async_r2_object_exists(object_key):
        return public_url
    return ""


async def get_first_r2_url_if_exists(*object_keys: str) -> str:
    for object_key in object_keys:
        if not object_key:
            continue
        url = await get_r2_url_if_exists(object_key)
        if url:
            return url
    return ""


def build_storage_media_url(
    output_file: str | None,
    *,
    expires_hours: int | None = None,
) -> str:
    if not output_file:
        return ""

    bucket_name, object_name = resolve_storage_object(output_file)
    kwargs = {"bucket": bucket_name}
    if expires_hours is not None:
        kwargs["expires_hours"] = expires_hours
    return storage.get_presigned_url(object_name, **kwargs) or ""


async def resolve_media_url(
    output_file: str | None,
    *,
    task_id: str | None = None,
    preferred_r2_object_name: str | None = None,
    prefer_r2: bool = True,
    expires_hours: int | None = None,
    fallback_to_storage_path: bool = False,
) -> str:
    if not output_file:
        return ""

    if prefer_r2:
        r2_url = await get_first_r2_url_if_exists(
            *build_r2_media_key_candidates(
                output_file=output_file,
                task_id=task_id,
                preferred_r2_object_name=preferred_r2_object_name,
            )
        )
        if r2_url:
            return r2_url

    storage_url = build_storage_media_url(output_file, expires_hours=expires_hours)
    if storage_url:
        return storage_url
    return output_file if fallback_to_storage_path else ""


async def resolve_thumbnail_url(
    output_file: str | None,
    media_type: str,
    *,
    task_id: str | None = None,
    preferred_r2_object_name: str | None = None,
    prefer_r2: bool = True,
) -> str:
    if not output_file:
        return ""

    thumb_file, thumb_r2_keys = build_r2_thumbnail_info(
        output_file=output_file,
        media_type=media_type,
        task_id=task_id,
        preferred_r2_object_name=preferred_r2_object_name,
    )
    if not thumb_file:
        return ""

    if prefer_r2:
        r2_url = await get_first_r2_url_if_exists(*thumb_r2_keys)
        if r2_url:
            return r2_url

    bucket_name, object_name = resolve_storage_object(thumb_file)
    if await storage.async_object_exists(bucket_name, object_name):
        return storage.get_presigned_url(object_name, bucket=bucket_name) or ""
    return ""


async def resolve_media_and_thumbnail_urls(
    output_file: str | None,
    media_type: str,
    *,
    task_id: str | None = None,
    media_preferred_r2_object_name: str | None = None,
    thumbnail_preferred_r2_object_name: str | None = None,
    prefer_r2_media: bool = True,
    prefer_r2_thumbnail: bool = True,
    fallback_to_storage_path: bool = False,
) -> tuple[str, str]:
    if not output_file:
        return "", ""

    media_url, thumbnail_url = await asyncio.gather(
        resolve_media_url(
            output_file,
            task_id=task_id,
            preferred_r2_object_name=media_preferred_r2_object_name,
            prefer_r2=prefer_r2_media,
            fallback_to_storage_path=fallback_to_storage_path,
        ),
        resolve_thumbnail_url(
            output_file,
            media_type,
            task_id=task_id,
            preferred_r2_object_name=thumbnail_preferred_r2_object_name,
            prefer_r2=prefer_r2_thumbnail,
        ),
    )
    return media_url, thumbnail_url


async def resolve_gallery_media_urls(
    *,
    task_id: str | None,
    output_file: str | None,
    media_type: str,
    build_media_url,
    build_thumbnail_url,
    logger,
) -> tuple[str, str]:
    if not output_file:
        return "", ""

    try:
        media_url, thumbnail_url = await asyncio.gather(
            build_media_url(
                output_file,
                task_id=task_id,
            ),
            build_thumbnail_url(
                output_file,
                media_type,
                task_id=task_id,
            ),
        )
        return media_url or output_file, thumbnail_url
    except Exception as exc:
        logger.warning(
            "Failed to build gallery media URL for task_id=%s: %s",
            task_id,
            exc,
            exc_info=exc,
        )
        return output_file, ""


async def resolve_history_media_urls(
    *,
    task_id: str | None,
    output_file: str | None,
    history_type: str | None,
    fallback_to_storage_path: bool = False,
) -> tuple[str, str]:
    media_type = get_media_type_from_history(history_type)
    return await resolve_media_and_thumbnail_urls(
        output_file,
        media_type,
        task_id=task_id,
        fallback_to_storage_path=fallback_to_storage_path,
    )
