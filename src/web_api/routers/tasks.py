import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException

from src.core.task_core import (
    ConcurrencyLimitError,
    CoreDomainError,
    InsufficientCreditsError,
)
from src.database.models import User, History
from src.quota import QuotaManager
from src.services.redis_client import redis_client
from src.services.image_service import image_service
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.web_api.dependencies import get_current_user, get_current_user_once, get_db
from src.web_api.schemas.task_schema import TaskGenerateRequest, TaskGenerateResponse, TaskResultResponse
from src.web_api.services.task_result_service import get_task_result_payload
from src.web_api.services.task_submission_service import submit_generation_task
from src.web_api.services.task_stream_service import build_task_status_stream_response

router = APIRouter()
logger = logging.getLogger(__name__)
quota_manager = QuotaManager()


def _build_terminal_progress_payload(status_data: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    payload = dict(status_data)
    status_val = payload.get("status")

    if status_val == "done":
        payload["status"] = "success"
        payload["task_id"] = task_id
        payload["task_type"] = payload.get("task_type", "edit")
        return payload

    if status_val == "error":
        payload["status"] = "failed"
        payload["task_id"] = task_id
        payload["error"] = payload.get("error_msg")
        payload.pop("error_msg", None)
        return payload

    if status_val == "cancelled":
        payload["status"] = "failed"
        payload["task_id"] = task_id
        payload["error"] = payload.get("error_msg") or "任务已取消"
        payload.pop("error_msg", None)
        return payload

    return None


async def _get_user_history_record(task_id: str, user_id: int, session_factory) -> History | None:
    async with session_factory() as session:
        result = await session.execute(
            select(History).where(
                History.task_id == task_id,
                History.user_id == user_id,
            )
        )
        return result.scalars().first()


async def _get_owned_active_task(task_id: str, user_id: int) -> dict[str, Any] | None:
    tasks = await redis_client.get_active_tasks()
    task = tasks.get(task_id)
    if task and task.get("user_id") == user_id:
        return task
    return None


async def _build_not_found_progress_payload(task_id: str, user_id: int, session_factory) -> dict[str, Any]:
    history = await _get_user_history_record(task_id, user_id, session_factory)
    if history:
        return {
            "status": "success",
            "task_id": task_id,
            "task_type": history.type or "edit",
        }

    return {
        "status": "failed",
        "task_id": task_id,
        "error": "任务不存在或无权限",
    }


@router.delete("/cancel/{task_id}")
async def cancel_pending_task(task_id: str, current_user: User = Depends(get_current_user)):
    try:
        from src.core.task_core import cancel_user_task
        result = await cancel_user_task(task_id, current_user.id)
        return {
            "status": "success",
            "message": result.get("message", "取消请求已受理"),
            "cancel_state": result.get("state"),
        }
    except CoreDomainError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/generate", response_model=TaskGenerateResponse)
async def create_generation_task(
    req: TaskGenerateRequest, current_user: User = Depends(get_current_user)
):
    """
    Submit a generation task (image/video).
    """
    try:
        return await submit_generation_task(
            req=req,
            current_user=current_user,
            get_balance=quota_manager.get_credits,
        )
    except ConcurrencyLimitError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except InsufficientCreditsError as e:
        raise HTTPException(status_code=402, detail=str(e))
    except CoreDomainError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Task submission error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{task_id}/result", response_model=TaskResultResponse)
async def get_task_result(
    task_id: str, 
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get task generation result directly.
    """
    return await get_task_result_payload(
        task_id=task_id,
        current_user=current_user,
        db=db,
    )


@router.get("/{task_id}/stream")
async def task_status_stream(
    task_id: str,
    current_user: User = Depends(get_current_user_once),
):
    """
    SSE Endpoint for real-time task progress tracking.
    Listens to Redis Pub/Sub channel: comfy:task_events:{task_id}
    Also periodically sends queue position while pending.
    """
    from src.database.core import AsyncSessionLocal
    user_id = current_user.id

    owned_active_task = await _get_owned_active_task(task_id, user_id)
    owned_history = await _get_user_history_record(task_id, user_id, AsyncSessionLocal)
    if not owned_active_task and not owned_history:
        raise HTTPException(status_code=404, detail="任务不存在或无权限")
    from config import API_BASE

    return build_task_status_stream_response(
        task_id=task_id,
        user_id=user_id,
        session_factory=AsyncSessionLocal,
        redis=redis_client.redis,
        api_base=API_BASE,
        httpx_async_client_factory=httpx.AsyncClient,
        logger=logger,
        build_not_found_progress_payload=_build_not_found_progress_payload,
        build_terminal_progress_payload=_build_terminal_progress_payload,
    )


@router.get("/queue-status")
async def get_queue_status(_current_user: User = Depends(get_current_user)) -> dict:
    """获取当前系统的排队宏观大盘数据"""
    status = await image_service.get_queue_info()
    if not status:
        return {"comfy_online": False, "queue_size": 0, "queue_by_type": {}}
    return status
