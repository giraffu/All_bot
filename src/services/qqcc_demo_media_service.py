from __future__ import annotations

import asyncio
import copy
import hashlib
import logging
import re
from io import BytesIO
from pathlib import Path
from typing import Any

from src.services.storage import storage
from telegram import InputMediaPhoto, InputMediaVideo

logger = logging.getLogger(__name__)

QQCC_DEMO_SCENE_KINDS = frozenset({"draw", "filter", "video", "ai_video"})
QQCC_DEMO_SLOTS = frozenset({"input", "output"})
QQCC_DEMO_IMAGE_MIME_TYPES = frozenset({"image/jpeg", "image/png"})
QQCC_DEMO_VIDEO_MIME_TYPES = frozenset({"video/mp4"})
QQCC_DEMO_IMAGE_MAX_BYTES = 10 * 1024 * 1024
QQCC_DEMO_VIDEO_MAX_BYTES = 50 * 1024 * 1024
PRIVATE_QQCC_DEMO_MAX_OBJECTS = 400
PRIVATE_QQCC_DEMO_MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024


class QqccDemoMediaValidationError(ValueError):
    pass


async def clone_qqcc_config_demo_media_for_private_bot(
    config: dict[str, Any],
    *,
    private_bot_id: int,
    storage_service=storage,
) -> dict[str, Any]:
    """Clone official QQCC demo objects into an immutable tenant namespace."""

    if int(private_bot_id) <= 0:
        raise QqccDemoMediaValidationError("Invalid private Bot id")
    cloned = copy.deepcopy(config)
    media_to_copy: dict[str, str] = {}
    private_prefix = f"qqcc/private/{int(private_bot_id)}/demo/"

    for section in ("video_scenes", "ai_video_scenes", "draw_scenes", "filter_scenes"):
        for scene in cloned.get(section, []):
            for field in ("demo_input_media", "demo_output_media"):
                media = scene.get(field)
                if not isinstance(media, dict):
                    continue
                source_key = str(media.get("object_key") or "").strip()
                if not source_key:
                    continue
                if not source_key.startswith("qqcc/demo/"):
                    raise QqccDemoMediaValidationError(
                        "Official QQCC demo media has an invalid namespace"
                    )
                destination_key = private_prefix + source_key.removeprefix(
                    "qqcc/demo/"
                )
                media_to_copy[source_key] = destination_key
                media["object_key"] = destination_key
                media["telegram_file_ids"] = {}

    if not media_to_copy:
        return cloned
    if not storage_service.r2_client or not storage_service.r2_bucket:
        raise RuntimeError("R2 storage is unavailable")

    for source_key, destination_key in media_to_copy.items():
        await asyncio.to_thread(
            storage_service.r2_client.copy_object,
            Bucket=storage_service.r2_bucket,
            Key=destination_key,
            CopySource={"Bucket": storage_service.r2_bucket, "Key": source_key},
        )
        storage_service.mark_r2_object_exists(destination_key)
    return cloned


async def delete_qqcc_private_bot_demo_media(
    private_bot_id: int,
    *,
    storage_service=storage,
) -> int:
    """Delete only the deterministic demo-media namespace for one private Bot."""

    if int(private_bot_id) <= 0:
        raise QqccDemoMediaValidationError("Invalid private Bot id")
    if not storage_service.r2_client or not storage_service.r2_bucket:
        raise RuntimeError("R2 storage is unavailable")
    prefix = f"qqcc/private/{int(private_bot_id)}/demo/"

    def _delete_prefix() -> int:
        deleted = 0
        continuation_token: str | None = None
        while True:
            request: dict[str, Any] = {
                "Bucket": storage_service.r2_bucket,
                "Prefix": prefix,
                "MaxKeys": 1000,
            }
            if continuation_token:
                request["ContinuationToken"] = continuation_token
            response = storage_service.r2_client.list_objects_v2(**request)
            objects = [
                {"Key": item["Key"]}
                for item in response.get("Contents", [])
                if str(item.get("Key") or "").startswith(prefix)
            ]
            if objects:
                storage_service.r2_client.delete_objects(
                    Bucket=storage_service.r2_bucket,
                    Delete={"Objects": objects, "Quiet": True},
                )
                deleted += len(objects)
            if not response.get("IsTruncated"):
                break
            continuation_token = str(response.get("NextContinuationToken") or "")
            if not continuation_token:
                break
        return deleted

    return await asyncio.to_thread(_delete_prefix)


