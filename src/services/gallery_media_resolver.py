import asyncio
import logging

from src.media_paths import (
    build_history_r2_media_key,
    build_history_r2_thumbnail_key,
    build_flat_r2_compatibility_key,
    build_storage_r2_object_key,
    build_thumbnail_object_name,
    resolve_storage_object,
)
from src.services.r2_presign import build_r2_presigned_url
from src.services.storage import storage

logger = logging.getLogger(__name__)


def _dedupe_r2_keys(keys: list[str]) -> list[str]:
    seen: set[str] = set()
    return [key for key in keys if key and not (key in seen or seen.add(key))]


def _gallery_media_r2_key_candidates(
    *,
    output_file: str | None,
    task_id: str | None,
) -> list[str]:
    if not output_file:
        return []

    candidates = []
    if task_id:
        candidates.append(build_history_r2_media_key(task_id, output_file))
    candidates.append(build_storage_r2_object_key(output_file))
    candidates.append(output_file)
    candidates.append(build_flat_r2_compatibility_key(output_file))
    return _dedupe_r2_keys(candidates)


def _gallery_thumbnail_r2_key_candidates(
    *,
    output_file: str | None,
    media_type: str,
    task_id: str | None,
) -> list[str]:
    if not output_file:
        return []

    thumb_object_name = build_thumbnail_object_name(output_file, media_type)
    candidates = []
    if task_id:
        candidates.append(build_history_r2_thumbnail_key(task_id, media_type))
    candidates.append(build_storage_r2_object_key(thumb_object_name))
    candidates.append(thumb_object_name)
    candidates.append(build_flat_r2_compatibility_key(thumb_object_name))
    return _dedupe_r2_keys(candidates)


async def _resolve_first_gallery_r2_url(
    object_keys: list[str],
    *,
    async_r2_object_exists_fn=None,
    get_r2_public_url_fn=None,
    build_r2_presigned_url_fn=None,
) -> str:
    async_r2_object_exists_fn = (
        async_r2_object_exists_fn or storage.async_r2_object_exists
    )
    get_r2_public_url_fn = get_r2_public_url_fn or storage.get_r2_public_url
    build_r2_presigned_url_fn = build_r2_presigned_url_fn or build_r2_presigned_url

    for object_key in object_keys:
        if not await async_r2_object_exists_fn(object_key):
            continue

        presigned_url = build_r2_presigned_url_fn(object_key, expires_hours=1.0)
        if presigned_url:
            return presigned_url
        public_url = get_r2_public_url_fn(object_key) or ""
        if public_url:
            return public_url
    return ""


def build_storage_media_url(output_file: str | None) -> str:
    if not output_file:
        return ""
    bucket_name, object_name = resolve_storage_object(output_file)
    return storage.get_presigned_url(object_name, bucket=bucket_name) or ""


async def build_gallery_media_url(
    output_file: str | None,
    *,
    task_id: str | None,
    async_r2_object_exists_fn=None,
    get_r2_public_url_fn=None,
    build_r2_presigned_url_fn=None,
) -> str:
    r2_url = await _resolve_first_gallery_r2_url(
        _gallery_media_r2_key_candidates(
            output_file=output_file,
            task_id=task_id,
        ),
        async_r2_object_exists_fn=async_r2_object_exists_fn,
        get_r2_public_url_fn=get_r2_public_url_fn,
        build_r2_presigned_url_fn=build_r2_presigned_url_fn,
    )
    if r2_url:
        return r2_url

    return build_storage_media_url(output_file) or (output_file or "")


async def build_gallery_thumbnail_url(
    output_file: str | None,
    media_type: str,
    *,
    task_id: str | None,
    fast_list_mode: bool = True,
    async_r2_object_exists_fn=None,
    get_r2_public_url_fn=None,
    build_r2_presigned_url_fn=None,
    resolve_thumbnail_url_fn=None,
    async_object_exists_fn=storage.async_object_exists,
    get_presigned_url_fn=storage.get_presigned_url,
) -> str:
    r2_url = await _resolve_first_gallery_r2_url(
        _gallery_thumbnail_r2_key_candidates(
            output_file=output_file,
            media_type=media_type,
            task_id=task_id,
        ),
        async_r2_object_exists_fn=async_r2_object_exists_fn,
        get_r2_public_url_fn=get_r2_public_url_fn,
        build_r2_presigned_url_fn=build_r2_presigned_url_fn,
    )
    if r2_url:
        return r2_url

    if fast_list_mode or not output_file:
        return ""

    if resolve_thumbnail_url_fn is not None:
        return await resolve_thumbnail_url_fn(
            output_file,
            media_type,
            task_id=task_id,
            prefer_r2=False,
        )

    bucket_name, object_name = resolve_storage_object(output_file)
    thumb_object_name = build_thumbnail_object_name(object_name, media_type)
    if not await async_object_exists_fn(bucket_name, thumb_object_name):
        return ""
    return get_presigned_url_fn(thumb_object_name, bucket=bucket_name) or ""


async def pick_gallery_media_urls(
    *,
    task_id: str | None,
    output_file: str | None,
    media_type: str,
    build_media_url_fn=build_gallery_media_url,
    build_thumbnail_url_fn=build_gallery_thumbnail_url,
    resolve_gallery_media_urls_fn=None,
    logger=None,
    logger_override=None,
) -> tuple[str, str]:
    if not output_file:
        return "", ""

    active_logger = logger_override or logger or globals()["logger"]
    if resolve_gallery_media_urls_fn is not None:
        return await resolve_gallery_media_urls_fn(
            task_id=task_id,
            output_file=output_file,
            media_type=media_type,
            build_media_url=build_media_url_fn,
            build_thumbnail_url=build_thumbnail_url_fn,
            logger=active_logger,
        )

    try:
        media_url, thumbnail_url = await asyncio.gather(
            build_media_url_fn(
                output_file,
                task_id=task_id,
            ),
            build_thumbnail_url_fn(
                output_file,
                media_type,
                task_id=task_id,
            ),
        )
        return media_url or output_file, thumbnail_url
    except Exception as exc:
        active_logger.warning(
            "Failed to build gallery media URL for task_id=%s: %s",
            task_id,
            exc,
            exc_info=exc,
        )
        return output_file, ""


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
