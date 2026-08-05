import asyncio
import logging
import os
from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse

from botocore.exceptions import ClientError
from sqlalchemy import select, text

from src.core.media_paths import (
    build_history_r2_media_key,
    build_history_r2_thumbnail_key,
    build_flat_r2_compatibility_key,
    build_thumbnail_object_name,
    get_media_type_from_history,
    resolve_storage_object,
)
from src.database.core import AsyncSessionLocal
from src.database.models import History

logger = logging.getLogger(__name__)


def sync_delete_r2_object(service, object_name: str) -> bool:
    if not service.r2_client or not service.r2_bucket or not object_name:
        return False

    try:
        service.r2_client.delete_object(Bucket=service.r2_bucket, Key=object_name)
        service.invalidate_r2_exists_cache(object_name)
        logger.info("Deleted R2 object: %s", object_name)
        return True
    except ClientError as exc:
        error = exc.response.get("Error", {}) if exc.response else {}
        code = str(error.get("Code", ""))
        status_code = (
            exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if exc.response
            else None
        )
        if code in {"404", "NoSuchKey", "NotFound"} or status_code == 404:
            service.invalidate_r2_exists_cache(object_name)
            logger.info("R2 object already absent, skip delete: %s", object_name)
            return True

        logger.warning("Failed to delete R2 object %s: %s", object_name, exc)
        return False
    except Exception as exc:
        logger.warning("Failed to delete R2 object %s: %s", object_name, exc)
        return False


async def async_delete_r2_objects(service, object_names: list[str]) -> int:
    if not object_names or not service.r2_client or not service.r2_bucket:
        return 0

    deleted_count = 0
    seen = set()
    for object_name in object_names:
        if not object_name or object_name in seen:
            continue
        seen.add(object_name)
        if await asyncio.to_thread(sync_delete_r2_object, service, object_name):
            deleted_count += 1
    return deleted_count


def build_history_r2_cleanup_keys(
    task_id: str, output_file: str, history_type: str | None
) -> set[str]:
    if not task_id or not output_file:
        return set()

    media_type = get_media_type_from_history(history_type)
    _, object_name = resolve_storage_object(output_file)
    thumb_object_name = build_thumbnail_object_name(object_name, media_type)

    return {
        key
        for key in {
            build_history_r2_media_key(task_id, output_file),
            build_history_r2_thumbnail_key(task_id, media_type),
            build_flat_r2_compatibility_key(object_name),
            build_flat_r2_compatibility_key(thumb_object_name),
        }
        if key
    }


def build_archive_asset_cleanup_keys(
    task_id: str, source_ref: str, history_type: str | None, role: str
) -> set[str]:
    """Return compatibility keys for every archived role; thumbnails are output-only."""
    if not task_id or not source_ref:
        return set()
    media_type = get_media_type_from_history(history_type)
    _, object_name = resolve_storage_object(source_ref)
    parsed = urlparse(source_ref)
    raw_key = (
        unquote(parsed.path.lstrip("/"))
        if parsed.scheme in {"http", "https"}
        else source_ref.lstrip("/")
    )
    basename = PurePosixPath(raw_key).name
    keys = {
        build_history_r2_media_key(task_id, source_ref),
        build_flat_r2_compatibility_key(object_name),
        raw_key,
        basename,
        f"history/{task_id}/{basename}" if basename else "",
    }
    if role == "output":
        keys.update(
            {
                build_history_r2_thumbnail_key(task_id, media_type),
                build_flat_r2_compatibility_key(
                    build_thumbnail_object_name(object_name, media_type)
                ),
            }
        )
    return {key for key in keys if key}


def build_archive_asset_restore_keys(
    task_id: str, source_ref: str, history_type: str | None
) -> set[str]:
    """Return original-media keys only; derived thumbnails are rebuilt separately."""
    if not task_id or not source_ref:
        return set()
    _, object_name = resolve_storage_object(source_ref)
    parsed = urlparse(source_ref)
    raw_key = (
        unquote(parsed.path.lstrip("/"))
        if parsed.scheme in {"http", "https"}
        else source_ref.lstrip("/")
    )
    basename = PurePosixPath(raw_key).name
    return {
        key
        for key in {
            build_history_r2_media_key(task_id, source_ref),
            build_flat_r2_compatibility_key(object_name),
            raw_key,
            basename,
            f"history/{task_id}/{basename}" if basename else "",
        }
        if key
    }


