import json
import time
from collections.abc import Awaitable, Callable
from typing import Any

from asgi_correlation_id import correlation_id


def build_enqueued_task_payload(
    *,
    params: dict[str, Any],
    build_enqueued_task_data_func: Callable[..., dict[str, Any]],
    calculate_enqueue_score_func: Callable[..., float],
    task_id: str,
    task_type,
    priority: int,
) -> tuple[dict[str, Any], float]:
    trace_id = correlation_id.get() or ""
    # 显式注入 trace_id 到 params 中，用于全链路追踪
    params["trace_id"] = trace_id
    created_at = time.time()

    task_data = build_enqueued_task_data_func(
        task_id=task_id,
        task_type=task_type,
        priority=priority,
        params=params,
        trace_id=trace_id,
        created_at=created_at,
    )
    score = calculate_enqueue_score_func(current_time=created_at, priority=priority)
    return task_data, score


async def check_zombie_tasks_flow(
    *,
    iter_running_task_ids_func,
    fail_zombie_task_if_needed_func: Callable[[str], Awaitable[bool]],
) -> None:
    for task_id in await iter_running_task_ids_func():
        await fail_zombie_task_if_needed_func(task_id)


async def complete_task_flow(
    *,
    task_id: str,
    result_path: str,
    extra_outputs: dict[str, Any] | None,
    result_kind: str | None,
    result_text: str | None,
    result_meta: dict[str, Any] | None,
    result_asset: dict[str, Any] | None,
    extra_output_assets: dict[str, Any] | None,
    get_task_type_func,
    persist_task_update_func,
    done_status,
) -> None:
    task_type = await get_task_type_func(task_id) or "edit"
    serialized_extra_outputs = (
        json.dumps(extra_outputs) if isinstance(extra_outputs, dict) else ""
    )
    serialized_result_meta = (
        json.dumps(result_meta) if isinstance(result_meta, dict) else ""
    )
    serialized_result_asset = (
        json.dumps(result_asset) if isinstance(result_asset, dict) else ""
    )
    serialized_extra_output_assets = (
        json.dumps(extra_output_assets) if isinstance(extra_output_assets, dict) else ""
    )
    task_mapping = {
        "status": done_status,
        "result_path": result_path,
        "extra_outputs": serialized_extra_outputs,
        "result_kind": result_kind or ("media" if result_path else ""),
        "result_text": result_text or "",
        "result_meta": serialized_result_meta,
        "progress": 1.0,
        "cancel_requested": 0,
        "cancel_requested_at": "",
        "cancel_locked": 0,
        "execution_phase": "",
        "cancel_locked_at": "",
    }
    event_payload = {
        "status": "done",
        "result_path": result_path,
        "extra_outputs": extra_outputs if isinstance(extra_outputs, dict) else None,
        "result_kind": result_kind or ("media" if result_path else None),
        "result_text": result_text,
        "result_meta": result_meta if isinstance(result_meta, dict) else None,
        "progress": 1.0,
        "task_type": task_type,
    }
    if isinstance(result_asset, dict):
        task_mapping["result_asset"] = serialized_result_asset
        event_payload["result_asset"] = result_asset
    if isinstance(extra_output_assets, dict):
        task_mapping["extra_output_assets"] = serialized_extra_output_assets
        event_payload["extra_output_assets"] = extra_output_assets
    await persist_task_update_func(
        task_id,
        task_mapping=task_mapping,
        event_payload=event_payload,
        remove_from_running=True,
    )


async def fail_task_flow(
    *,
    task_id: str,
    error_msg: str,
    persist_task_update_func,
    error_status,
) -> None:
    await persist_task_update_func(
        task_id,
        task_mapping={
            "status": error_status,
            "error_msg": error_msg,
            "cancel_requested": 0,
            "cancel_requested_at": "",
            "cancel_locked": 0,
            "execution_phase": "",
            "cancel_locked_at": "",
        },
        event_payload={"status": "error", "error_msg": error_msg},
        remove_from_running=True,
    )


async def update_progress_flow(
    *,
    task_id: str,
    progress: float,
    persist_task_update_func,
) -> None:
    await persist_task_update_func(
        task_id,
        task_mapping={"progress": progress},
        event_payload={"status": "running", "progress": progress},
    )


def is_truthy_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


