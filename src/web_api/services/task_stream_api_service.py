import logging
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select

from src.database.models import History
from src.services.redis_client import redis_client
from src.web_api.services.task_stream_service import build_task_status_stream_response


def build_terminal_progress_payload(
    status_data: dict[str, Any],
    task_id: str,
) -> dict[str, Any] | None:
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


async def get_user_history_record(
    task_id: str,
    user_id: int,
    session_factory,
) -> History | None:
    async with session_factory() as session:
        result = await session.execute(
            select(History).where(
                History.task_id == task_id,
                History.user_id == user_id,
            )
        )
        return result.scalars().first()


async def get_owned_active_task(
    task_id: str,
    user_id: int,
) -> dict[str, Any] | None:
    tasks = await redis_client.get_active_tasks()
    task = tasks.get(task_id)
    if task and task.get("user_id") == user_id:
        return task
    return None


async def build_not_found_progress_payload(
    task_id: str,
    user_id: int,
    session_factory,
) -> dict[str, Any]:
    history = await get_user_history_record(task_id, user_id, session_factory)
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


async def build_task_stream_response_payload(
    *,
    task_id: str,
    user_id: int,
    session_factory,
    redis,
    api_base: str,
    httpx_async_client_factory,
    logger: logging.Logger,
):
    owned_active_task = await get_owned_active_task(task_id, user_id)
    owned_history = await get_user_history_record(task_id, user_id, session_factory)
    if not owned_active_task and not owned_history:
        raise HTTPException(status_code=404, detail="任务不存在或无权限")

    return build_task_status_stream_response(
        task_id=task_id,
        user_id=user_id,
        session_factory=session_factory,
        redis=redis,
        api_base=api_base,
        httpx_async_client_factory=httpx_async_client_factory,
        logger=logger,
        build_not_found_progress_payload=build_not_found_progress_payload,
        build_terminal_progress_payload=build_terminal_progress_payload,
    )
