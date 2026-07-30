from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import asdict, dataclass
from typing import Any, Awaitable, Callable


PENDING_KEY = "comfy:queue:pending"
RUNNING_KEY = "comfy:queue:running"
TASK_PREFIX = "comfy:task:"
TASK_EVENT_PREFIX = "comfy:task_events:"
REFUND_TASK_TYPE = "refund_prod_maintenance_release"


class RefundGateError(RuntimeError):
    pass


@dataclass
class RefundSummary:
    pending_count: int
    running_count: int
    mapped_pending_count: int
    orphan_pending_count: int
    invalid_mapping_count: int = 0
    refunded_count: int = 0
    already_refunded_count: int = 0
    moved_count: int = 0
    dry_run: bool = True


async def connect_redis(url: str):
    import redis.asyncio as redis

    return redis.from_url(
        url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=10,
        retry_on_timeout=False,
    )


async def load_active_tasks(app_redis, redis_prefix: str) -> dict[str, dict[str, Any]]:
    raw = await app_redis.hgetall(f"{redis_prefix}active_tasks")
    tasks: dict[str, dict[str, Any]] = {}
    for registry_task_id, payload in raw.items():
        try:
            parsed = json.loads(payload)
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, dict):
            tasks[str(registry_task_id)] = parsed
    return tasks


async def build_queue_snapshot(worker_redis, app_redis, redis_prefix: str) -> dict[str, Any]:
    pending_backend_ids = [
        str(item) for item in await worker_redis.zrange(PENDING_KEY, 0, -1)
    ]
    running_backend_ids = [
        str(item) for item in await worker_redis.smembers(RUNNING_KEY)
    ]
    active_tasks = await load_active_tasks(app_redis, redis_prefix)
    registry_by_backend: dict[str, str] = {}
    duplicate_backend_ids: set[str] = set()
    for registry_id, data in active_tasks.items():
        backend_id = data.get("backend_task_id")
        if not backend_id:
            continue
        normalized = str(backend_id)
        if normalized in registry_by_backend:
            duplicate_backend_ids.add(normalized)
        registry_by_backend[normalized] = registry_id
    mapped_pending = [
        backend_id for backend_id in pending_backend_ids
        if backend_id in registry_by_backend
    ]
    orphan_pending = [
        backend_id for backend_id in pending_backend_ids
        if backend_id not in registry_by_backend
    ]
    return {
        "pending_count": len(pending_backend_ids),
        "running_count": len(running_backend_ids),
        "active_task_count": len(active_tasks),
        "pending_backend_ids": pending_backend_ids,
        "running_backend_ids": running_backend_ids,
        "active_tasks": active_tasks,
        "registry_by_backend": registry_by_backend,
        "mapped_pending_count": len(mapped_pending),
        "orphan_pending_count": len(orphan_pending),
        "duplicate_backend_count": len(
            duplicate_backend_ids.intersection(pending_backend_ids)
        ),
    }


async def cancel_backend_pending(worker_redis, backend_task_id: str) -> bool:
    removed = await worker_redis.zrem(PENDING_KEY, backend_task_id)
    if not removed:
        return False
    await worker_redis.hset(
        f"{TASK_PREFIX}{backend_task_id}",
        mapping={
            "status": "cancelled",
            "cancel_requested": 0,
            "cancel_requested_at": "",
            "cancel_locked": 0,
            "execution_phase": "",
            "cancel_locked_at": "",
        },
    )
    await worker_redis.srem(RUNNING_KEY, backend_task_id)
    await worker_redis.publish(
        f"{TASK_EVENT_PREFIX}{backend_task_id}",
        json.dumps({"status": "cancelled"}),
    )
    return True


def _validated_task(
    active_tasks: dict[str, dict[str, Any]], registry_task_id: str
) -> tuple[int, str, int]:
    task = active_tasks.get(registry_task_id) or {}
    try:
        user_id = int(task["user_id"])
        cost = int(task.get("cost") or 0)
    except (KeyError, TypeError, ValueError) as exc:
        raise RefundGateError("pending task mapping is incomplete") from exc
    if user_id <= 0 or cost < 0:
        raise RefundGateError("pending task mapping is invalid")
    return user_id, str(task.get("username") or "Unknown"), cost


