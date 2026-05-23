import logging

import httpx

from config import API_BASE
from src.database.core import AsyncSessionLocal
from src.services.image_service import image_service
from src.services.redis_client import redis_client
from src.web_api.services.task_stream_api_service import (
    build_task_stream_response_payload,
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
