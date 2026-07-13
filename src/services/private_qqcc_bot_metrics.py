from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from config import REDIS_PREFIX


DEFAULT_PRIVATE_QQCC_CONSUMER_GROUP = "private-qqcc-bot-workers"
PRIVATE_QQCC_WORKER_METRICS_TTL_SECONDS = 90


def private_qqcc_metrics_hash_key(redis_prefix: str = REDIS_PREFIX) -> str:
    return f"{redis_prefix}private_qqcc_bot:metrics:counters"


def private_qqcc_worker_metrics_key(redis_prefix: str = REDIS_PREFIX) -> str:
    return f"{redis_prefix}private_qqcc_bot:metrics:worker"


def private_qqcc_update_stream_key(redis_prefix: str = REDIS_PREFIX) -> str:
    return f"{redis_prefix}private_qqcc_bot:webhook:updates"


def _text(value: Any) -> str:
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value)


def _integer(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


async def publish_private_qqcc_worker_metrics(
    redis,
    *,
    active_applications: int,
    update_processing_failures: int,
    dead_lettered_updates: int,
    recovery_failures: int,
    inflight_updates: int,
    max_inflight_updates: int,
    deferred_updates: int,
    redis_prefix: str = REDIS_PREFIX,
    now: datetime | None = None,
) -> None:
    payload = {
        "active_applications": max(0, int(active_applications)),
        "update_processing_failures_since_start": max(
            0, int(update_processing_failures)
        ),
        "dead_lettered_updates_since_start": max(0, int(dead_lettered_updates)),
        "recovery_failures_since_start": max(0, int(recovery_failures)),
        "inflight_updates": max(0, int(inflight_updates)),
        "max_inflight_updates": max(1, int(max_inflight_updates)),
        "deferred_updates": max(0, int(deferred_updates)),
        "updated_at": (now or datetime.now()).isoformat(),
    }
    await redis.set(
        private_qqcc_worker_metrics_key(redis_prefix),
        json.dumps(payload, separators=(",", ":")),
        ex=PRIVATE_QQCC_WORKER_METRICS_TTL_SECONDS,
    )


async def collect_private_qqcc_runtime_metrics(
    redis,
    *,
    redis_prefix: str = REDIS_PREFIX,
    consumer_group: str | None = None,
) -> dict[str, Any]:
    resolved_consumer_group = consumer_group or os.getenv(
        "PRIVATE_QQCC_BOT_WORKER_CONSUMER_GROUP",
        DEFAULT_PRIVATE_QQCC_CONSUMER_GROUP,
    )
    stream_key = private_qqcc_update_stream_key(redis_prefix)
    counters_key = private_qqcc_metrics_hash_key(redis_prefix)
    worker_key = private_qqcc_worker_metrics_key(redis_prefix)
    try:
        backlog = _integer(await redis.xlen(stream_key))
        raw_counters = await redis.hgetall(counters_key)
        raw_worker = await redis.get(worker_key)
    except Exception:
        return {
            "available": False,
            "error_code": "private_bot_metrics_unavailable",
        }

    pending: int | None
    try:
        pending_payload = await redis.xpending(stream_key, resolved_consumer_group)
        if isinstance(pending_payload, dict):
            pending = _integer(
                pending_payload.get("pending")
                if "pending" in pending_payload
                else pending_payload.get(b"pending")
            )
        elif isinstance(pending_payload, (list, tuple)) and pending_payload:
            pending = _integer(pending_payload[0])
        else:
            pending = _integer(pending_payload)
    except Exception:
        # Before the worker creates its consumer group there cannot be a
        # meaningful pending count, but the stream backlog remains observable.
        pending = None

    counters = {
        _text(key): _integer(value)
        for key, value in dict(raw_counters or {}).items()
    }
    worker: dict[str, Any] | None = None
    if raw_worker:
        try:
            decoded = json.loads(_text(raw_worker))
            if isinstance(decoded, dict):
                worker = decoded
        except (TypeError, ValueError, json.JSONDecodeError):
            worker = None
    return {
        "available": True,
        "stream_backlog": backlog,
        "stream_pending": pending,
        "counters": counters,
        "worker": worker,
        "worker_heartbeat_fresh": worker is not None,
    }
