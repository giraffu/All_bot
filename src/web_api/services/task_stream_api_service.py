import logging
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select

from src.constants import VIDEO_TASK_TYPES
from src.core.task_status_mapper import (
    STREAM_STATUS_FAILED,
    STREAM_STATUS_SUCCESS,
    build_stream_terminal_payload,
    map_backend_status_to_stream_status,
)
from src.database.models import History
from src.services.redis_client import redis_client
from src.services.task_queue_position_display import select_display_queue_position
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


def _media_type_for_task_type(task_type: str | None) -> str | None:
    if not task_type:
        return None
    return "video" if task_type in VIDEO_TASK_TYPES else "image"


def _compact_optional_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def build_history_task_status_payload(history: History, task_id: str) -> dict[str, Any]:
    task_type = history.type or "edit"
    return _compact_optional_payload(
        {
            "status": STREAM_STATUS_SUCCESS,
            "task_id": task_id,
            "task_type": task_type,
            "media_type": _media_type_for_task_type(task_type),
        }
    )


def build_not_found_task_status_payload(task_id: str) -> dict[str, Any]:
    return {
        "status": STREAM_STATUS_FAILED,
        "task_id": task_id,
        "error": "任务不存在或无权限",
    }


def build_coarse_task_status_payload(
    status_data: dict[str, Any],
    task_id: str,
) -> dict[str, Any]:
    status = map_backend_status_to_stream_status(status_data.get("status"))
    task_type = status_data.get("task_type")
    base_payload: dict[str, Any] = {
        "status": status or "running",
        "task_id": task_id,
        "task_type": task_type,
        "media_type": status_data.get("media_type") or _media_type_for_task_type(task_type),
    }

    if status == "pending":
        queue_pos = select_display_queue_position(status_data)
        if queue_pos is not None:
            base_payload["queue_pos"] = queue_pos
        return _compact_optional_payload(base_payload)

    if status == STREAM_STATUS_FAILED:
        base_payload["error"] = status_data.get("error") or status_data.get("error_msg")
        return _compact_optional_payload(base_payload)

    if status == "cancelled":
        base_payload["message"] = (
            status_data.get("message")
            or status_data.get("error_msg")
            or "任务已取消"
        )
        return _compact_optional_payload(base_payload)

    if status == STREAM_STATUS_SUCCESS:
        return _compact_optional_payload(base_payload)

    base_payload["status"] = "running" if status == "running" else base_payload["status"]
    return _compact_optional_payload(base_payload)


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

    stream_kwargs = {
        "task_id": task_id,
        "runtime_task_id": runtime_task_id,
        "user_id": user_id,
        "session_factory": session_factory,
        "redis": redis,
        "api_base": api_base,
        "httpx_async_client_factory": httpx_async_client_factory,
        "logger": logger,
        "build_not_found_progress_payload": (
            dependencies.build_not_found_progress_payload_func
        ),
        "build_terminal_progress_payload": (
            dependencies.build_terminal_progress_payload_func
        ),
    }
    if owned_history and not owned_active_task:
        stream_kwargs["history_terminal"] = True

    return dependencies.build_task_status_stream_response_func(
        **stream_kwargs,
    )