def resolve_qqcc_demo_media_type(*, scene_kind: str, slot: str) -> str:
    if scene_kind not in QQCC_DEMO_SCENE_KINDS or slot not in QQCC_DEMO_SLOTS:
        raise QqccDemoMediaValidationError("Unsupported scene kind or demo slot")
    return "video" if scene_kind in {"video", "ai_video"} and slot == "output" else "image"


def build_qqcc_demo_object_key(
    *,
    scene_kind: str,
    scene_id: str,
    slot: str,
    object_prefix: str = "qqcc/demo",
) -> str:
    from src.services.qqcc_config_service import VIDEO_SCENE_ID_PATTERN

    if not VIDEO_SCENE_ID_PATTERN.fullmatch(scene_id):
        raise QqccDemoMediaValidationError("Invalid scene id")
    resolve_qqcc_demo_media_type(scene_kind=scene_kind, slot=slot)
    normalized_prefix = object_prefix.strip().strip("/")
    if normalized_prefix != "qqcc/demo" and not re.fullmatch(
        r"qqcc/private/[1-9][0-9]*/demo", normalized_prefix
    ):
        raise QqccDemoMediaValidationError("Invalid demo media namespace")
    return f"{normalized_prefix}/{scene_kind}/{scene_id}/{slot}"


def _matches_file_signature(*, content: bytes, mime_type: str) -> bool:
    if mime_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if mime_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if mime_type == "video/mp4":
        return b"ftyp" in content[:32]
    return False


async def upload_qqcc_demo_media(
    *,
    scene_kind: str,
    scene_id: str,
    slot: str,
    upload,
    object_prefix: str = "qqcc/demo",
    generated_object_id: str | None = None,
    storage_service=storage,
) -> dict[str, Any]:
    media_type = resolve_qqcc_demo_media_type(scene_kind=scene_kind, slot=slot)
    mime_type = str(getattr(upload, "content_type", "") or "").lower().strip()
    allowed_mime_types = (
        QQCC_DEMO_IMAGE_MIME_TYPES
        if media_type == "image"
        else QQCC_DEMO_VIDEO_MIME_TYPES
    )
    if mime_type not in allowed_mime_types:
        raise QqccDemoMediaValidationError(
            "Input/output demo file type does not match the scene"
        )

    max_bytes = (
        QQCC_DEMO_IMAGE_MAX_BYTES
        if media_type == "image"
        else QQCC_DEMO_VIDEO_MAX_BYTES
    )
    content = await upload.read(max_bytes + 1)
    if not content or len(content) > max_bytes:
        raise QqccDemoMediaValidationError("Demo file is empty or too large")
    if not _matches_file_signature(content=content, mime_type=mime_type):
        raise QqccDemoMediaValidationError("Demo file content does not match its type")
    if not storage_service.r2_client or not storage_service.r2_bucket:
        raise RuntimeError("R2 storage is unavailable")

    object_key = build_qqcc_demo_object_key(
        scene_kind=scene_kind,
        scene_id=scene_id,
        slot=slot,
        object_prefix=object_prefix,
    )
    if generated_object_id is not None:
        normalized_generation_id = str(generated_object_id).strip()
        if slot != "output" or re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", normalized_generation_id
        ) is None:
            raise QqccDemoMediaValidationError("Invalid generated demo media id")
        object_key = (
            f"{object_prefix.strip().strip('/')}/{scene_kind}/{scene_id}/"
            f"generated/{normalized_generation_id}/output"
        )
    if object_key.startswith("qqcc/private/"):
        prefix = f"{object_prefix.strip().strip('/')}/"

        def _check_private_tenant_quota() -> None:
            object_count = 0
            total_bytes = 0
            existing_bytes = 0
            continuation_token: str | None = None
            while True:
                request: dict[str, Any] = {
                    "Bucket": storage_service.r2_bucket,
                    "Prefix": prefix,
                    "MaxKeys": 1000,
                }
                if continuation_token:
                    request["ContinuationToken"] = continuation_token
                response = storage_service.r2_client.list_objects_v2(**request)
                for item in response.get("Contents", []):
                    key = str(item.get("Key") or "")
                    if not key.startswith(prefix):
                        continue
                    size = max(0, int(item.get("Size") or 0))
                    object_count += 1
                    total_bytes += size
                    if key == object_key:
                        existing_bytes = size
                if not response.get("IsTruncated"):
                    break
                continuation_token = str(
                    response.get("NextContinuationToken") or ""
                )
                if not continuation_token:
                    break
            is_new_object = existing_bytes == 0
            if is_new_object and object_count >= PRIVATE_QQCC_DEMO_MAX_OBJECTS:
                raise QqccDemoMediaValidationError(
                    "Private Bot demo media object quota exceeded"
                )
            projected_bytes = total_bytes - existing_bytes + len(content)
            if projected_bytes > PRIVATE_QQCC_DEMO_MAX_TOTAL_BYTES:
                raise QqccDemoMediaValidationError(
                    "Private Bot demo media storage quota exceeded"
                )

        await asyncio.to_thread(_check_private_tenant_quota)
    await asyncio.to_thread(
        storage_service.r2_client.put_object,
        Bucket=storage_service.r2_bucket,
        Key=object_key,
        Body=content,
        ContentType=mime_type,
    )
    storage_service.mark_r2_object_exists(object_key)
    return {
        "object_key": object_key,
        "media_type": media_type,
        "mime_type": mime_type,
        "file_name": Path(str(getattr(upload, "filename", "") or "demo")).name[:255],
        "content_sha256": hashlib.sha256(content).hexdigest(),
        "telegram_file_ids": {},
    }


