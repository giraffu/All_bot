import logging

import httpx

from config import API_BASE
from src.database.core import AsyncSessionLocal
from src.services.image_service import image_service
from src.services.redis_client import redis_client
from src.web_api.services.task_stream_api_service import (
    build_coarse_task_status_payload,
    build_history_task_status_payload,
    build_not_found_task_status_payload,
    build_task_stream_response_payload,
    get_owned_active_task,
    get_user_history_record,
)

logger = logging.getLogger(__name__)


async def build_task_status_stream_response_for_user(
    *,
    task_id: str,
    user_id: int,
    session_factory=None,
    redis=None,
    api_base: str = API_BASE,
    httpx_async_client_factory=httpx.AsyncClient,
    logger_override: logging.Logger | None = None,
):
    if session_factory is None:
        session_factory = AsyncSessionLocal
    if redis is None:
        redis = redis_client.redis

    return await build_task_stream_response_payload(
        task_id=task_id,
        user_id=user_id,
        session_factory=session_factory,
        redis=redis,
        api_base=api_base,
        httpx_async_client_factory=httpx_async_client_factory,
        logger=logger_override or logger,
    )


async def get_task_status_payload_for_user(
    *,
    task_id: str,
    user_id: int,
    session_factory=None,
    get_owned_active_task_func=None,
    get_user_history_record_func=None,
    get_task_status_func=None,
) -> dict:
    if session_factory is None:
        session_factory = AsyncSessionLocal
    get_owned_active_task_func = get_owned_active_task_func or get_owned_active_task
    get_user_history_record_func = (
        get_user_history_record_func or get_user_history_record
    )
    get_task_status_func = get_task_status_func or image_service.get_task_status

    owned_active_task = await get_owned_active_task_func(task_id, user_id)
    owned_history = await get_user_history_record_func(
        task_id, user_id, session_factory
    )

    if not owned_active_task and not owned_history:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="任务不存在或无权限")

    if owned_history and not owned_active_task:
        return build_history_task_status_payload(owned_history, task_id)

    runtime_task_id = (
        owned_active_task.get("backend_task_id")
        if owned_active_task and owned_active_task.get("backend_task_id")
        else task_id
    )
    status_data = await get_task_status_func(runtime_task_id)
    if not status_data:
        if owned_history:
            return build_history_task_status_payload(owned_history, task_id)
        return build_not_found_task_status_payload(task_id)

    return build_coarse_task_status_payload(status_data, task_id)


async def get_queue_status_payload(
    *,
    get_queue_info_func=None,
) -> dict:
    if get_queue_info_func is None:
        get_queue_info_func = image_service.get_queue_info

    status = await get_queue_info_func()
    if not status:
        return {"comfy_online": False, "queue_size": 0, "queue_by_type": {}}
    return status
