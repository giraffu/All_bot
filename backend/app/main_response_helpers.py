import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from fastapi import BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from app.models import SystemStatusResponse, SystemWorkersResponse, TaskStatusResponse
from minio import Minio

SYSTEM_STATUS_CACHE_TTL_SECONDS = float(
    os.getenv("SYSTEM_STATUS_CACHE_TTL_SECONDS", "10.0")
)
SYSTEM_STATUS_STALE_SECONDS = float(os.getenv("SYSTEM_STATUS_STALE_SECONDS", "120.0"))
TASK_STATUS_CACHE_TTL_SECONDS = float(os.getenv("TASK_STATUS_CACHE_TTL_SECONDS", "2.0"))
TASK_STATUS_CACHE_STALE_SECONDS = float(
    os.getenv("TASK_STATUS_CACHE_STALE_SECONDS", "4.0")
)
TASK_STATUS_CACHE_MAX_ENTRIES = int(os.getenv("TASK_STATUS_CACHE_MAX_ENTRIES", "5000"))
logger = logging.getLogger(__name__)


@dataclass
class _CachedSnapshot:
    value: Any
    cached_at: float
    expires_at: float


_worker_snapshot_cache: dict[Any, _CachedSnapshot] = {}
_worker_snapshot_locks: dict[Any, asyncio.Lock] = {}
_status_snapshot_cache: dict[Any, _CachedSnapshot] = {}
_status_snapshot_locks: dict[Any, asyncio.Lock] = {}
_task_status_snapshot_cache: dict[Any, _CachedSnapshot] = {}
_task_status_snapshot_locks: dict[Any, asyncio.Lock] = {}


def clear_system_snapshot_cache() -> None:
    _worker_snapshot_cache.clear()
    _worker_snapshot_locks.clear()
    _status_snapshot_cache.clear()
    _status_snapshot_locks.clear()
    _task_status_snapshot_cache.clear()
    _task_status_snapshot_locks.clear()


def _prune_snapshot_cache(
    *,
    cache: dict[Any, _CachedSnapshot],
    locks: dict[Any, asyncio.Lock],
    max_entries: int,
    stale_seconds: float,
    now: float,
) -> None:
    if max_entries <= 0 or len(cache) <= max_entries:
        return

    def remove_if_unlocked(cache_key: Any) -> bool:
        lock = locks.get(cache_key)
        if lock and lock.locked():
            return False
        cache.pop(cache_key, None)
        locks.pop(cache_key, None)
        return True

    for cache_key, snapshot in list(cache.items()):
        if (now - snapshot.cached_at) > stale_seconds:
            remove_if_unlocked(cache_key)

    overflow = len(cache) - max_entries
    if overflow <= 0:
        return

    for cache_key, _snapshot in sorted(
        cache.items(),
        key=lambda item: item[1].cached_at,
    ):
        if overflow <= 0:
            break
        if remove_if_unlocked(cache_key):
            overflow -= 1


async def _get_cached_snapshot(
    *,
    cache: dict[Any, _CachedSnapshot],
    locks: dict[Any, asyncio.Lock],
    cache_key: Any,
    collect_func: Callable[[], Awaitable[Any]],
    ttl_seconds: float = SYSTEM_STATUS_CACHE_TTL_SECONDS,
    stale_seconds: float = SYSTEM_STATUS_STALE_SECONDS,
    max_entries: int = 0,
    now_func: Callable[[], float] = time.monotonic,
) -> Any:
    if ttl_seconds <= 0:
        return await collect_func()

    now = now_func()
    cached = cache.get(cache_key)
    if cached and cached.expires_at > now:
        return cached.value

    lock = locks.setdefault(cache_key, asyncio.Lock())
    if cached and (now - cached.cached_at) <= stale_seconds:
        if not lock.locked():
            asyncio.create_task(
                _refresh_cached_snapshot(
                    cache=cache,
                    locks=locks,
                    lock=lock,
                    cache_key=cache_key,
                    collect_func=collect_func,
                    ttl_seconds=ttl_seconds,
                    stale_seconds=stale_seconds,
                    max_entries=max_entries,
                    now_func=now_func,
                )
            )
        return cached.value

    async with lock:
        now = now_func()
        cached = cache.get(cache_key)
        if cached and cached.expires_at > now:
            return cached.value

        try:
            value = await collect_func()
        except Exception:
            if cache_key not in cache:
                locks.pop(cache_key, None)
            raise
        cache[cache_key] = _CachedSnapshot(
            value=value,
            cached_at=now,
            expires_at=now + ttl_seconds,
        )
        _prune_snapshot_cache(
            cache=cache,
            locks=locks,
            max_entries=max_entries,
            stale_seconds=stale_seconds,
            now=now,
        )
        return value


