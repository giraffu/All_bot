import asyncio
from typing import Any

import httpx

from src.core.media_paths import (
    get_media_type_from_history,
    resolve_legacy_storage_object,
    resolve_storage_object,
)
from src.core.media_urls import build_r2_media_key_candidates, build_r2_thumbnail_info
from src.services.storage import storage
from src.services.wan22_video_v2_extension_service import (
    extract_wan22_history_context,
    is_wan22_stitched_result,
    resolve_wan22_segment_index,
)
from src.domain_config.wan22_aio_video import is_wan22_chain_history_task_type


HISTORY_R2_LOOKUP_TIMEOUT_SECONDS = 2.5


async def r2_public_url_exists(
    public_url: str,
    *,
    timeout_seconds: float,
) -> bool:
    if not public_url:
        return False

    request_timeout = httpx.Timeout(
        timeout_seconds,
        connect=min(timeout_seconds, 1.0),
    )
    try:
        async with httpx.AsyncClient(timeout=request_timeout, trust_env=False) as client:
            response = await client.head(public_url, follow_redirects=True)
            if response.status_code == 405:
                response = await client.get(
                    public_url,
                    headers={"Range": "bytes=0-0"},
                    follow_redirects=True,
                )
    except httpx.HTTPError:
        return False

    return response.status_code in {200, 204, 206, 301, 302, 304}


def mark_r2_object_exists(object_key: str) -> None:
    mark_exists = getattr(storage, "mark_r2_object_exists", None)
    if callable(mark_exists):
        mark_exists(object_key)


def build_r2_presigned_url(
    object_key: str,
    *,
    expires_hours: float = 1.0,
) -> str:
    r2_client = getattr(storage, "r2_client", None)
    r2_bucket = getattr(storage, "r2_bucket", None)
    if not r2_client or not r2_bucket:
        return ""
    try:
        return (
            r2_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": r2_bucket, "Key": object_key},
                ExpiresIn=int(expires_hours * 3600),
            )
            or ""
        )
    except Exception:
        return ""


async def get_r2_url_if_exists(
    object_key: str,
    *,
    timeout_seconds: float | None = None,
    fallback_to_presigned: bool = False,
    presigned_expires_hours: float = 1.0,
) -> str:
    public_url = storage.get_r2_public_url(object_key)
    if not public_url:
        return ""

    if timeout_seconds:
        if await r2_public_url_exists(
            public_url,
            timeout_seconds=timeout_seconds,
        ):
            mark_r2_object_exists(object_key)
            return public_url
        if fallback_to_presigned and await storage.async_r2_object_exists(object_key):
            return build_r2_presigned_url(
                object_key,
                expires_hours=presigned_expires_hours,
            )
        return ""

    exists_coro = storage.async_r2_object_exists(object_key)
    try:
        exists = (
            await asyncio.wait_for(exists_coro, timeout=timeout_seconds)
            if timeout_seconds
            else await exists_coro
        )
    except asyncio.TimeoutError:
        return ""
    if exists:
        return public_url
    return ""


async def get_first_r2_url_if_exists(
    *object_keys: str,
    timeout_seconds: float | None = None,
    fallback_to_presigned: bool = False,
    presigned_expires_hours: float = 1.0,
) -> str:
    for object_key in object_keys:
        if not object_key:
            continue
        url = await get_r2_url_if_exists(
            object_key,
            timeout_seconds=timeout_seconds,
            fallback_to_presigned=fallback_to_presigned,
            presigned_expires_hours=presigned_expires_hours,
        )
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

    legacy_url = build_legacy_storage_media_url(
        output_file,
        expires_hours=expires_hours,
    )
    if legacy_url:
        return legacy_url

    bucket_name, object_name = resolve_storage_object(output_file)
    kwargs = {"bucket": bucket_name}
    if expires_hours is not None:
        kwargs["expires_hours"] = expires_hours
    return storage.get_presigned_url(object_name, **kwargs) or ""


