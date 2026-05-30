import logging
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select

from src.core.task_status_mapper import (
    STREAM_STATUS_FAILED,
    STREAM_STATUS_SUCCESS,
    build_stream_terminal_payload,
)
from src.database.models import History
from src.services.redis_client import redis_client
from src.web_api.services.task_stream_service import build_task_status_stream_response


@dataclass(frozen=True)
class TaskStreamResponseDependencies:
    get_owned_active_task_func: Any
    get_user_history_record_func: Any
    build_not_found_progress_payload_func: Any
    build_terminal_progress_payload_func: Any
    build_task_status_stream_response_func: Any


def build_terminal_progress_payload(
    status_data: dict[str, Any],
    task_id: str,
) -> dict[str, Any] | None:
    return build_stream_terminal_payload(status_data, task_id)


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
            "status": STREAM_STATUS_SUCCESS,
            "task_id": task_id,
            "task_type": history.type or "edit",
        }

    return {
        "status": STREAM_STATUS_FAILED,
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
    dependencies: TaskStreamResponseDependencies | None = None,
):
    dependencies = dependencies or TaskStreamResponseDependencies(
        get_owned_active_task_func=get_owned_active_task,
        get_user_history_record_func=get_user_history_record,
        build_not_found_progress_payload_func=build_not_found_progress_payload,
        build_terminal_progress_payload_func=build_terminal_progress_payload,
        build_task_status_stream_response_func=build_task_status_stream_response,
    )
    owned_active_task = await dependencies.get_owned_active_task_func(task_id, user_id)
    owned_history = await dependencies.get_user_history_record_func(
        task_id, user_id, session_factory
    )
    runtime_task_id = (
        owned_active_task.get("backend_task_id")
        if owned_active_task and owned_active_task.get("backend_task_id")
        else task_id
    )
    if not owned_active_task and not owned_history:
        raise HTTPException(status_code=404, detail="任务不存在或无权限")

    return dependencies.build_task_status_stream_response_func(
        task_id=task_id,
        runtime_task_id=runtime_task_id,
        user_id=user_id,
        session_factory=session_factory,
        redis=redis,
        api_base=api_base,
        httpx_async_client_factory=httpx_async_client_factory,
        logger=logger,
        build_not_found_progress_payload=(
            dependencies.build_not_found_progress_payload_func
        ),
        build_terminal_progress_payload=(
            dependencies.build_terminal_progress_payload_func
        ),
    )
