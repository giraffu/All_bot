#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_ENV_FILE = ROOT / ".env.cloud.prod"
DEFAULT_CONTROL_HOST = "allbot-do-sgp1-control"
PENDING_KEY = "comfy:queue:pending"
RUNNING_KEY = "comfy:queue:running"
TASK_PREFIX = "comfy:task:"
TASK_EVENT_PREFIX = "comfy:task_events:"
MAINTENANCE_CONTAINERS = (
    "cloud-web-api-prod",
    "cloud-tg-bot-prod",
    "cloud-qqcc-bot-prod",
)
GENERATION_MAINTENANCE_PATH = "/app/GENERATION_MAINTENANCE"
GENERATION_MAINTENANCE_RUNTIME_PATH = "/app/runtime-flags/GENERATION_MAINTENANCE"
REFUND_TASK_TYPE = "refund_prod_maintenance_release"


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        values[key] = value.strip().strip('"').strip("'")
    return values


def configure_process_env(values: dict[str, str]) -> None:
    mapping = {
        "DATABASE_URL": values.get("CLOUD_PROD_DATABASE_URL"),
        "REDIS_URL": values.get("CLOUD_PROD_REDIS_URL"),
        "WORKER_REDIS_URL": values.get("CLOUD_PROD_WORKER_REDIS_URL"),
        "API_BASE": "https://worker-central.aivison.it.com",
        "REDIS_PREFIX": "prod_bot_",
        "BOT_TYPE": "PROD",
    }
    passthrough = (
        "API_TOKEN",
        "AUTH_TOKEN",
        "MINIO_ENDPOINT",
        "MINIO_ACCESS_KEY",
        "MINIO_SECRET_KEY",
        "MINIO_BUCKET",
        "MINIO_INPUT_BUCKET",
        "MINIO_RESULT_BUCKET",
        "MINIO_TEMPLATE_BUCKET",
        "MINIO_SECURE",
        "R2_ENDPOINT",
        "R2_ACCESS_KEY",
        "R2_SECRET_KEY",
        "R2_BUCKET",
        "R2_PUBLIC_DOMAIN",
    )
    for key in passthrough:
        mapping[key] = values.get(key)
    for key, value in mapping.items():
        if value and not os.environ.get(key):
            os.environ[key] = value


def require_env(values: dict[str, str], *keys: str) -> None:
    missing = [key for key in keys if not values.get(key) and not os.environ.get(key)]
    if missing:
        raise SystemExit("missing required env keys: " + ", ".join(missing))


def run_ssh(host: str, script: str, *, execute: bool) -> None:
    if not execute:
        print(f"[dry-run] ssh {host!r} <<'REMOTE'\n{script.rstrip()}\nREMOTE")
        return
    subprocess.run(["ssh", host, "bash", "-s"], input=script, text=True, check=True)


def set_maintenance(host: str, *, enabled: bool, execute: bool) -> None:
    if enabled:
        operation = (
            f"mkdir -p {GENERATION_MAINTENANCE_RUNTIME_PATH.rsplit('/', 1)[0]} && "
            f"printf '1\\n' > {GENERATION_MAINTENANCE_PATH} && "
            f"printf '1\\n' > {GENERATION_MAINTENANCE_RUNTIME_PATH}"
        )
    else:
        operation = (
            f"rm -f {GENERATION_MAINTENANCE_PATH} "
            f"{GENERATION_MAINTENANCE_RUNTIME_PATH}"
        )
    script = "\n".join(
        [
            "set -euo pipefail",
            f"for container in {' '.join(MAINTENANCE_CONTAINERS)}; do",
            "  if docker ps --format '{{.Names}}' | grep -qx \"$container\"; then",
            f"    docker exec \"$container\" sh -lc {operation!r}",
            "    echo \"$container maintenance updated\"",
            "  else",
            "    echo \"$container not running; skipped\"",
            "  fi",
            "done",
        ]
    )
    run_ssh(host, script, execute=execute)


