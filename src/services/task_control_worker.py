from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from config import REDIS_PREFIX
from src.control_worker_health import (
    build_task_control_worker_id,
)
from src.services.redis_client import redis_client
from src.services.task_web_finalizer import (
    process_all_pending_web_finalizers,
    run_pending_web_finalizer_event_listener,
)
from src.services.zombie_cleaner_service import clean_zombies

logger = logging.getLogger("task-control-worker")

RECONCILIATION_PHASES = {"prepared", "dispatching", "reconciling"}
FINALIZER_PHASES = {"accepted", "terminal"}
DEFAULT_LEASE_TTL_SECONDS = 30
DEFAULT_LEASE_RENEW_SECONDS = 10.0
DEFAULT_LEASE_RETRY_SECONDS = 5.0

_RENEW_LEASE_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('EXPIRE', KEYS[1], ARGV[2])
end
return 0
"""
_RELEASE_LEASE_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""


class LeaderLeaseStore(Protocol):
    async def acquire(
        self, lease_name: str, owner_token: str, ttl_seconds: int
    ) -> bool: ...

    async def renew(
        self, lease_name: str, owner_token: str, ttl_seconds: int
    ) -> bool: ...

    async def release(self, lease_name: str, owner_token: str) -> None: ...


class RedisLeaderLeaseStore:
    def __init__(self, redis) -> None:
        self._redis = redis

    @staticmethod
    def _key(lease_name: str) -> str:
        return f"{REDIS_PREFIX}task_control:leader:{lease_name}"

    async def acquire(
        self, lease_name: str, owner_token: str, ttl_seconds: int
    ) -> bool:
        return bool(
            await self._redis.set(
                self._key(lease_name),
                owner_token,
                nx=True,
                ex=int(ttl_seconds),
            )
        )

    async def renew(
        self, lease_name: str, owner_token: str, ttl_seconds: int
    ) -> bool:
        return bool(
            await self._redis.eval(
                _RENEW_LEASE_SCRIPT,
                1,
                self._key(lease_name),
                owner_token,
                int(ttl_seconds),
            )
        )

    async def release(self, lease_name: str, owner_token: str) -> None:
        await self._redis.eval(
            _RELEASE_LEASE_SCRIPT,
            1,
            self._key(lease_name),
            owner_token,
        )


@dataclass(frozen=True, slots=True)
class LeasedServiceSpec:
    lease_name: str
    runner: Callable[[], Awaitable[None]]


async def _renew_lease_until_lost(
    *,
    lease_name: str,
    owner_token: str,
    lease_store: LeaderLeaseStore,
    ttl_seconds: int,
    renew_interval_seconds: float,
    lease_state: dict[str, Any] | None = None,
) -> str:
    while True:
        await asyncio.sleep(max(0.0, renew_interval_seconds))
        if not await lease_store.renew(lease_name, owner_token, ttl_seconds):
            _record_lease_state(lease_state, "lost")
            return "lease_lost"
        _record_lease_state(lease_state, "renewing")


def _record_lease_state(
    state: dict[str, Any] | None,
    status: str,
) -> None:
    if state is None:
        return
    state["lease"] = {
        "status": status,
        "updated_at": time.time(),
    }


async def run_leased_worker_session(
    *,
    lease_name: str,
    runner: Callable[[], Awaitable[None]],
    lease_store: LeaderLeaseStore,
    owner_id: str,
    ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
    renew_interval_seconds: float = DEFAULT_LEASE_RENEW_SECONDS,
    lease_state: dict[str, Any] | None = None,
) -> str:
    owner_token = f"{owner_id}:{uuid.uuid4().hex}"
    if not await lease_store.acquire(lease_name, owner_token, ttl_seconds):
        _record_lease_state(lease_state, "not_acquired")
        return "not_acquired"
    _record_lease_state(lease_state, "acquired")

    runner_task = asyncio.create_task(runner(), name=f"task-control:{lease_name}")
    renew_task = asyncio.create_task(
        _renew_lease_until_lost(
            lease_name=lease_name,
            owner_token=owner_token,
            lease_store=lease_store,
            ttl_seconds=ttl_seconds,
            renew_interval_seconds=renew_interval_seconds,
            lease_state=lease_state,
        ),
        name=f"task-control:{lease_name}:lease-renewal",
    )
    try:
        done, _pending = await asyncio.wait(
            {runner_task, renew_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if renew_task in done:
            outcome = renew_task.result()
            runner_task.cancel()
            await asyncio.gather(runner_task, return_exceptions=True)
            return outcome
        renew_task.cancel()
        await asyncio.gather(renew_task, return_exceptions=True)
        await runner_task
        return "worker_completed"
    finally:
        for task in (runner_task, renew_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(runner_task, renew_task, return_exceptions=True)
        await lease_store.release(lease_name, owner_token)


async def _run_periodically(
    run_once: Callable[[], Awaitable[Any]],
    *,
    interval_seconds: float,
) -> None:
    while True:
        await run_once()
        await asyncio.sleep(max(0.0, interval_seconds))


async def run_submission_reconciliation_loop() -> None:
    async def reconcile_once() -> None:
        await process_all_pending_web_finalizers(
            phases=RECONCILIATION_PHASES,
            include_legacy_records=False,
            index_legacy_records=False,
        )

    await _run_periodically(
        reconcile_once,
        interval_seconds=float(
            os.getenv("TASK_CONTROL_RECONCILIATION_INTERVAL_SECONDS", "5")
        ),
    )


async def run_web_finalizer_control_loop() -> None:
    event_listener = asyncio.create_task(
        run_pending_web_finalizer_event_listener(),
        name="task-control:web-finalizer-events",
    )

    async def finalize_once() -> None:
        await process_all_pending_web_finalizers(
            phases=FINALIZER_PHASES,
            include_legacy_records=True,
        )

    try:
        await _run_periodically(
            finalize_once,
            interval_seconds=float(
                os.getenv("TASK_CONTROL_FINALIZER_INTERVAL_SECONDS", "5")
            ),
        )
    finally:
        event_listener.cancel()
        await asyncio.gather(event_listener, return_exceptions=True)


async def run_generic_zombie_sweep_loop() -> None:
    async def sweep_once() -> None:
        await clean_zombies(client_type=None, include_legacy=True)

    await _run_periodically(
        sweep_once,
        interval_seconds=float(
            os.getenv("TASK_CONTROL_ZOMBIE_INTERVAL_SECONDS", "600")
        ),
    )


def build_task_control_specs() -> tuple[LeasedServiceSpec, ...]:
    return (
        LeasedServiceSpec(
            lease_name="submission-reconciliation",
            runner=run_submission_reconciliation_loop,
        ),
        LeasedServiceSpec(
            lease_name="web-finalizer",
            runner=run_web_finalizer_control_loop,
        ),
        LeasedServiceSpec(
            lease_name="generic-zombie-sweep",
            runner=run_generic_zombie_sweep_loop,
        ),
    )


async def run_task_control_services(
    *,
    lease_store: LeaderLeaseStore | None = None,
    worker_id: str | None = None,
    task_states: dict[str, dict[str, Any]] | None = None,
) -> None:
    store = lease_store or RedisLeaderLeaseStore(redis_client.redis)
    owner_id = worker_id or build_task_control_worker_id()
    states = task_states if task_states is not None else {}

    async def run_spec(spec: LeasedServiceSpec) -> None:
        state = states.setdefault(spec.lease_name, {})
        while True:
            try:
                outcome = await run_leased_worker_session(
                    lease_name=spec.lease_name,
                    runner=spec.runner,
                    lease_store=store,
                    owner_id=owner_id,
                    lease_state=state,
                )
                state.update(outcome=outcome, updated_at=time.time())
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                state.update(
                    outcome="error",
                    error_type=type(exc).__name__,
                    updated_at=time.time(),
                )
                logger.exception(
                    "Task control service failed lease_name=%s",
                    spec.lease_name,
                )
            await asyncio.sleep(DEFAULT_LEASE_RETRY_SECONDS)

    await asyncio.gather(*(run_spec(spec) for spec in build_task_control_specs()))