async def _refresh_cached_snapshot(
    *,
    cache: dict[Any, _CachedSnapshot],
    locks: dict[Any, asyncio.Lock],
    lock: asyncio.Lock,
    cache_key: Any,
    collect_func: Callable[[], Awaitable[Any]],
    ttl_seconds: float,
    stale_seconds: float,
    max_entries: int,
    now_func: Callable[[], float],
) -> None:
    async with lock:
        now = now_func()
        cached = cache.get(cache_key)
        if cached and cached.expires_at > now:
            return

        try:
            value = await collect_func()
        except Exception:
            logger.exception("Failed to refresh cached system snapshot")
            return

        now = now_func()
        cache[cache_key] = _CachedSnapshot(
            value=value,
            cached_at=now,
            expires_at=now + ttl_seconds,
        )
        _prune_snapshot_cache(
            cache=cache,
            locks=locks,
            max_entries=max_entries,
            stale_seconds=stale_seconds,
            now=now,
        )


def _copy_workers(workers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(worker) for worker in workers]


def _queue_manager_cache_key(queue_manager) -> tuple[Any, ...]:
    redis = getattr(queue_manager, "redis", None)
    pool = getattr(redis, "connection_pool", None)
    connection_kwargs = getattr(pool, "connection_kwargs", None) or {}
    redis_identity = tuple(
        (key, str(connection_kwargs.get(key)))
        for key in ("host", "port", "db", "path", "username", "client_name")
        if key in connection_kwargs
    )
    if not redis_identity and redis is not None:
        redis_identity = (("object_id", str(id(redis))),)

    return (
        redis_identity,
        getattr(queue_manager, "pending_key", ""),
        getattr(queue_manager, "running_key", ""),
        getattr(queue_manager, "agent_heartbeat_prefix", ""),
    )


async def _get_worker_snapshot(queue_manager) -> list[dict[str, Any]]:
    async def collect_workers() -> list[dict[str, Any]]:
        workers = _copy_workers(await queue_manager.get_all_workers())
        if not hasattr(queue_manager, "get_agent_control_state"):
            return workers

        async def attach_control_state(worker: dict[str, Any]) -> dict[str, Any]:
            agent_id = str(worker.get("agent_id") or "")
            if not agent_id:
                return worker
            control = await queue_manager.get_agent_control_state(agent_id)
            worker["control_state"] = control.get("state") or "enabled"
            worker["control_reason"] = control.get("reason") or ""
            worker["control_updated_at"] = control.get("updated_at")
            return worker

        return await asyncio.gather(
            *(attach_control_state(worker) for worker in workers)
        )

    workers = await _get_cached_snapshot(
        cache=_worker_snapshot_cache,
        locks=_worker_snapshot_locks,
        cache_key=_queue_manager_cache_key(queue_manager),
        collect_func=collect_workers,
    )
    return _copy_workers(workers)


def _build_worker_status_counts(workers: list[dict[str, Any]]) -> dict[str, int]:
    workers_by_status: dict[str, int] = {}
    for worker in workers:
        status = str(worker.get("status") or "unknown")
        workers_by_status[status] = workers_by_status.get(status, 0) + 1
    return workers_by_status


def _build_worker_control_counts(workers: list[dict[str, Any]]) -> dict[str, int]:
    workers_by_control_state: dict[str, int] = {}
    for worker in workers:
        state = str(worker.get("control_state") or "enabled")
        workers_by_control_state[state] = workers_by_control_state.get(state, 0) + 1
    return workers_by_control_state


async def _get_system_status_snapshot(queue_manager) -> dict[str, Any]:
    async def collect_status() -> dict[str, Any]:
        queue_size, workers, queue_by_type = await asyncio.gather(
            queue_manager.get_queue_size(),
            _get_worker_snapshot(queue_manager),
            queue_manager.get_queue_metrics_by_type(),
        )
        workers_by_status = _build_worker_status_counts(workers)
        workers_by_control_state = _build_worker_control_counts(workers)
        healthy_workers = sum(
            count
            for status, count in workers_by_status.items()
            if status in {"idle", "running"}
        )
        accepting_workers = sum(
            1
            for worker in workers
            if str(worker.get("status") or "") in {"idle", "running"}
            and str(worker.get("control_state") or "enabled") == "enabled"
        )
        return {
            "queue_size": queue_size,
            "queue_by_type": dict(queue_by_type),
            "active_workers": len(workers),
            "healthy_workers": healthy_workers,
            "accepting_workers": accepting_workers,
            "error_workers": workers_by_status.get("error", 0),
            "quarantined_workers": workers_by_status.get("quarantined", 0),
            "workers_by_status": workers_by_status,
            "workers_by_control_state": workers_by_control_state,
            "comfy_online": healthy_workers > 0,
        }

    snapshot = await _get_cached_snapshot(
        cache=_status_snapshot_cache,
        locks=_status_snapshot_locks,
        cache_key=_queue_manager_cache_key(queue_manager),
        collect_func=collect_status,
    )
    return dict(snapshot)