def build_qqcc_demo_preview_url(
    media: dict[str, Any] | None,
    *,
    storage_service=storage,
    expires_seconds: int = 3600,
) -> str:
    object_key = str((media or {}).get("object_key") or "").strip()
    if not object_key or not storage_service.r2_client or not storage_service.r2_bucket:
        return ""
    try:
        return storage_service.r2_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": storage_service.r2_bucket, "Key": object_key},
            ExpiresIn=expires_seconds,
        )
    except Exception:
        logger.exception("Failed to generate QQCC demo preview URL for %s", object_key)
        return ""


def _telegram_media_source(
    media: dict[str, Any],
    *,
    bot_id: str,
    prefer_cache: bool,
    preview_url_builder,
) -> str:
    if prefer_cache:
        file_ids = media.get("telegram_file_ids")
        if isinstance(file_ids, dict):
            file_id = str(file_ids.get(bot_id) or "").strip()
            if file_id:
                return file_id
    return str(preview_url_builder(media) or "").strip()


def _build_telegram_input_media(*, media: dict[str, Any], source: str):
    if media.get("media_type") == "video":
        return InputMediaVideo(media=source)
    return InputMediaPhoto(media=source)


def _extract_telegram_file_id(message, *, media_type: str) -> str:
    if media_type == "video":
        return str(getattr(getattr(message, "video", None), "file_id", "") or "")
    photos = getattr(message, "photo", None) or []
    return str(getattr(photos[-1], "file_id", "") or "") if photos else ""


async def _send_demo_items(message, items: list[tuple[str, dict[str, Any], str]]):
    if len(items) == 2:
        return await message.reply_media_group(
            media=[
                _build_telegram_input_media(media=media, source=source)
                for _slot, media, source in items
            ]
        )
    slot, media, source = items[0]
    _ = slot
    if media.get("media_type") == "video":
        sent = await message.reply_video(video=source)
    else:
        sent = await message.reply_photo(photo=source)
    return [sent]


def _read_demo_media_from_r2(media: dict[str, Any], *, storage_service) -> BytesIO:
    """Read a validated demo object for a Telegram upload fallback."""
    if not storage_service.r2_client or not storage_service.r2_bucket:
        raise RuntimeError("R2 storage is unavailable")
    media_type = str(media.get("media_type") or "")
    max_bytes = (
        QQCC_DEMO_VIDEO_MAX_BYTES if media_type == "video" else QQCC_DEMO_IMAGE_MAX_BYTES
    )
    response = storage_service.r2_client.get_object(
        Bucket=storage_service.r2_bucket,
        Key=str(media["object_key"]),
    )
    body = response.get("Body") if isinstance(response, dict) else None
    try:
        content = body.read(max_bytes + 1) if body is not None else b""
    finally:
        close = getattr(body, "close", None)
        if callable(close):
            close()
    mime_type = str(media.get("mime_type") or "").lower()
    if (
        not content
        or len(content) > max_bytes
        or not _matches_file_signature(content=content, mime_type=mime_type)
    ):
        raise QqccDemoMediaValidationError("Demo media could not be read safely")
    upload = BytesIO(content)
    upload.name = str(media.get("file_name") or "demo")
    return upload