def build_archive_thumbnail_restore_keys(
    task_id: str, source_ref: str, history_type: str | None
) -> set[str]:
    if not task_id or not source_ref:
        return set()
    media_type = get_media_type_from_history(history_type)
    _, object_name = resolve_storage_object(source_ref)
    return {
        key
        for key in {
            build_history_r2_thumbnail_key(task_id, media_type),
            build_flat_r2_compatibility_key(
                build_thumbnail_object_name(object_name, media_type)
            ),
        }
        if key
    }


async def async_prune_user_web_history_r2_cache(
    service,
    user_id: int,
    keep_recent: int = 8,
    async_session_factory=AsyncSessionLocal,
    async_delete_r2_objects_func=None,
) -> None:
    if not service.r2_client or not service.r2_bucket or not user_id:
        return
    deletion_enabled = os.getenv("R2_ARCHIVE_DELETE_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    confirmation = os.getenv("R2_ARCHIVE_DELETE_CONFIRMATION", "")
    if not deletion_enabled or confirmation != "DELETE_VERIFIED_COLD_R2":
        logger.info(
            "Incremental R2 prune disabled: archive deletion gate is closed for user %s",
            user_id,
        )
        return

    async with async_session_factory() as session:
        overflow_stmt = (
            select(
                History.id,
                History.task_id,
                History.output_file,
                History.type,
            )
            .where(
                History.user_id == user_id,
                History.source == "web",
                History.is_favorited.is_(False),
                History.is_public.is_(False),
                History.task_id.is_not(None),
                History.output_file.is_not(None),
            )
            .order_by(History.created_at.desc())
            .offset(keep_recent)
            .limit(1)
        )
        overflow_row = (await session.execute(overflow_stmt)).first()

    if not overflow_row:
        logger.info(
            "Incremental prune skipped for user %s: no overflow web history beyond %s",
            user_id,
            keep_recent,
        )
        return

    history_id, task_id, output_file, history_type = overflow_row
    async with async_session_factory() as gate_session:
        verified = (
            await gate_session.execute(
                text(
                    """select exists(
                      select 1 from media_archive_outbox o
                      join media_archive_receipts r on r.history_id=o.history_id
                      where o.history_id=:history_id and o.status='archived'
                        and r.role='output' and r.ordinal=0
                        and r.status='archived_verified' and length(r.sha256)=64
                    )"""
                ),
                {"history_id": history_id},
            )
        ).scalar()
        shared_hot_reference = (
            await gate_session.execute(
                text(
                    """with ranked as (
                      select id, row_number() over(partition by user_id order by id desc) rn from history
                    ) select exists(
                      select 1 from history h join ranked r on r.id=h.id
                      where h.id<>:history_id and h.output_file=:output_file and (
                        h.is_favorited is true or h.is_public is true
                        or (r.rn<=:keep_recent and h.is_visible is true)
                        or exists(select 1 from gallery_posts gp where gp.task_id=h.task_id and gp.is_active is true)
                      )
                    )"""
                ),
                {
                    "history_id": history_id,
                    "output_file": output_file,
                    "keep_recent": keep_recent,
                },
            )
        ).scalar()
    if not verified:
        logger.warning(
            "R2 prune blocked: History %s has no verified NAS output receipt",
            history_id,
        )
        return
    if shared_hot_reference:
        logger.warning(
            "R2 prune blocked: %s is still referenced by a hot History", output_file
        )
        return
    delete_keys = build_history_r2_cleanup_keys(task_id, output_file, history_type)

    delete_func = async_delete_r2_objects_func or async_delete_r2_objects
    deleted_count = await delete_func(service, list(delete_keys))
    logger.info(
        "Incrementally pruned user %s web history R2 cache: overflow_task=%s delete_keys=%s deleted=%s",
        user_id,
        task_id,
        len(delete_keys),
        deleted_count,
    )