def build_result_url(*, result_path: str, settings) -> str:
    protocol = "https" if settings.minio_secure else "http"
    return (
        f"{protocol}://{settings.minio_endpoint}/"
        f"{settings.minio_result_bucket}/{result_path}"
    )


async def build_task_status_response(
    *,
    task_id: str,
    queue_manager,
    include_image_url: bool = False,
    include_task_type: bool = False,
    build_result_url_func,
) -> TaskStatusResponse:
    async def collect_status() -> dict[str, Any]:
        task = await queue_manager.get_task_status(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        status = task.get("status")
        queue_pos = None
        queue_remaining = None
        if status == "pending":
            queue_pos = await queue_manager.get_queue_position(task_id)
            queue_remaining = queue_pos if queue_pos is not None else 0

        result_path = task.get("result_path")
        extra_outputs = queue_manager._maybe_parse_json_dict(task.get("extra_outputs"))
        response_kwargs = {
            "status": status,
            "queue_pos": queue_pos,
            "queue_remaining": queue_remaining,
            "progress": float(task.get("progress", 0.0)),
            "error": task.get("error_msg"),
            "result_path": result_path,
            "extra_outputs": extra_outputs,
            "cancel_requested": queue_manager._as_bool(task.get("cancel_requested")),
            "cancel_requested_at": (
                float(task["cancel_requested_at"])
                if task.get("cancel_requested_at")
                else None
            ),
            "cancel_locked": queue_manager._as_bool(task.get("cancel_locked")),
            "execution_phase": task.get("execution_phase") or None,
        }
        if include_image_url and status == "done" and result_path:
            response_kwargs["image_url"] = build_result_url_func(result_path)
        if include_task_type:
            response_kwargs["task_type"] = task.get("type")
        return response_kwargs

    cache_key = (
        _queue_manager_cache_key(queue_manager),
        task_id,
        include_image_url,
        include_task_type,
    )
    response_kwargs = await _get_cached_snapshot(
        cache=_task_status_snapshot_cache,
        locks=_task_status_snapshot_locks,
        cache_key=cache_key,
        collect_func=collect_status,
        ttl_seconds=TASK_STATUS_CACHE_TTL_SECONDS,
        stale_seconds=TASK_STATUS_CACHE_STALE_SECONDS,
        max_entries=TASK_STATUS_CACHE_MAX_ENTRIES,
    )
    response_kwargs = dict(response_kwargs)
    return TaskStatusResponse(**response_kwargs)


async def serve_task_result_file(
    *,
    task_id: str,
    ready_error_detail: str,
    queue_manager,
    minio_client: Optional[Minio],
    settings,
    logger,
) -> FileResponse:
    task = await queue_manager.get_task_status(task_id)
    if not task or task.get("status") != "done":
        raise HTTPException(status_code=404, detail=ready_error_detail)

    result_path = task.get("result_path")
    if not result_path:
        raise HTTPException(status_code=404, detail="Result path missing")
    if not minio_client:
        raise HTTPException(status_code=500, detail="MinIO client not initialized")

    import tempfile

    try:
        logger.info(
            "Fetching %s from MinIO bucket %s",
            result_path,
            settings.minio_result_bucket,
        )
        fd, temp_path = tempfile.mkstemp()
        os.close(fd)
        minio_client.fget_object(settings.minio_result_bucket, result_path, temp_path)
        background_tasks = BackgroundTasks()
        background_tasks.add_task(os.remove, temp_path)
        return FileResponse(temp_path, background=background_tasks)
    except Exception as exc:
        logger.error(f"MinIO download failed: {exc}")
        raise HTTPException(status_code=404, detail="File not found in storage")


async def build_system_workers_response(queue_manager) -> SystemWorkersResponse:
    workers = await _get_worker_snapshot(queue_manager)
    return SystemWorkersResponse(workers=workers, count=len(workers))


async def build_system_status_response(queue_manager) -> SystemStatusResponse:
    return SystemStatusResponse(**await _get_system_status_snapshot(queue_manager))


async def cancel_task_or_404(queue_manager, task_id: str):
    result = await queue_manager.cancel_task(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return result