async def cancel_task_flow(
    *,
    task_id: str,
    task_key: str,
    exists_func,
    zrem_func,
    cancel_pending_task_func,
    request_running_task_cancellation_func,
    sismember_func,
    get_task_status_func,
    build_cancel_result_func,
    cancelled_status,
) -> dict[str, Any] | None:
    if not await exists_func(task_key):
        return None

    removed_from_pending = await zrem_func(task_id)
    if removed_from_pending:
        return await cancel_pending_task_func(task_id)

    task_data = await get_task_status_func(task_id)
    if task_data and is_truthy_flag(task_data.get("cancel_locked")):
        return build_cancel_result_func(
            "not_cancellable",
            task_id,
            "任务已进入输入准备或执行阶段，无法再取消",
            reason="cancel_locked",
            cancel_locked=True,
        )

    is_running = bool(await sismember_func(task_id))
    if is_running:
        return await request_running_task_cancellation_func(task_id)

    status = task_data.get("status") if task_data else None
    if status == "running":
        return await request_running_task_cancellation_func(task_id)
    if status == cancelled_status:
        return build_cancel_result_func("already_cancelled", task_id, "任务已取消")

    return build_cancel_result_func(
        "not_cancellable", task_id, "任务已结束，无法再取消"
    )


def build_cancel_result(
    state: str,
    task_id: str,
    message: str,
    **extra_fields: Any,
) -> dict[str, Any]:
    return {
        "state": state,
        "task_id": task_id,
        "message": message,
        **extra_fields,
    }


async def cancel_pending_task_flow(
    *,
    task_id: str,
    persist_task_update_func,
    build_cancel_result_func,
    cancelled_status,
) -> dict[str, Any]:
    await persist_task_update_func(
        task_id,
        task_mapping={
            "status": cancelled_status,
            "cancel_requested": 0,
            "cancel_requested_at": "",
            "cancel_locked": 0,
            "execution_phase": "",
            "cancel_locked_at": "",
        },
        event_payload={"status": "cancelled"},
        remove_from_running=True,
    )
    return build_cancel_result_func("cancelled", task_id, "任务已从排队队列移除")


async def cancel_running_task_flow(
    *,
    task_id: str,
    persist_task_update_func,
    build_cancel_result_func,
    cancelled_status,
) -> dict[str, Any]:
    await persist_task_update_func(
        task_id,
        task_mapping={
            "status": cancelled_status,
            "cancel_requested": 0,
            "cancel_requested_at": "",
            "cancel_locked": 0,
            "execution_phase": "",
            "cancel_locked_at": "",
        },
        event_payload={"status": "cancelled"},
        remove_from_running=True,
    )
    return build_cancel_result_func("cancelled", task_id, "任务已取消")


async def request_running_task_cancellation_flow(
    *,
    task_id: str,
    persist_task_update_func,
    build_cancel_result_func,
    time_func=time.time,
) -> dict[str, Any]:
    cancel_requested_at = time_func()
    await persist_task_update_func(
        task_id,
        task_mapping={
            "cancel_requested": 1,
            "cancel_requested_at": cancel_requested_at,
        },
        event_payload={
            "status": "running",
            "cancel_requested": True,
            "message": "已请求取消，等待执行端确认",
        },
    )
    return build_cancel_result_func(
        "cancellation_requested",
        task_id,
        "任务已请求取消，等待执行端确认",
        cancel_requested=True,
        cancel_requested_at=cancel_requested_at,
    )


async def iter_running_task_ids_flow(
    *,
    smembers_func,
    running_key: str,
    decode_redis_value_func: Callable[[Any], Any],
) -> list[str]:
    running_tasks = await smembers_func(running_key)
    return [decode_redis_value_func(task_id) for task_id in running_tasks]


async def has_task_heartbeat_flow(
    *,
    task_id: str,
    exists_func,
    task_heartbeat_key_func,
) -> bool:
    return bool(await exists_func(task_heartbeat_key_func(task_id)))


async def fail_zombie_task_if_needed_flow(
    *,
    task_id: str,
    has_task_heartbeat_func: Callable[[str], Awaitable[bool]],
    fail_task_func,
) -> bool:
    if await has_task_heartbeat_func(task_id):
        return False
    await fail_task_func(task_id, "Task execution timed out (Worker heartbeat lost)")
    return True
