import logging

import httpx
from fastapi import APIRouter, Depends

from src.database.models import User
from src.quota import QuotaManager
from src.services.redis_client import redis_client
from src.services.image_service import image_service
from sqlalchemy.ext.asyncio import AsyncSession
from src.web_api.dependencies import get_current_user, get_current_user_once, get_db
from src.web_api.schemas.task_schema import TaskGenerateRequest, TaskGenerateResponse, TaskResultResponse
from src.web_api.services.task_result_service import get_task_result_payload
from src.web_api.services.task_action_api_service import (
    cancel_pending_task_payload,
    submit_generation_task_payload,
)
from src.web_api.services.task_stream_api_service import (
    build_task_stream_response_payload,
)

router = APIRouter()
logger = logging.getLogger(__name__)
quota_manager = QuotaManager()


@router.delete("/cancel/{task_id}")
async def cancel_pending_task(task_id: str, current_user: User = Depends(get_current_user)):
    return await cancel_pending_task_payload(task_id=task_id, user_id=current_user.id)

@router.post("/generate", response_model=TaskGenerateResponse)
async def create_generation_task(
    req: TaskGenerateRequest, current_user: User = Depends(get_current_user)
):
    """
    Submit a generation task (image/video).
    """
    return await submit_generation_task_payload(
        req=req,
        current_user=current_user,
        get_balance=quota_manager.get_credits,
        logger=logger,
    )


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
    from config import API_BASE

    return await build_task_stream_response_payload(
        task_id=task_id,
        user_id=current_user.id,
        session_factory=AsyncSessionLocal,
        redis=redis_client.redis,
        api_base=API_BASE,
        httpx_async_client_factory=httpx.AsyncClient,
        logger=logger,
    )


@router.get("/queue-status")
async def get_queue_status(_current_user: User = Depends(get_current_user)) -> dict:
    """获取当前系统的排队宏观大盘数据"""
    status = await image_service.get_queue_info()
    if not status:
        return {"comfy_online": False, "queue_size": 0, "queue_by_type": {}}
    return status
