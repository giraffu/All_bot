import asyncio
import logging
import os
import time
from typing import Any

import httpx
import redis.asyncio as redis
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from config import API_BASE, STATUS_ENDPOINT
from src.core.task_core import get_system_task_stats
from src.core.task_core_finalization import finalize_terminated_task
from src.core.task_core import sync_user_concurrency as core_sync_user_concurrency
from src.core.task_execution_types import resolve_worker_execution_task_type
from src.database.models import User
from src.services.image_service import image_service

logger = logging.getLogger("dashboard.system")
BACKEND_TASK_STATUS_CACHE_TTL_SECONDS = float(
    os.getenv("DASHBOARD_BACKEND_TASK_STATUS_CACHE_TTL_SECONDS", "5.0")
)
BACKEND_TASK_STATUS_CACHE_MAX_ENTRIES = int(
    os.getenv("DASHBOARD_BACKEND_TASK_STATUS_CACHE_MAX_ENTRIES", "2000")
)
CENTRAL_PENDING_QUEUE_KEY = "comfy:queue:pending"
CENTRAL_TASK_KEY_PREFIX = "comfy:task:"
_backend_task_status_cache: dict[tuple[str, str], tuple[float, dict]] = {}
_backend_task_status_locks: dict[tuple[str, str], asyncio.Lock] = {}


def clear_backend_task_status_cache() -> None:
    _backend_task_status_cache.clear()
    _backend_task_status_locks.clear()


def _prune_backend_task_status_cache(now: float) -> None:
    if (
        BACKEND_TASK_STATUS_CACHE_MAX_ENTRIES <= 0
        or len(_backend_task_status_cache) <= BACKEND_TASK_STATUS_CACHE_MAX_ENTRIES
    ):
        return

    def remove_if_unlocked(cache_key: tuple[str, str]) -> bool:
        lock = _backend_task_status_locks.get(cache_key)
        if lock and lock.locked():
            return False
        _backend_task_status_cache.pop(cache_key, None)
        _backend_task_status_locks.pop(cache_key, None)
        return True

    for cache_key, (expires_at, _data) in list(_backend_task_status_cache.items()):
        if expires_at <= now:
            remove_if_unlocked(cache_key)

    overflow = len(_backend_task_status_cache) - BACKEND_TASK_STATUS_CACHE_MAX_ENTRIES
    if overflow <= 0:
        return

    for cache_key, _cached in sorted(
        _backend_task_status_cache.items(),
        key=lambda item: item[1][0],
    ):
        if overflow <= 0:
            break
        if remove_if_unlocked(cache_key):
            overflow -= 1