def build_legacy_storage_media_url(
    output_file: str | None,
    *,
    expires_hours: int | None = None,
) -> str:
    if not output_file:
        return ""

    has_legacy_storage = getattr(storage, "has_legacy_storage_configured", None)
    if not callable(has_legacy_storage) or not has_legacy_storage():
        return ""

    legacy_bucket, legacy_object = resolve_legacy_storage_object(output_file)
    legacy_exists = getattr(storage, "legacy_object_exists", None)
    if callable(legacy_exists) and not legacy_exists(legacy_bucket, legacy_object):
        return ""

    kwargs = {"bucket": legacy_bucket}
    if expires_hours is not None:
        kwargs["expires_hours"] = expires_hours
    return storage.get_legacy_presigned_url(legacy_object, **kwargs) or ""


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
            ),
            timeout_seconds=HISTORY_R2_LOOKUP_TIMEOUT_SECONDS,
            fallback_to_presigned=True,
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
        r2_url = await get_first_r2_url_if_exists(
            *thumb_r2_keys,
            timeout_seconds=HISTORY_R2_LOOKUP_TIMEOUT_SECONDS,
            fallback_to_presigned=True,
        )
        if r2_url:
            return r2_url

    has_legacy_storage = getattr(storage, "has_legacy_storage_configured", None)
    if callable(has_legacy_storage) and has_legacy_storage():
        legacy_bucket, legacy_object = resolve_legacy_storage_object(thumb_file)
        legacy_exists = getattr(storage, "async_legacy_object_exists", None)
        if callable(legacy_exists) and await legacy_exists(
            legacy_bucket,
            legacy_object,
        ):
            return (
                storage.get_legacy_presigned_url(
                    legacy_object,
                    bucket=legacy_bucket,
                )
                or ""
            )

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


def _infer_extra_output_media_type(item: dict[str, Any]) -> str:
    media_type = item.get("media_type")
    if media_type in {"image", "video"}:
        return media_type

    path = str(item.get("path") or "").lower()
    if path.endswith((".mp4", ".mov", ".webm", ".mkv", ".avi")):
        return "video"
    return "image"


async def resolve_history_extra_outputs(
    *,
    task_id: str | None,
    extra_outputs: dict[str, Any] | None,
    source: str | None,
) -> dict[str, dict[str, Any]]:
    if not isinstance(extra_outputs, dict):
        return {}

    resolved: dict[str, dict[str, Any]] = {}
    for key, value in extra_outputs.items():
        if not isinstance(value, dict):
            continue
        output_path = value.get("path")
        if not isinstance(output_path, str) or not output_path:
            continue
        media_type = _infer_extra_output_media_type(value)
        url = await resolve_media_url(
            output_path,
            task_id=task_id,
            prefer_r2=(source == "web"),
            expires_hours=None if source == "web" else 24,
            fallback_to_storage_path=True,
        )
        resolved[key] = {
            **value,
            "media_type": media_type,
            "url": url or output_path,
        }
    return resolved


def filter_user_visible_extra_outputs(
    *,
    task_type: str | None,
    extra_outputs: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    if not isinstance(extra_outputs, dict):
        return {}
    if is_wan22_chain_history_task_type(task_type):
        last_frame = extra_outputs.get("last_frame")
        return {"last_frame": last_frame} if isinstance(last_frame, dict) else {}
    return extra_outputs


def extract_history_result_meta(
    *,
    task_type: str | None,
    extra_outputs: dict[str, Any] | None,
) -> dict[str, Any]:
    if is_wan22_chain_history_task_type(task_type):
        result_meta = extract_wan22_history_context(extra_outputs)
        if is_wan22_stitched_result(extra_outputs):
            result_meta["wan22_is_stitched"] = True
        else:
            segment_index = resolve_wan22_segment_index(extra_outputs)
            if segment_index:
                result_meta["wan22_segment_index"] = segment_index
        return result_meta
    return {}
