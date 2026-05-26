from fastapi import HTTPException
from sqlalchemy import select

from src.constants import VIDEO_TASK_TYPES
from src.core.media_urls import build_r2_media_key_candidates
from src.database.models import History
from src.web_api.presenters.media_presenter import (
    build_storage_media_url,
    get_first_r2_url_if_exists,
)


async def _resolve_task_result_url(hist: History) -> str:
    if not hist.output_file:
        return ""

    if hist.source == "web":
        r2_url = await get_first_r2_url_if_exists(
            *build_r2_media_key_candidates(
                output_file=hist.output_file,
                task_id=hist.task_id,
            )
        )
        return r2_url or ""

    return (
        build_storage_media_url(
            hist.output_file,
            expires_hours=24,
        )
        or hist.output_file
    )


async def get_task_result_payload(*, task_id: str, current_user, db) -> dict:
    hist = (
        (
            await db.execute(
                select(History).where(
                    History.task_id == task_id,
                    History.user_id == current_user.id,
                )
            )
        )
        .scalars()
        .first()
    )

    if not hist:
        return {
            "status": "pending_result",
            "task_id": task_id,
            "task_type": None,
            "media_type": None,
        }

    if hist.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="任务不存在或无权限")

    is_video = hist.type in VIDEO_TASK_TYPES if hist.type else False
    media_type = "video" if is_video else "image"

    if hist.output_file:
        result_url = await _resolve_task_result_url(hist)
        if not result_url:
            return {
                "status": "pending_result",
                "task_id": task_id,
                "task_type": hist.type,
                "media_type": media_type,
            }
        return {
            "status": "success",
            "task_id": task_id,
            "task_type": hist.type,
            "media_type": media_type,
            "result_url": result_url,
        }

    return {
        "status": "pending_result",
        "task_id": task_id,
        "task_type": hist.type,
        "media_type": media_type,
    }