def count_tasks_by_type(tasks: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for task in tasks.values():
        task_type = resolve_worker_execution_task_type(task.get("task_type"))
        counts[task_type] = counts.get(task_type, 0) + 1
    return counts


def _decode_redis_value(value: Any) -> Any:
    return value.decode() if isinstance(value, bytes) else value


def _empty_queue_type_detail(active_count: int = 0) -> dict:
    return {
        "active_count": active_count,
        "pending_count": 0,
        "max_pending_wait_seconds": None,
        "oldest_pending_task_id": None,
        "oldest_pending_created_at": None,
    }


def build_queue_type_details(
    active_tasks: dict,
    pending_wait_details: dict[str, dict] | None = None,
) -> dict[str, dict]:
    details = {
        task_type: _empty_queue_type_detail(active_count=count)
        for task_type, count in count_tasks_by_type(active_tasks).items()
    }

    for task_type, pending_detail in (pending_wait_details or {}).items():
        detail = details.setdefault(task_type, _empty_queue_type_detail())
        detail["pending_count"] = int(pending_detail.get("pending_count") or 0)
        detail["max_pending_wait_seconds"] = pending_detail.get(
            "max_pending_wait_seconds"
        )
        detail["oldest_pending_task_id"] = pending_detail.get(
            "oldest_pending_task_id"
        )
        detail["oldest_pending_created_at"] = pending_detail.get(
            "oldest_pending_created_at"
        )

    return details


async def _close_redis_resource(resource) -> None:
    close = getattr(resource, "aclose", None) or getattr(resource, "close", None)
    if close is None:
        return
    result = close()
    if asyncio.iscoroutine(result):
        await result


async def get_pending_queue_wait_details(
    *,
    redis_url: str | None = None,
    redis_from_url_func=None,
    now_func=None,
    logger_override: logging.Logger | None = None,
) -> dict[str, dict]:
    active_logger = logger_override or logger
    if now_func is None:
        now_func = time.time
    if redis_from_url_func is None:
        redis_from_url_func = redis.from_url

    resolved_redis_url = redis_url or os.getenv("WORKER_REDIS_URL")
    if not resolved_redis_url:
        return {}

    redis_client = None
    try:
        redis_client = redis_from_url_func(resolved_redis_url, decode_responses=True)
        pending_task_ids = await redis_client.zrange(CENTRAL_PENDING_QUEUE_KEY, 0, -1)
        if not pending_task_ids:
            return {}

        pipeline = redis_client.pipeline(transaction=False)
        normalized_task_ids: list[str] = []
        for raw_task_id in pending_task_ids:
            task_id = str(_decode_redis_value(raw_task_id))
            normalized_task_ids.append(task_id)
            task_key = f"{CENTRAL_TASK_KEY_PREFIX}{task_id}"
            pipeline.hget(task_key, "type")
            pipeline.hget(task_key, "created_at")
        values = await pipeline.execute()

        now = float(now_func())
        details: dict[str, dict] = {}
        for index, task_id in enumerate(normalized_task_ids):
            task_type = _decode_redis_value(values[index * 2])
            created_at = _decode_redis_value(values[index * 2 + 1])
            if not task_type or created_at in (None, ""):
                continue

            try:
                created_at_float = float(created_at)
            except (TypeError, ValueError):
                continue

            execution_type = resolve_worker_execution_task_type(task_type)
            wait_seconds = max(0, int(now - created_at_float))
            detail = details.setdefault(execution_type, _empty_queue_type_detail())
            detail["pending_count"] += 1

            current_max = detail.get("max_pending_wait_seconds")
            if current_max is None or wait_seconds > current_max:
                detail["max_pending_wait_seconds"] = wait_seconds
                detail["oldest_pending_task_id"] = task_id
                detail["oldest_pending_created_at"] = created_at_float

        return details
    except Exception as exc:
        active_logger.warning("Could not collect pending queue wait details: %s", exc)
        return {}
    finally:
        if redis_client is not None:
            await _close_redis_resource(redis_client)


async def refund_bot_task_payload(
    *,
    task_id: str,
    get_system_task_stats_func=None,
    finalize_terminated_task_func=None,
    logger_override: logging.Logger | None = None,
) -> dict:
    active_logger = logger_override or logger
    if get_system_task_stats_func is None:
        get_system_task_stats_func = get_system_task_stats
    if finalize_terminated_task_func is None:
        finalize_terminated_task_func = finalize_terminated_task

    try:
        tasks, _ = await get_system_task_stats_func()
        if not tasks or task_id not in tasks:
            raise HTTPException(
                status_code=404, detail="Task not found in Redis active tasks"
            )

        task = tasks[task_id]
        user_id = task.get("user_id")
        username = task.get("username", "Unknown")
        cost = task.get("cost", 0)

        result = await finalize_terminated_task_func(
            registry_task_id=task_id,
            user_id=user_id,
            username=username,
            cost=cost,
            should_refund=cost > 0,
            refund_task_type="refund_admin_force",
        )
        return {
            "status": "success",
            "message": (
                f"Task {task_id} terminated and {cost} credits refunded."
                if result.refunded
                else f"Task {task_id} terminated."
            ),
        }
    except HTTPException:
        raise
    except Exception as exc:
        active_logger.error(f"Error refunding bot task: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def clean_zombie_tasks_payload(
    *,
    get_system_task_stats_func=None,
    finalize_terminated_task_func=None,
    now_func=None,
    logger_override: logging.Logger | None = None,
) -> dict:
    active_logger = logger_override or logger
    if get_system_task_stats_func is None:
        get_system_task_stats_func = get_system_task_stats
    if finalize_terminated_task_func is None:
        finalize_terminated_task_func = finalize_terminated_task
    if now_func is None:
        now_func = time.time

    try:
        tasks, _ = await get_system_task_stats_func()
        if not tasks:
            return {
                "status": "success",
                "message": "No active tasks found.",
                "removed": 0,
            }

        removed = 0
        now = now_func()
        for task_id, task in tasks.items():
            age = now - task.get("created_at", now)
            if age > 7200:
                user_id = task.get("user_id")
                username = task.get("username", "Unknown")
                cost = task.get("cost", 0)
                await finalize_terminated_task_func(
                    registry_task_id=task_id,
                    user_id=user_id,
                    username=username,
                    cost=cost,
                    should_refund=cost > 0,
                    refund_task_type="refund_admin_force_cleanup",
                )
                removed += 1

        return {
            "status": "success",
            "message": f"Cleaned up {removed} zombie tasks.",
            "removed": removed,
        }
    except Exception as exc:
        active_logger.error(f"Error cleaning zombie tasks: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def sync_user_concurrency_payload(
    *,
    user_id: int,
    get_system_task_stats_func=None,
    sync_user_concurrency_func=None,
    logger_override: logging.Logger | None = None,
) -> dict:
    active_logger = logger_override or logger
    if get_system_task_stats_func is None:
        get_system_task_stats_func = get_system_task_stats
    if sync_user_concurrency_func is None:
        sync_user_concurrency_func = core_sync_user_concurrency

    try:
        active_tasks, concurrencies = await get_system_task_stats_func()
        actual_count = sum(1 for task in active_tasks.values() if task.get("user_id") == user_id)
        current_lock = concurrencies.get(user_id, 0)

        if current_lock > actual_count:
            await sync_user_concurrency_func(user_id, actual_count)
            return {
                "status": "success",
                "message": f"用户 {user_id} 并发锁已从 {current_lock} 修复为 {actual_count}",
            }
        return {"status": "info", "message": "无需修复，锁数量未超出真实任务数"}
    except Exception as exc:
        active_logger.error(f"Error syncing concurrency lock for user {user_id}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def _load_user_names_for_stats(*, user_ids: set[int], session_factory) -> dict[int, str]:
    if not user_ids:
        return {}

    async with session_factory() as db:
        stmt = select(User.id, User.username).where(User.id.in_(list(user_ids)))
        result = await db.execute(stmt)
        return {row.id: row.username for row in result.all()}


async def get_concurrency_stats_payload(
    *,
    get_system_task_stats_func=None,
    session_factory=None,
    logger_override: logging.Logger | None = None,
) -> dict:
    active_logger = logger_override or logger
    if get_system_task_stats_func is None:
        get_system_task_stats_func = get_system_task_stats
    if session_factory is None:
        from src.database.core import AsyncSessionLocal

        session_factory = AsyncSessionLocal

    try:
        active_tasks, concurrencies = await get_system_task_stats_func()
        user_active_tasks: dict[int, int] = {}
        user_names: dict[int, str] = {}
        for task in active_tasks.values():
            uid = task.get("user_id")
            if uid:
                user_active_tasks[uid] = user_active_tasks.get(uid, 0) + 1
                if task.get("username"):
                    user_names[uid] = task.get("username")

        all_uids = set(concurrencies.keys()).union(set(user_active_tasks.keys()))
        missing_uids = all_uids - set(user_names.keys())
        if missing_uids:
            user_names.update(
                await _load_user_names_for_stats(
                    user_ids=missing_uids,
                    session_factory=session_factory,
                )
            )

        stats = []
        for uid in all_uids:
            stats.append(
                {
                    "user_id": uid,
                    "username": user_names.get(uid, f"User_{uid}"),
                    "concurrency_locks": concurrencies.get(uid, 0),
                    "active_tasks": user_active_tasks.get(uid, 0),
                }
            )
        return {"status": "success", "data": stats}
    except Exception as exc:
        active_logger.error(f"Error getting concurrency stats: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def _load_active_task_user_info(*, user_ids: list[int], session_factory) -> dict[int, dict]:
    if not user_ids:
        return {}

    async with session_factory() as db:
        stmt = select(
            User.id,
            User.user_group,
            User.current_identity,
            User.full_name,
            User.username,
        ).where(
            User.id.in_(user_ids)
        )
        result = await db.execute(stmt)
        return {
            row.id: {
                "user_group": row.user_group,
                "current_identity": row.current_identity,
                "full_name": row.full_name,
                "username": row.username,
            }
            for row in result.all()
        }


async def _fetch_backend_task_statuses(
    *,
    tasks: dict,
    api_base: str,
    request_backend_status_func=None,
) -> dict[str, dict]:
    if request_backend_status_func is None:
        from src.api_client import api_client

        async def request_backend_status_func(backend_id: str):
            return await api_client._request(
                "GET", f"{api_base}/status/{backend_id}", timeout=2
            )

    task_ids = [
        task.get("backend_task_id")
        for task in tasks.values()
        if task.get("backend_task_id")
    ]
    if not task_ids:
        return {}

    async def fetch_status(backend_id: str):
        cache_key = (api_base, backend_id)
        now = time.monotonic()
        cached = _backend_task_status_cache.get(cache_key)
        if (
            BACKEND_TASK_STATUS_CACHE_TTL_SECONDS > 0
            and cached
            and cached[0] > now
        ):
            return backend_id, dict(cached[1])

        lock = _backend_task_status_locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            cached = _backend_task_status_cache.get(cache_key)
            if (
                BACKEND_TASK_STATUS_CACHE_TTL_SECONDS > 0
                and cached
                and cached[0] > now
            ):
                return backend_id, dict(cached[1])

            try:
                response = await request_backend_status_func(backend_id)
                status_data = response.json()
                if BACKEND_TASK_STATUS_CACHE_TTL_SECONDS > 0:
                    now = time.monotonic()
                    expires_at = now + BACKEND_TASK_STATUS_CACHE_TTL_SECONDS
                    _backend_task_status_cache[cache_key] = (
                        expires_at,
                        dict(status_data),
                    )
                    _prune_backend_task_status_cache(now)
                return backend_id, status_data
            except Exception:
                if cache_key not in _backend_task_status_cache:
                    _backend_task_status_locks.pop(cache_key, None)
                return backend_id, None

    results = await asyncio.gather(*(fetch_status(task_id) for task_id in task_ids[:20]))
    return {
        backend_id: status_data
        for backend_id, status_data in results
        if status_data is not None
    }


def _merge_backend_status_into_task(task: dict, *, backend_statuses: dict, user_info: dict) -> None:
    uid = task.get("user_id")
    if uid in user_info:
        task["user_group"] = user_info[uid]["user_group"]
        task["user_identity"] = user_info[uid]["current_identity"]
        task["display_name"] = (
            user_info[uid].get("full_name")
            or user_info[uid].get("username")
            or task.get("full_name")
            or task.get("username")
            or f"User_{uid}"
        )
    else:
        task["user_group"] = "未知"
        task["user_identity"] = "外门弟子"
        task["display_name"] = (
            task.get("full_name")
            or task.get("username")
            or (f"User_{uid}" if uid else "Unknown")
        )

    backend_id = task.get("backend_task_id")
    status_data = backend_statuses.get(backend_id)
    if status_data:
        state = status_data.get("status")
        task["execution_status"] = state
        if state == "running":
            task["queue_position"] = "生成中"
        elif state == "pending":
            task["queue_position"] = status_data.get("queue_pos", "-")
        elif state == "done":
            task["queue_position"] = "已完成"
        elif state == "error":
            task["queue_position"] = "异常"
        elif state == "cancelled":
            task["queue_position"] = "已取消"
        else:
            task["queue_position"] = "未知"
    elif backend_id:
        task["execution_status"] = "pending"
        task["queue_position"] = "-"
    else:
        task["execution_status"] = "submitting"
        task["queue_position"] = "提交中"


async def get_active_bot_tasks_payload(
    *,
    get_system_task_stats_func=None,
    session_factory=None,
    api_base: str = API_BASE,
    request_backend_status_func=None,
    logger_override: logging.Logger | None = None,
) -> dict:
    active_logger = logger_override or logger
    if get_system_task_stats_func is None:
        get_system_task_stats_func = get_system_task_stats
    if session_factory is None:
        from src.database.core import AsyncSessionLocal

        session_factory = AsyncSessionLocal

    try:
        tasks, _ = await get_system_task_stats_func()
        if tasks:
            user_ids = [task.get("user_id") for task in tasks.values() if task.get("user_id")]
            user_info = await _load_active_task_user_info(
                user_ids=user_ids,
                session_factory=session_factory,
            )
            try:
                backend_statuses = await _fetch_backend_task_statuses(
                    tasks=tasks,
                    api_base=api_base,
                    request_backend_status_func=request_backend_status_func,
                )
            except Exception as exc:
                active_logger.warning(
                    f"Could not fetch executing tasks from backend: {exc}"
                )
                backend_statuses = {}

            for task in tasks.values():
                _merge_backend_status_into_task(
                    task,
                    backend_statuses=backend_statuses,
                    user_info=user_info,
                )

        return {"status": "success", "tasks": tasks, "count": len(tasks)}
    except Exception as exc:
        active_logger.error(f"Error getting active bot tasks from Redis: {exc}")
        return {"status": "error", "message": str(exc), "tasks": {}, "count": 0}


async def get_bot_queue_payload(
    *,
    get_queue_info_func=None,
    logger_override: logging.Logger | None = None,
) -> dict:
    active_logger = logger_override or logger
    if get_queue_info_func is None:
        get_queue_info_func = image_service.get_queue_info

    try:
        status = await get_queue_info_func()
        return status or {
            "total_active_tasks": 0,
            "img2img_active_tasks": 0,
            "img2video_active_tasks": 0,
        }
    except Exception as exc:
        active_logger.error(f"Error getting bot queue status: {exc}")
        return {
            "total_active_tasks": 0,
            "img2img_active_tasks": 0,
            "img2video_active_tasks": 0,
            "error": str(exc),
        }


async def get_system_status_payload(
    *,
    status_endpoint: str = STATUS_ENDPOINT,
    httpx_async_client_factory=httpx.AsyncClient,
) -> dict:
    try:
        async with httpx_async_client_factory(trust_env=False) as client:
            response = await client.get(status_endpoint, timeout=5.0)
            return {
                "comfyui": "online" if response.status_code == 200 else "error",
                "details": response.json()
                if response.status_code == 200
                else str(response.status_code),
            }
    except Exception as exc:
        return {"comfyui": "offline", "error": str(exc)}


async def _request_json(url: str, *, httpx_async_client_factory=httpx.AsyncClient) -> tuple[int, dict | None]:
    async with httpx_async_client_factory(trust_env=False) as client:
        response = await client.get(url, timeout=10.0)
        if response.status_code == 200:
            return response.status_code, response.json()
        return response.status_code, None


async def get_system_status_proxy_payload(
    *,
    api_base: str = API_BASE,
    httpx_async_client_factory=httpx.AsyncClient,
    get_system_task_stats_func=None,
    get_pending_queue_wait_details_func=None,
    logger_override: logging.Logger | None = None,
) -> dict:
    active_logger = logger_override or logger
    if get_system_task_stats_func is None:
        get_system_task_stats_func = get_system_task_stats
    if get_pending_queue_wait_details_func is None:
        get_pending_queue_wait_details_func = get_pending_queue_wait_details

    try:
        status_code, payload = await _request_json(
            f"{api_base}/system/status",
            httpx_async_client_factory=httpx_async_client_factory,
        )
        if status_code == 200:
            data = payload
        else:
            data = {
                "queue_size": 0,
                "queue_by_type": {},
                "queue_by_type_details": {},
                "active_workers": 0,
                "healthy_workers": 0,
                "error_workers": 0,
                "quarantined_workers": 0,
                "workers_by_status": {},
                "comfy_online": False,
                "error": f"Middleware returned {status_code}",
            }
        data.setdefault("healthy_workers", data.get("active_workers", 0) if data.get("comfy_online") else 0)
        data.setdefault("error_workers", 0)
        data.setdefault("quarantined_workers", 0)
        data.setdefault("workers_by_status", {})
    except Exception as exc:
        active_logger.error(f"Error proxying system status: {exc}")
        data = {
            "queue_size": 0,
            "queue_by_type": {},
            "queue_by_type_details": {},
            "active_workers": 0,
            "healthy_workers": 0,
            "error_workers": 0,
            "quarantined_workers": 0,
            "workers_by_status": {},
            "comfy_online": False,
            "error": str(exc),
        }

    try:
        active_tasks, concurrencies = await get_system_task_stats_func()
        try:
            pending_wait_details = await get_pending_queue_wait_details_func()
        except Exception as exc:
            active_logger.warning(
                f"Could not collect pending queue wait details: {exc}"
            )
            pending_wait_details = {}

        active_counts = count_tasks_by_type(active_tasks)
        data["middleware_queue_size"] = data.get("queue_size", 0)
        data["middleware_queue_by_type"] = data.get("queue_by_type", {})
        data["queue_size"] = len(active_tasks)
        data["queue_by_type"] = active_counts
        data["queue_by_type_details"] = build_queue_type_details(
            active_tasks,
            pending_wait_details,
        )
        data["concurrency_locks"] = sum(concurrencies.values())
        data["concurrency_details"] = concurrencies
    except Exception as exc:
        active_logger.error(f"Error getting concurrency locks: {exc}")
        data.setdefault("queue_by_type_details", {})
        data["concurrency_locks"] = 0
        data["concurrency_details"] = {}

    return data


async def get_system_workers_proxy_payload(
    *,
    api_base: str = API_BASE,
    httpx_async_client_factory=httpx.AsyncClient,
    logger_override: logging.Logger | None = None,
) -> dict:
    active_logger = logger_override or logger
    try:
        status_code, payload = await _request_json(
            f"{api_base}/system/workers",
            httpx_async_client_factory=httpx_async_client_factory,
        )
        if status_code == 200:
            return payload
        return {
            "workers": [],
            "count": 0,
            "error": f"Middleware returned {status_code}",
        }
    except Exception as exc:
        active_logger.error(f"Error proxying system workers: {exc}")
        return {"workers": [], "count": 0, "error": str(exc)}


async def get_task_status_proxy_payload(
    *,
    task_id: str,
    api_base: str = API_BASE,
    httpx_async_client_factory=httpx.AsyncClient,
    logger_override: logging.Logger | None = None,
):
    active_logger = logger_override or logger
    try:
        async with httpx_async_client_factory(trust_env=False) as client:
            response = await client.get(f"{api_base}/status/{task_id}", timeout=5.0)
            if response.status_code == 200:
                return response.json()
            raise HTTPException(
                status_code=response.status_code, detail="Task not found or error"
            )
    except HTTPException:
        raise
    except Exception as exc:
        active_logger.error(f"Error proxying task status: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def stream_task_asset_proxy(
    *,
    task_id: str,
    asset_type: str,
    api_base: str = API_BASE,
    timeout: float = 30.0,
    not_found_detail: str = "Asset not found",
    httpx_async_client_factory=httpx.AsyncClient,
    logger_override: logging.Logger | None = None,
):
    active_logger = logger_override or logger
    try:
        url = f"{api_base}/{asset_type}/{task_id}"
        client = httpx_async_client_factory(trust_env=False)
        req = client.build_request("GET", url, timeout=timeout)
        response = await client.send(req, stream=True)

        if response.status_code != 200:
            await response.aclose()
            await client.aclose()
            raise HTTPException(status_code=response.status_code, detail=not_found_detail)

        async def iter_file():
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose()
                await client.aclose()

        return StreamingResponse(
            iter_file(),
            media_type=response.headers.get("content-type"),
        )
    except HTTPException:
        raise
    except Exception as exc:
        active_logger.error(f"Error proxying {asset_type}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