async def refund_pending_tasks(
    *,
    worker_redis,
    app_redis,
    redis_prefix: str,
    threshold: int,
    allow_above_threshold: bool,
    execute: bool,
    finalize_task_failure_func: Callable[..., Awaitable[Any]],
    sync_user_concurrency_func: Callable[[int, int], Awaitable[Any]],
) -> RefundSummary:
    snapshot = await build_queue_snapshot(worker_redis, app_redis, redis_prefix)
    pending_ids: list[str] = snapshot["pending_backend_ids"]
    summary = RefundSummary(
        pending_count=len(pending_ids),
        running_count=len(snapshot["running_backend_ids"]),
        mapped_pending_count=int(snapshot["mapped_pending_count"]),
        orphan_pending_count=int(snapshot["orphan_pending_count"]),
        dry_run=not execute,
    )
    if summary.pending_count >= threshold and not allow_above_threshold:
        raise RefundGateError("pending threshold requires explicit override")
    if summary.orphan_pending_count or snapshot["duplicate_backend_count"]:
        raise RefundGateError("pending queue contains orphan or ambiguous mappings")

    active_tasks: dict[str, dict[str, Any]] = snapshot["active_tasks"]
    registry_by_backend: dict[str, str] = snapshot["registry_by_backend"]
    validated: dict[str, tuple[str, int, str, int]] = {}
    for backend_id in pending_ids:
        registry_id = registry_by_backend[backend_id]
        try:
            user_id, username, cost = _validated_task(active_tasks, registry_id)
        except RefundGateError:
            summary.invalid_mapping_count += 1
            continue
        validated[backend_id] = (registry_id, user_id, username, cost)
    if summary.invalid_mapping_count:
        raise RefundGateError("pending queue contains invalid task mappings")
    if not execute:
        return summary

    affected_users: set[int] = set()
    for backend_id in pending_ids:
        registry_id, user_id, username, cost = validated[backend_id]
        if not await cancel_backend_pending(worker_redis, backend_id):
            summary.moved_count += 1
            continue
        result = await finalize_task_failure_func(
            internal_user_id=user_id,
            username=username,
            cost=cost,
            should_refund=cost > 0,
            registry_task_id=registry_id,
            refund_task_type=REFUND_TASK_TYPE,
            explicit_user_message="发布维护取消排队任务，已退还预扣灵石。",
        )
        if cost > 0 and not bool(getattr(result, "refunded", False)):
            summary.already_refunded_count += 1
        else:
            summary.refunded_count += 1
        affected_users.add(user_id)

    refreshed = await load_active_tasks(app_redis, redis_prefix)
    for user_id in sorted(affected_users):
        actual_count = sum(
            1
            for task in refreshed.values()
            if int(task.get("user_id") or 0) == user_id
        )
        await sync_user_concurrency_func(user_id, actual_count)
    return summary


async def async_main(args: argparse.Namespace) -> int:
    from src.billing_core_provider_setup import (
        ensure_billing_core_providers_registered,
    )
    from src.core.task_core_finalization import finalize_task_failure
    from src.core.task_core_runtime import sync_user_concurrency
    from src.task_core_provider_setup import (
        ensure_task_core_service_providers_registered,
    )

    ensure_billing_core_providers_registered()
    ensure_task_core_service_providers_registered()
    app_redis = await connect_redis(os.environ["REDIS_URL"])
    worker_redis = await connect_redis(os.environ["WORKER_REDIS_URL"])
    try:
        summary = await refund_pending_tasks(
            worker_redis=worker_redis,
            app_redis=app_redis,
            redis_prefix=os.environ.get("REDIS_PREFIX", "prod_bot_"),
            threshold=args.threshold,
            allow_above_threshold=args.allow_above_threshold,
            execute=args.execute,
            finalize_task_failure_func=finalize_task_failure,
            sync_user_concurrency_func=sync_user_concurrency,
        )
        print(json.dumps(asdict(summary), sort_keys=True))
        return 0
    except RefundGateError as exc:
        print(json.dumps({"error": str(exc), "status": "blocked"}, sort_keys=True))
        return 2
    except Exception:
        print(
            json.dumps(
                {"error": "refund execution failed", "status": "blocked"},
                sort_keys=True,
            )
        )
        return 3
    finally:
        await app_redis.aclose()
        await worker_redis.aclose()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=int, default=10)
    parser.add_argument("--allow-above-threshold", action="store_true")
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