async def send_qqcc_scene_demo_media(
    *,
    message,
    bot,
    scene_kind: str,
    scene: dict[str, Any],
    private_bot_id: int | None = None,
    preview_url_builder=build_qqcc_demo_preview_url,
    cache_file_ids_func=None,
    storage_service=storage,
) -> bool:
    descriptors: list[tuple[str, dict[str, Any]]] = []
    for slot in ("input", "output"):
        media = scene.get(f"demo_{slot}_media")
        if isinstance(media, dict) and media.get("object_key"):
            descriptors.append((slot, media))
    if not descriptors:
        return False

    bot_id = str(getattr(bot, "id", "") or "")
    has_cached_source = any(
        isinstance(media.get("telegram_file_ids"), dict)
        and bool(media["telegram_file_ids"].get(bot_id))
        for _slot, media in descriptors
    )

    async def _attempt(*, prefer_cache: bool):
        items = [
            (
                slot,
                media,
                _telegram_media_source(
                    media,
                    bot_id=bot_id,
                    prefer_cache=prefer_cache,
                    preview_url_builder=preview_url_builder,
                ),
            )
            for slot, media in descriptors
        ]
        if any(not source for _slot, _media, source in items):
            raise RuntimeError("QQCC demo media URL is unavailable")
        return items, await _send_demo_items(message, items)

    try:
        items, sent_messages = await _attempt(prefer_cache=True)
    except Exception:
        if not has_cached_source:
            logger.info("QQCC demo URL was rejected by Telegram; uploading from R2")
        else:
            logger.info("QQCC Telegram file_id cache missed; retrying demo media from R2")
            try:
                items, sent_messages = await _attempt(prefer_cache=False)
            except Exception:
                logger.info("QQCC demo URL retry was rejected by Telegram; uploading from R2")
            else:
                return await _cache_qqcc_demo_file_ids(
                    items=items,
                    sent_messages=sent_messages,
                    bot_id=bot_id,
                    scene_kind=scene_kind,
                    scene=scene,
                    private_bot_id=private_bot_id,
                    cache_file_ids_func=cache_file_ids_func,
                )
        try:
            items = [
                (
                    slot,
                    media,
                    await asyncio.to_thread(
                        _read_demo_media_from_r2,
                        media,
                        storage_service=storage_service,
                    ),
                )
                for slot, media in descriptors
            ]
            sent_messages = await _send_demo_items(message, items)
        except Exception:
            logger.exception("Failed to upload QQCC scene demo media from R2")
            return False

    return await _cache_qqcc_demo_file_ids(
        items=items,
        sent_messages=sent_messages,
        bot_id=bot_id,
        scene_kind=scene_kind,
        scene=scene,
        private_bot_id=private_bot_id,
        cache_file_ids_func=cache_file_ids_func,
    )


async def _cache_qqcc_demo_file_ids(
    *,
    items,
    sent_messages,
    bot_id: str,
    scene_kind: str,
    scene: dict[str, Any],
    private_bot_id: int | None,
    cache_file_ids_func,
) -> bool:
    cache_updates = []
    for (slot, media, _source), sent_message in zip(items, sent_messages):
        file_id = _extract_telegram_file_id(
            sent_message,
            media_type=str(media.get("media_type") or "image"),
        )
        if file_id:
            cache_updates.append(
                {
                    "slot": slot,
                    "object_key": media["object_key"],
                    "content_sha256": str(media.get("content_sha256") or ""),
                    "file_id": file_id,
                }
            )
    if cache_updates and bot_id:
        if cache_file_ids_func is None:
            from src.services.qqcc_config_service import cache_qqcc_demo_telegram_file_ids

            cache_file_ids_func = cache_qqcc_demo_telegram_file_ids
        try:
            await cache_file_ids_func(
                scene_kind=scene_kind,
                scene_id=str(scene.get("id") or ""),
                bot_id=bot_id,
                updates=cache_updates,
                private_bot_id=private_bot_id,
            )
        except Exception:
            logger.exception("Failed to persist QQCC Telegram demo file_id cache")
    return True
