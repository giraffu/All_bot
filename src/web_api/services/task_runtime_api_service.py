import logging

import httpx

from config import API_BASE
from src.circuit_breaker import CircuitBreakerOpenException
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
    get_owned_prompt_result_func=None,
) -> dict:
    if session_factory is None:
        session_factory = AsyncSessionLocal
    get_owned_active_task_func = get_owned_active_task_func or get_owned_active_task
    get_user_history_record_func = (
        get_user_history_record_func or get_user_history_record
    )
    get_task_status_func = get_task_status_func or image_service.get_task_status
    if get_owned_prompt_result_func is None:
        from src.web_api.services.prompt_result_store import get_owned_prompt_result

        get_owned_prompt_result_func = get_owned_prompt_result

    owned_active_task = await get_owned_active_task_func(task_id, user_id)
    owned_history = await get_user_history_record_func(
        task_id, user_id, session_factory
    )

    if not owned_active_task and not owned_history:
        prompt_result = await get_owned_prompt_result_func(task_id, user_id)
        if prompt_result:
            return {
                "status": (
                    "failed"
                    if prompt_result.get("status") == "failed"
                    else "success"
                ),
                "task_id": task_id,
                "task_type": "prompt_optimize",
                "media_type": None,
                **(
                    {"error": prompt_result.get("message") or "prompt optimizer failed"}
                    if prompt_result.get("status") == "failed"
                    else {}
                ),
            }
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="任务不存在或无权限")

    if owned_history and not owned_active_task:
        return build_history_task_status_payload(owned_history, task_id)

    runtime_task_id = (
        owned_active_task.get("backend_task_id")
        if owned_active_task and owned_active_task.get("backend_task_id")
        else task_id
    )
    try:
        status_data = await get_task_status_func(
            runtime_task_id,
            include_type_position=True,
        )
    except (CircuitBreakerOpenException, httpx.RequestError) as exc:
        if owned_history:
            logger.info(
                "Central status unavailable; returning persisted history "
                "task_id=%s runtime_task_id=%s error_type=%s",
                task_id,
                runtime_task_id,
                type(exc).__name__,
            )
            return build_history_task_status_payload(owned_history, task_id)
        logger.warning(
            "Central status unavailable; returning active-task fallback "
            "task_id=%s runtime_task_id=%s error_type=%s error=%s",
            task_id,
            runtime_task_id,
            type(exc).__name__,
            exc,
        )
        registry_status = owned_active_task.get("status")
        if registry_status not in {"pending", "running"}:
            registry_status = (
                "running" if owned_active_task.get("backend_task_id") else "pending"
            )
        return build_coarse_task_status_payload(
            {
                "status": registry_status,
                "task_type": owned_active_task.get("task_type"),
            },
            task_id,
        )
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
