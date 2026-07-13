from __future__ import annotations

import asyncio
import secrets
from contextlib import asynccontextmanager

from config import REDIS_PREFIX
from src.services.redis_client import redis_client


PRIVATE_BOT_TASK_MONITOR_LEASE_TTL_SECONDS = 20
PRIVATE_BOT_TASK_MONITOR_RENEW_SECONDS = 5.0

_RENEW_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('EXPIRE', KEYS[1], ARGV[2])
end
return 0
"""
_RELEASE_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""


class PrivateBotTaskMonitorLeaseError(RuntimeError):
    pass


class PrivateBotTaskMonitorAlreadyOwned(PrivateBotTaskMonitorLeaseError):
    pass


class PrivateBotTaskMonitorInterrupted(PrivateBotTaskMonitorLeaseError):
    pass


@asynccontextmanager
async def private_bot_task_monitor_lease(
    registry_task_id: str,
    *,
    redis=None,
    ttl_seconds: int = PRIVATE_BOT_TASK_MONITOR_LEASE_TTL_SECONDS,
    renew_seconds: float = PRIVATE_BOT_TASK_MONITOR_RENEW_SECONDS,
):
    """Give one process exclusive monitor/result-delivery ownership."""

    normalized_task_id = str(registry_task_id or "").strip()
    if not normalized_task_id:
        raise PrivateBotTaskMonitorLeaseError("registry task id is required")
    redis = redis if redis is not None else redis_client.redis
    key = f"{REDIS_PREFIX}private_qqcc_bot:task_monitor:{normalized_task_id}"
    lease = secrets.token_urlsafe(24)
    try:
        acquired = await redis.set(
            key,
            lease,
            ex=max(1, int(ttl_seconds)),
            nx=True,
        )
    except Exception as exc:
        raise PrivateBotTaskMonitorLeaseError(
            "private Bot task monitor coordination is unavailable"
        ) from exc
    if not acquired:
        raise PrivateBotTaskMonitorAlreadyOwned(
            "private Bot task already has a monitor owner"
        )

    owner_task = asyncio.current_task()
    stop = asyncio.Event()
    lease_lost = asyncio.Event()

    async def renew() -> None:
        while not stop.is_set():
            try:
                await asyncio.wait_for(
                    stop.wait(),
                    timeout=max(0.1, float(renew_seconds)),
                )
                return
            except asyncio.TimeoutError:
                pass
            try:
                renewed = await redis.eval(
                    _RENEW_SCRIPT,
                    1,
                    key,
                    lease,
                    str(max(1, int(ttl_seconds))),
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                renewed = 0
            if int(renewed or 0) != 1:
                lease_lost.set()
                if owner_task is not None and not owner_task.done():
                    owner_task.cancel()
                return

    renewal_task = asyncio.create_task(
        renew(),
        name=f"private-qqcc-task-monitor-{normalized_task_id}",
    )
    try:
        yield
        if lease_lost.is_set():
            raise PrivateBotTaskMonitorInterrupted(
                "private Bot task monitor lease was lost"
            )
    except asyncio.CancelledError:
        raise PrivateBotTaskMonitorInterrupted(
            "private Bot task monitor was interrupted"
        ) from None
    finally:
        stop.set()
        renewal_task.cancel()
        await asyncio.gather(renewal_task, return_exceptions=True)
        try:
            await redis.eval(_RELEASE_SCRIPT, 1, key, lease)
        except Exception:
            pass
