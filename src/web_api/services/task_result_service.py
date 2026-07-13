import asyncio
import copy
import logging
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select

from src.constants import VIDEO_TASK_TYPES
from src.core.task_status_mapper import (
    build_result_pending_payload,
    build_result_success_payload,
)
from src.core.media_urls import build_r2_media_key_candidates
from src.database.models import History
from src.web_api.presenters.media_presenter import (
    build_r2_presigned_url,
    build_storage_media_url,
    extract_history_result_meta,
    filter_user_visible_extra_outputs,
    get_first_r2_url_if_exists,
    resolve_history_extra_outputs,
)
from src.services.storage import storage

WEB_RESULT_STORAGE_FALLBACK_EXPIRES_HOURS = 1
WEB_RESULT_R2_LOOKUP_TIMEOUT_SECONDS = 2.5
WEB_RESULT_R2_S3_FALLBACK_TIMEOUT_SECONDS = 1.0
WEB_RESULT_EXTRA_OUTPUTS_TIMEOUT_SECONDS = 5.0


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _HistorySnapshot:
    user_id: int
    task_id: str
    type: str | None
    output_file: str | None
    source: str | None
    extra_outputs: dict[str, Any] | None


def _snapshot_history(hist: History) -> _HistorySnapshot:
    extra_outputs = (
        copy.deepcopy(hist.extra_outputs)
        if isinstance(hist.extra_outputs, dict)
        else None
    )
    return _HistorySnapshot(
        user_id=hist.user_id,
        task_id=hist.task_id,
        type=hist.type,
        output_file=hist.output_file,
        source=hist.source,
        extra_outputs=extra_outputs,
    )


async def _release_read_transaction(db) -> None:
    in_transaction = getattr(db, "in_transaction", None)
    if callable(in_transaction):
        try:
            if not in_transaction():
                return
        except Exception:
            pass

    rollback = getattr(db, "rollback", None)
    if not callable(rollback):
        return

    try:
        await rollback()
    except Exception as exc:
        logger.warning("Failed to release task result read transaction: %s", exc)


async def _resolve_web_r2_url(hist: _HistorySnapshot) -> str:
    object_keys = build_r2_media_key_candidates(
        output_file=hist.output_file,
        task_id=hist.task_id,
    )
    try:
        public_url = await asyncio.wait_for(
            get_first_r2_url_if_exists(
                *object_keys,
                timeout_seconds=WEB_RESULT_R2_LOOKUP_TIMEOUT_SECONDS,
                fallback_to_presigned=False,
            ),
            timeout=WEB_RESULT_R2_LOOKUP_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Timed out resolving web result R2 URL for task_id=%s",
            hist.task_id,
        )
    else:
        if public_url:
            return public_url

    return await _resolve_web_r2_presigned_url_from_s3(object_keys)


async def _resolve_web_r2_presigned_url_from_s3(object_keys: list[str]) -> str:
    valid_object_keys = [object_key for object_key in object_keys if object_key]
    if not valid_object_keys:
        return ""

    exists_results = await asyncio.gather(
        *(
            _web_r2_object_exists_with_timeout(object_key)
            for object_key in valid_object_keys
        )
    )
    for object_key, exists in zip(valid_object_keys, exists_results):
        if not exists:
            continue
        presigned_url = build_r2_presigned_url(
            object_key,
            expires_hours=WEB_RESULT_STORAGE_FALLBACK_EXPIRES_HOURS,
        )
        if presigned_url:
            return presigned_url
    return ""


async def _web_r2_object_exists_with_timeout(object_key: str) -> bool:
    try:
        return await asyncio.wait_for(
            storage.async_r2_object_exists(object_key),
            timeout=WEB_RESULT_R2_S3_FALLBACK_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return False
    except Exception as exc:
        logger.warning(
            "Failed to verify web result R2 object via S3 key=%s: %s",
            object_key,
            exc,
        )
        return False


async def _resolve_task_result_url(hist: _HistorySnapshot, *, media_type: str) -> str:
    if not hist.output_file:
        return ""

    if hist.source == "web":
        r2_url = await _resolve_web_r2_url(hist)
        if r2_url:
            return r2_url

        if media_type == "video":
            return ""

        return build_storage_media_url(
            hist.output_file,
            expires_hours=WEB_RESULT_STORAGE_FALLBACK_EXPIRES_HOURS,
        )

    return (
        build_storage_media_url(
            hist.output_file,
            expires_hours=24,
        )
        or hist.output_file
    )


async def _resolve_visible_extra_outputs(hist: _HistorySnapshot) -> dict[str, dict[str, Any]]:
    try:
        extra_outputs = await asyncio.wait_for(
            resolve_history_extra_outputs(
                task_id=hist.task_id,
                extra_outputs=hist.extra_outputs,
                source=hist.source,
            ),
            timeout=WEB_RESULT_EXTRA_OUTPUTS_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Timed out resolving task result extra outputs for task_id=%s",
            hist.task_id,
        )
        extra_outputs = {}
    return filter_user_visible_extra_outputs(
        task_type=hist.type,
        extra_outputs=extra_outputs,
    )


async def get_task_result_payload(*, task_id: str, current_user, db) -> dict:
    user_id = current_user.id
    hist = (
        (
            await db.execute(
                select(History).where(
                    History.task_id == task_id,
                    History.user_id == user_id,
                )
            )
        )
        .scalars()
        .first()
    )

    if not hist:
        await _release_read_transaction(db)
        return build_result_pending_payload(
            task_id=task_id,
            task_type=None,
            media_type=None,
        )

    hist_snapshot = _snapshot_history(hist)
    await _release_read_transaction(db)

    if hist_snapshot.user_id != user_id:
        raise HTTPException(status_code=403, detail="任务不存在或无权限")

    is_video = hist_snapshot.type in VIDEO_TASK_TYPES if hist_snapshot.type else False
    media_type = "video" if is_video else "image"

    if hist_snapshot.output_file:
        result_url = await _resolve_task_result_url(
            hist_snapshot,
            media_type=media_type,
        )
        if not result_url:
            return build_result_pending_payload(
                task_id=task_id,
                task_type=hist_snapshot.type,
                media_type=media_type,
            )
        visible_extra_outputs = await _resolve_visible_extra_outputs(hist_snapshot)
        return build_result_success_payload(
            task_id=task_id,
            task_type=hist_snapshot.type,
            media_type=media_type,
            result_url=result_url,
            extra_outputs=visible_extra_outputs,
            result_meta=extract_history_result_meta(
                task_type=hist_snapshot.type,
                extra_outputs=hist_snapshot.extra_outputs,
            ),
        )

    return build_result_pending_payload(
        task_id=task_id,
        task_type=hist_snapshot.type,
        media_type=media_type,
    )
