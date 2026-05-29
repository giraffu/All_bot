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


async def dequeue_task_flow(
    *,
    allowed_types: list[str] | None,
    pop_next_pending_task_func,
    find_next_allowed_task_func,
    activate_dequeued_task_func,
):
    if not allowed_types:
        return await activate_dequeued_task_func(await pop_next_pending_task_func())

    return await activate_dequeued_task_func(
        await find_next_allowed_task_func(allowed_types)
    )


async def find_next_allowed_task_flow(
    *,
    allowed_types: list[str],
    zrange_func,
    pending_key: str,
    decode_redis_value_func: Callable[[Any], Any],
    get_task_type_func,
    zrem_func,
    batch_size: int = 50,
):
    offset = 0
    while True:
        tasks_with_scores = await zrange_func(
            pending_key,
            offset,
            offset + batch_size - 1,
            withscores=True,
        )
        if not tasks_with_scores:
            return None

        for task_id_bytes, score in tasks_with_scores:
            task_id = decode_redis_value_func(task_id_bytes)
            task_type = await get_task_type_func(task_id)
            if not task_type or task_type not in allowed_types:
                continue

            removed = await zrem_func(pending_key, task_id)
            if removed:
                return task_id, score

        offset += batch_size


async def build_worker_info_flow(
    *,
    agent_id: str,
    raw_data: dict[Any, Any],
    decode_redis_dict_func,
    get_task_status_func,
) -> dict[str, Any] | None:
    if not raw_data:
        return None

    worker_info = decode_redis_dict_func(raw_data)
    worker_info["agent_id"] = agent_id

    current_task_id = worker_info.get("current_task_id")
    if worker_info.get("status") == "running" and current_task_id:
        task_data = await get_task_status_func(current_task_id)
        if task_data:
            worker_info["current_task_type"] = task_data.get("type")
            worker_info["current_task_progress"] = float(task_data.get("progress", 0.0))
            worker_info["current_task_created_at"] = float(
                task_data.get("created_at", 0.0)
            )

    return worker_info


async def get_all_workers_flow(
    *,
    scan_agent_heartbeat_keys_func,
    decode_redis_value_func: Callable[[Any], Any],
    agent_heartbeat_prefix: str,
    hgetall_func,
    build_worker_info_func,
) -> list[dict[str, Any]]:
    workers: list[dict[str, Any]] = []
    for key in await scan_agent_heartbeat_keys_func():
        key_str = decode_redis_value_func(key)
        agent_id = key_str.replace(agent_heartbeat_prefix, "")
        data = await hgetall_func(key)
        worker_info = await build_worker_info_func(agent_id, data)
        if worker_info:
            workers.append(worker_info)
    return workers


async def check_zombie_tasks_flow(
    *,
    iter_running_task_ids_func,
    fail_zombie_task_if_needed_func: Callable[[str], Awaitable[bool]],
) -> None:
    for task_id in await iter_running_task_ids_func():
        await fail_zombie_task_if_needed_func(task_id)


async def get_queue_metrics_by_type_flow(
    *,
    zrange_func,
    pending_key: str,
    initialize_type_counts_func,
    fetch_pending_task_types_func,
    accumulate_type_counts_func,
) -> dict[str, int]:
    task_ids = await zrange_func(pending_key, 0, -1)
    counts = initialize_type_counts_func()
    if not task_ids:
        return counts
    task_types = await fetch_pending_task_types_func(task_ids)
    return accumulate_type_counts_func(counts, task_types)


async def complete_task_flow(
    *,
    task_id: str,
    result_path: str,
    extra_outputs: dict[str, Any] | None,
    get_task_type_func,
    persist_task_update_func,
    done_status,
) -> None:
    task_type = await get_task_type_func(task_id) or "edit"
    serialized_extra_outputs = (
        json.dumps(extra_outputs) if isinstance(extra_outputs, dict) else ""
    )
    await persist_task_update_func(
        task_id,
        task_mapping={
            "status": done_status,
            "result_path": result_path,
            "extra_outputs": serialized_extra_outputs,
            "progress": 1.0,
            "cancel_requested": 0,
        },
        event_payload={
            "status": "done",
            "result_path": result_path,
            "extra_outputs": extra_outputs if isinstance(extra_outputs, dict) else None,
            "progress": 1.0,
            "task_type": task_type,
        },
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

    is_running = bool(await sismember_func(task_id))
    if is_running:
        return await request_running_task_cancellation_func(task_id)

    task_data = await get_task_status_func(task_id)
    status = task_data.get("status") if task_data else None
    if status == "running":
        return await request_running_task_cancellation_func(task_id)
    if status == cancelled_status:
        return build_cancel_result_func("already_cancelled", task_id, "任务已取消")

    return build_cancel_result_func("not_cancellable", task_id, "任务已结束，无法再取消")


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


async def get_active_workers_count_flow(*, scan_agent_heartbeat_keys_func) -> int:
    return len(await scan_agent_heartbeat_keys_func())


async def update_agent_heartbeat_flow(
    *,
    agent_id: str,
    types: str,
    status: str,
    agent_heartbeat_key_func,
    hset_func,
    expire_func,
    time_func=time.time,
) -> None:
    key = agent_heartbeat_key_func(agent_id)
    data = {"types": types, "status": status, "last_seen": time_func()}
    await hset_func(key, mapping=data)
    await expire_func(key, 30)


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


async def scan_agent_heartbeat_keys_flow(
    *,
    scan_func,
    agent_heartbeat_pattern_func,
) -> list[Any]:
    cursor = 0
    keys: list[Any] = []
    pattern = agent_heartbeat_pattern_func()
    while True:
        cursor, batch = await scan_func(cursor, match=pattern, count=100)
        keys.extend(batch)
        if cursor == 0:
            break
    return keys