def maintenance_status(host: str) -> None:
    script = "\n".join(
        [
            "set -euo pipefail",
            f"for container in {' '.join(MAINTENANCE_CONTAINERS)}; do",
            "  if docker ps --format '{{.Names}}' | grep -qx \"$container\"; then",
            f"    if docker exec \"$container\" sh -lc 'test -f {GENERATION_MAINTENANCE_PATH} || test -f {GENERATION_MAINTENANCE_RUNTIME_PATH}'; then",
            "      echo \"$container=generation_maintenance\"",
            "    else",
            "      echo \"$container=open\"",
            "    fi",
            "  else",
            "    echo \"$container=not_running\"",
            "  fi",
            "done",
        ]
    )
    subprocess.run(["ssh", host, "bash", "-s"], input=script, text=True, check=True)


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
    pending_backend_ids = [str(item) for item in await worker_redis.zrange(PENDING_KEY, 0, -1)]
    running_backend_ids = [str(item) for item in await worker_redis.smembers(RUNNING_KEY)]
    active_tasks = await load_active_tasks(app_redis, redis_prefix)
    by_backend = {
        str(data.get("backend_task_id")): registry_id
        for registry_id, data in active_tasks.items()
        if data.get("backend_task_id")
    }
    mapped_pending = [backend_id for backend_id in pending_backend_ids if backend_id in by_backend]
    orphan_pending = [backend_id for backend_id in pending_backend_ids if backend_id not in by_backend]
    return {
        "pending_count": len(pending_backend_ids),
        "running_count": len(running_backend_ids),
        "active_task_count": len(active_tasks),
        "mapped_pending_count": len(mapped_pending),
        "orphan_pending_count": len(orphan_pending),
        "pending_backend_ids": pending_backend_ids,
        "running_backend_ids": running_backend_ids,
        "active_tasks": active_tasks,
        "registry_by_backend": by_backend,
    }


