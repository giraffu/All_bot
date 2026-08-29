import asyncio
from typing import Any, Literal

from src.media_paths import (
    get_media_type_from_history,
    resolve_storage_object,
)
from src.core.media_urls import build_r2_media_key_candidates, build_r2_thumbnail_info
from src.services.r2_presign import build_r2_presigned_url
from src.services.storage import storage
from src.web_api.services.r2_public_probe_service import r2_public_probe_service
from src.services.wan22_video_v2_extension_service import (
    extract_wan22_history_context,
    is_wan22_stitched_result,
    resolve_wan22_segment_index,
)
from src.services.ltx_video_extension_service import (
    extract_ltx_history_context,
    is_ltx_video_history_task_type,
    is_ltx_stitched_result,
    resolve_ltx_segment_index,
)
from src.domain_config.wan22_aio_video import is_wan22_chain_history_task_type
from src.domain_config.minimax_h3 import MINIMAX_H3_TASK_TYPES
from src.services.minimax_h3_history_context_service import (
    extract_minimax_h3_history_context,
)
from src.services.minimax_h3_extension_service import (
    is_minimax_h3_stitched_result,
    resolve_minimax_h3_segment_index,
)


HISTORY_R2_LOOKUP_TIMEOUT_SECONDS = 2.5


async def r2_public_url_exists(
    object_key: str,
    public_url: str,
    *,
    timeout_seconds: float,
) -> bool:
    return await r2_public_probe_service.probe(
        object_key,
        public_url,
        timeout_seconds=timeout_seconds,
    )


def mark_r2_object_exists(object_key: str) -> None:
    mark_exists = getattr(storage, "mark_r2_object_exists", None)
    if callable(mark_exists):
        mark_exists(object_key)


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
            object_key,
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


async def get_first_r2_url_from_s3_cache(
    *object_keys: str,
    presigned_expires_hours: float = 1.0,
) -> str:
    for object_key in object_keys:
        if not object_key:
            continue
        if not await storage.async_r2_object_exists(object_key):
            continue
        presigned_url = build_r2_presigned_url(
            object_key,
            expires_hours=presigned_expires_hours,
        )
        if presigned_url:
            return presigned_url
        return storage.get_r2_public_url(object_key) or ""
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
    r2_lookup_strategy: Literal["public_probe", "s3_cached"] = "public_probe",
) -> str:
    if not output_file:
        return ""

    if prefer_r2:
        object_keys = build_r2_media_key_candidates(
            output_file=output_file,
            task_id=task_id,
            preferred_r2_object_name=preferred_r2_object_name,
        )
        if r2_lookup_strategy == "s3_cached":
            r2_url = await get_first_r2_url_from_s3_cache(*object_keys)
        else:
            r2_url = await get_first_r2_url_if_exists(
                *object_keys,
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
    r2_lookup_strategy: Literal["public_probe", "s3_cached"] = "public_probe",
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
        if r2_lookup_strategy == "s3_cached":
            r2_url = await get_first_r2_url_from_s3_cache(*thumb_r2_keys)
        else:
            r2_url = await get_first_r2_url_if_exists(
                *thumb_r2_keys,
                timeout_seconds=HISTORY_R2_LOOKUP_TIMEOUT_SECONDS,
                fallback_to_presigned=True,
            )
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
    r2_lookup_strategy: Literal["public_probe", "s3_cached"] = "public_probe",
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
            r2_lookup_strategy=r2_lookup_strategy,
        ),
        resolve_thumbnail_url(
            output_file,
            media_type,
            task_id=task_id,
            preferred_r2_object_name=thumbnail_preferred_r2_object_name,
            prefer_r2=prefer_r2_thumbnail,
            r2_lookup_strategy=r2_lookup_strategy,
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
    r2_lookup_strategy: Literal["public_probe", "s3_cached"] = "s3_cached",
) -> tuple[str, str]:
    media_type = get_media_type_from_history(history_type)
    return await resolve_media_and_thumbnail_urls(
        output_file,
        media_type,
        task_id=task_id,
        fallback_to_storage_path=fallback_to_storage_path,
        r2_lookup_strategy=r2_lookup_strategy,
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
    r2_lookup_strategy: Literal["public_probe", "s3_cached"] = "public_probe",
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
            r2_lookup_strategy=r2_lookup_strategy,
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
    if is_wan22_chain_history_task_type(task_type) or task_type in MINIMAX_H3_TASK_TYPES:
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
    if is_ltx_video_history_task_type(task_type):
        result_meta = extract_ltx_history_context(extra_outputs)
        if is_ltx_stitched_result(extra_outputs):
            result_meta["ltx_is_stitched"] = True
        else:
            segment_index = resolve_ltx_segment_index(extra_outputs)
            if segment_index:
                result_meta["ltx_segment_index"] = segment_index
        return result_meta
    if task_type in MINIMAX_H3_TASK_TYPES:
        context = extract_minimax_h3_history_context(extra_outputs)
        result_meta: dict[str, Any] = {}
        prev_task_id = str(context.get("prev_task_id") or "").strip()
        chain_task_ids = context.get("chain_task_ids")
        if prev_task_id:
            result_meta["minimax_h3_prev_task_id"] = prev_task_id
        if isinstance(chain_task_ids, list) and chain_task_ids:
            result_meta["minimax_h3_chain_task_ids"] = list(chain_task_ids)
        if is_minimax_h3_stitched_result(extra_outputs):
            result_meta["minimax_h3_is_stitched"] = True
            stitch = extra_outputs.get("_minimax_h3_chain_stitch") or {}
            stitched_chain = stitch.get("chain_task_ids")
            if isinstance(stitched_chain, list):
                result_meta["minimax_h3_chain_task_ids"] = list(stitched_chain)
        else:
            segment_index = resolve_minimax_h3_segment_index(extra_outputs)
            if segment_index:
                result_meta["minimax_h3_segment_index"] = segment_index
        return result_meta
    return {}
