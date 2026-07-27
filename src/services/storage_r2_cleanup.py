import asyncio
import logging

from botocore.exceptions import ClientError
from sqlalchemy import select

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


async def async_prune_user_web_history_r2_cache(
    service,
    user_id: int,
    keep_recent: int = 8,
    async_session_factory=AsyncSessionLocal,
    async_delete_r2_objects_func=None,
) -> None:
    if not service.r2_client or not service.r2_bucket or not user_id:
        return

    async with async_session_factory() as session:
        overflow_stmt = (
            select(
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

    task_id, output_file, history_type = overflow_row
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