async def print_status(args, values: dict[str, str]) -> None:
    app_redis = await connect_redis(os.environ["REDIS_URL"])
    worker_redis = await connect_redis(os.environ["WORKER_REDIS_URL"])
    try:
        snapshot = await build_queue_snapshot(
            worker_redis,
            app_redis,
            os.environ.get("REDIS_PREFIX", "prod_bot_"),
        )
        print(
            json.dumps(
                {
                    "pending_count": snapshot["pending_count"],
                    "running_count": snapshot["running_count"],
                    "active_task_count": snapshot["active_task_count"],
                    "mapped_pending_count": snapshot["mapped_pending_count"],
                    "orphan_pending_count": snapshot["orphan_pending_count"],
                    "threshold": args.threshold,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        await app_redis.aclose()
        await worker_redis.aclose()


async def wait_pending_below(args, values: dict[str, str]) -> None:
    deadline = time.time() + args.timeout_seconds
    app_redis = await connect_redis(os.environ["REDIS_URL"])
    worker_redis = await connect_redis(os.environ["WORKER_REDIS_URL"])
    try:
        last_count = None
        while time.time() < deadline:
            snapshot = await build_queue_snapshot(
                worker_redis,
                app_redis,
                os.environ.get("REDIS_PREFIX", "prod_bot_"),
            )
            count = snapshot["pending_count"]
            if count < args.threshold:
                print(f"pending_count={count} below threshold={args.threshold}")
                return
            if count != last_count:
                print(f"waiting pending_count={count} threshold={args.threshold}")
                last_count = count
            await asyncio.sleep(args.interval_seconds)
        raise SystemExit(
            f"timed out waiting for pending_count < {args.threshold}"
        )
    finally:
        await app_redis.aclose()
        await worker_redis.aclose()


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


async def refund_pending(args, values: dict[str, str]) -> None:
    from src.core.task_core_finalization import finalize_task_failure
    from src.core.task_core_runtime import sync_user_concurrency

    app_redis = await connect_redis(os.environ["REDIS_URL"])
    worker_redis = await connect_redis(os.environ["WORKER_REDIS_URL"])
    affected_users: set[int] = set()
    try:
        snapshot = await build_queue_snapshot(
            worker_redis,
            app_redis,
            os.environ.get("REDIS_PREFIX", "prod_bot_"),
        )
        pending_count = snapshot["pending_count"]
        if pending_count >= args.threshold and not args.allow_above_threshold:
            raise SystemExit(
                f"refusing to refund while pending_count={pending_count} >= "
                f"threshold={args.threshold}; wait first or pass --allow-above-threshold"
            )
        if not snapshot["pending_backend_ids"]:
            print("no pending backend tasks to refund")
            return

        active_tasks: dict[str, dict[str, Any]] = snapshot["active_tasks"]
        registry_by_backend: dict[str, str] = snapshot["registry_by_backend"]
        summary = {
            "refunded": 0,
            "skipped_orphan": 0,
            "skipped_moved": 0,
            "dry_run": not args.execute,
        }
        for backend_task_id in snapshot["pending_backend_ids"]:
            registry_task_id = registry_by_backend.get(backend_task_id)
            if not registry_task_id:
                summary["skipped_orphan"] += 1
                print(f"skip orphan pending backend_task_id={backend_task_id}")
                continue
            task = active_tasks.get(registry_task_id) or {}
            user_id = task.get("user_id")
            username = str(task.get("username") or "Unknown")
            try:
                user_id_int = int(user_id)
            except (TypeError, ValueError):
                print(f"skip task without numeric user_id registry_task_id={registry_task_id}")
                summary["skipped_orphan"] += 1
                continue
            cost = int(task.get("cost") or 0)
            if not args.execute:
                print(
                    "would_refund "
                    f"registry_task_id={registry_task_id} backend_task_id={backend_task_id} "
                    f"user_id={user_id_int} cost={cost}"
                )
                summary["refunded"] += 1
                continue
            cancelled = await cancel_backend_pending(worker_redis, backend_task_id)
            if not cancelled:
                summary["skipped_moved"] += 1
                print(f"skip moved backend_task_id={backend_task_id}")
                continue
            await finalize_task_failure(
                internal_user_id=user_id_int,
                username=username,
                cost=cost,
                should_refund=cost > 0,
                registry_task_id=registry_task_id,
                refund_task_type=REFUND_TASK_TYPE,
                explicit_user_message="发布维护取消排队任务，已退还预扣灵石。",
            )
            affected_users.add(user_id_int)
            summary["refunded"] += 1
            print(
                f"refunded registry_task_id={registry_task_id} "
                f"backend_task_id={backend_task_id} user_id={user_id_int} cost={cost}"
            )

        if args.execute and affected_users:
            refreshed = await load_active_tasks(
                app_redis,
                os.environ.get("REDIS_PREFIX", "prod_bot_"),
            )
            for user_id in sorted(affected_users):
                actual_count = sum(
                    1 for task in refreshed.values() if int(task.get("user_id") or 0) == user_id
                )
                await sync_user_concurrency(user_id, actual_count)
                print(f"sync_user_concurrency user_id={user_id} actual_count={actual_count}")

        print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        await app_redis.aclose()
        await worker_redis.aclose()


async def async_main(args) -> None:
    values = load_env_file(Path(args.env_file))
    configure_process_env(values)
    require_env(
        values,
        "CLOUD_PROD_REDIS_URL",
        "CLOUD_PROD_WORKER_REDIS_URL",
        "CLOUD_PROD_DATABASE_URL",
    )
    if args.action == "status":
        await print_status(args, values)
    elif args.action == "wait-pending":
        await wait_pending_below(args, values)
    elif args.action == "refund-pending":
        await refund_pending(args, values)
    else:
        raise SystemExit(f"unsupported async action: {args.action}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cloud prod generation release gate for maintenance, queue drain and pending refunds."
    )
    parser.add_argument(
        "action",
        choices=(
            "status",
            "enable-maintenance",
            "disable-maintenance",
            "maintenance-status",
            "wait-pending",
            "refund-pending",
        ),
    )
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    parser.add_argument("--control-host", default=DEFAULT_CONTROL_HOST)
    parser.add_argument("--threshold", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=int, default=7200)
    parser.add_argument("--interval-seconds", type=int, default=15)
    parser.add_argument("--allow-above-threshold", action="store_true")
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.action == "enable-maintenance":
        set_maintenance(args.control_host, enabled=True, execute=args.execute)
        return 0
    if args.action == "disable-maintenance":
        set_maintenance(args.control_host, enabled=False, execute=args.execute)
        return 0
    if args.action == "maintenance-status":
        maintenance_status(args.control_host)
        return 0
    asyncio.run(async_main(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
