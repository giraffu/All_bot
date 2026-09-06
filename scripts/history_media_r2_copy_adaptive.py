#!/usr/bin/env python3
"""Run one frozen History R2 copy plan with graceful, adaptive batching."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import resource
import signal
import sys
import time
from collections import Counter, deque
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.history_media_r2_migration import (  # noqa: E402
    AdaptiveCopyController,
    AdaptiveConcurrencyLimiter,
    _bounded_copy_concurrency,
    _bounded_copy_retries,
    _execute_copy,
    _positive_float,
    _positive_pool_connections,
    _resolve_copy_max_pool_connections,
    _unit_ratio,
)

BatchExecutor = Callable[[Any], Awaitable[dict[str, Any]]]
Sleep = Callable[[float], Awaitable[None]]
R2_P95_LOWER_MS = 8_000.0
R2_P95_RAISE_MS = 5_000.0
R2_MAX_LOWER_MS = 120_000.0
R2_MAX_RAISE_MS = 30_000.0
R2_LATENCY_SUSTAINED_WINDOWS = 2
RATE_LIMIT_COOLDOWN_SECONDS = 60.0


@dataclass
class ResourceGate:
    max_cpu_percent: float = 70.0
    cpu_batches_to_pause: int = 3
    max_fd_ratio: float = 0.5
    db_commit_p95_baseline_ms: float | None = None
    db_latency_multiplier: float = 3.0

    def __post_init__(self) -> None:
        self.high_cpu_batches = 0

    def evaluate(
        self,
        *,
        capacity_cpu_percent: float,
        fd_count: int,
        fd_soft_limit: int,
        db_commit_p95_ms: float | None = None,
    ) -> str | None:
        if fd_soft_limit > 0 and fd_count > fd_soft_limit * self.max_fd_ratio:
            return "fd_above_half_soft_limit"
        if (
            self.db_commit_p95_baseline_ms is not None
            and db_commit_p95_ms is not None
            and db_commit_p95_ms
            > self.db_commit_p95_baseline_ms * self.db_latency_multiplier
        ):
            return "db_commit_latency_regressed"
        if capacity_cpu_percent > self.max_cpu_percent:
            self.high_cpu_batches += 1
        else:
            self.high_cpu_batches = 0
        if self.high_cpu_batches >= self.cpu_batches_to_pause:
            return "sustained_cpu_above_limit"
        return None


@dataclass(frozen=True)
class CopyHealthDecision:
    action: str
    reason: str
    error_rate: float
    sample_count: int


@dataclass(frozen=True)
class ResourceSample:
    process_cpu_percent: float
    capacity_cpu_percent: float
    available_cpu_count: int
    fd_count: int
    fd_soft_limit: int


class CopyHealthWindow:
    """Bound global concurrency by recent request health, not batch perfection."""

    def __init__(
        self,
        *,
        max_requests: int = 1000,
        max_age_seconds: float = 60.0,
        lower_error_rate: float = 0.005,
        raise_error_rate: float = 0.002,
        systemic_error_rate: float = 0.10,
        minimum_samples: int = 200,
        minimum_observation_seconds: float = 30.0,
    ) -> None:
        self.max_requests = max_requests
        self.max_age_seconds = max_age_seconds
        self.lower_error_rate = lower_error_rate
        self.raise_error_rate = raise_error_rate
        self.systemic_error_rate = systemic_error_rate
        self.minimum_samples = minimum_samples
        self.minimum_observation_seconds = minimum_observation_seconds
        self._events: deque[dict[str, Any]] = deque()
        self._latest: list[dict[str, Any]] = []

    def reset(self) -> None:
        """Start a fresh observation epoch after changing concurrency."""
        self._events.clear()
        self._latest = []

    def extend(self, events: list[dict[str, Any]]) -> None:
        self._latest = sorted(
            (dict(event) for event in events), key=lambda event: float(event["at"])
        )
        self._events.extend(self._latest)
        while len(self._events) > self.max_requests:
            self._events.popleft()
        if self._events:
            cutoff = float(self._events[-1]["at"]) - self.max_age_seconds
            while self._events and float(self._events[0]["at"]) < cutoff:
                self._events.popleft()

    def decision(self, *, current_concurrency: int) -> CopyHealthDecision:
        sample_count = len(self._events)
        errors = sum(event["kind"] != "ok" for event in self._events)
        error_rate = errors / sample_count if sample_count else 0.0
        observation_seconds = (
            float(self._events[-1]["at"]) - float(self._events[0]["at"])
            if sample_count > 1
            else 0.0
        )
        observation_ready = (
            sample_count >= self.minimum_samples
            or observation_seconds >= self.minimum_observation_seconds
        )
        latest_rate_limits = sum(
            event["kind"] == "rate_limit" for event in self._latest
        )
        if latest_rate_limits:
            return CopyHealthDecision("lower", "rate_limit", error_rate, sample_count)
        if observation_ready and error_rate >= self.systemic_error_rate:
            return CopyHealthDecision(
                "systemic", "systemic_transient_error_rate", error_rate, sample_count
            )
        if observation_ready and error_rate > self.lower_error_rate:
            return CopyHealthDecision(
                "lower", "sustained_transient_error_rate", error_rate, sample_count
            )
        if observation_ready and error_rate < self.raise_error_rate:
            return CopyHealthDecision(
                "raise", "low_transient_error_rate", error_rate, sample_count
            )
        return CopyHealthDecision(
            "hold", "within_error_budget", error_rate, sample_count
        )


@dataclass(frozen=True)
class CopyLatencyDecision:
    action: str
    reason: str
    p95_ms: float
    max_ms: float


class CopyLatencyWindow:
    """Report R2 latency without turning one long tail into a global downshift."""

    def __init__(
        self,
        *,
        p95_lower_ms: float = 8_000,
        p95_raise_ms: float = 5_000,
        max_lower_ms: float = 120_000,
        max_raise_ms: float = 30_000,
        sustained_windows: int = 2,
    ) -> None:
        if not 0 < p95_raise_ms < p95_lower_ms:
            raise ValueError("R2 p95 raise threshold must be below lower threshold")
        if not 0 < max_raise_ms < max_lower_ms:
            raise ValueError("R2 max raise threshold must be below lower threshold")
        if sustained_windows <= 0:
            raise ValueError("R2 latency sustained windows must be positive")
        self.p95_lower_ms = p95_lower_ms
        self.p95_raise_ms = p95_raise_ms
        self.max_lower_ms = max_lower_ms
        self.max_raise_ms = max_raise_ms
        self.sustained_windows = sustained_windows
        self.high_p95_windows = 0

    def reset(self) -> None:
        self.high_p95_windows = 0

    def decision(self, *, p95_ms: float, max_ms: float) -> CopyLatencyDecision:
        if max_ms >= self.max_lower_ms:
            return CopyLatencyDecision(
                "hold", "r2_extreme_long_tail_observed", p95_ms, max_ms
            )
        if p95_ms >= self.p95_lower_ms:
            self.high_p95_windows += 1
            if self.high_p95_windows >= self.sustained_windows:
                return CopyLatencyDecision(
                    "hold", "sustained_r2_p95_observed", p95_ms, max_ms
                )
            return CopyLatencyDecision(
                "hold", "r2_p95_latency_observing", p95_ms, max_ms
            )
        self.high_p95_windows = 0
        if p95_ms <= self.p95_raise_ms and max_ms <= self.max_raise_ms:
            return CopyLatencyDecision("raise", "healthy_r2_latency", p95_ms, max_ms)
        return CopyLatencyDecision("hold", "r2_latency_guard_band", p95_ms, max_ms)


def _available_cpu_count() -> int:
    """Return CPUs available to this process, respecting container cpusets."""
    try:
        affinity_count = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        affinity_count = 0
    return max(1, affinity_count or os.cpu_count() or 1)


def _resource_sample(*, cpu_started: float, wall_started: float) -> ResourceSample:
    wall_seconds = max(time.perf_counter() - wall_started, 1e-9)
    process_cpu_percent = max(
        0.0, (time.process_time() - cpu_started) / wall_seconds * 100
    )
    available_cpu_count = _available_cpu_count()
    capacity_cpu_percent = process_cpu_percent / available_cpu_count
    fd_count = len(os.listdir("/proc/self/fd"))
    fd_soft_limit = int(resource.getrlimit(resource.RLIMIT_NOFILE)[0])
    return ResourceSample(
        process_cpu_percent=round(process_cpu_percent, 3),
        capacity_cpu_percent=round(capacity_cpu_percent, 3),
        available_cpu_count=available_cpu_count,
        fd_count=fd_count,
        fd_soft_limit=fd_soft_limit,
    )


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True), flush=True)


def _summarize_request_evidence(events: list[dict[str, Any]]) -> dict[str, Any]:
    errors = [event for event in events if event.get("kind") != "ok"]
    rate_limits = [event for event in errors if event.get("kind") == "rate_limit"]
    return {
        "request_error_kinds": dict(
            sorted(Counter(str(event.get("kind")) for event in errors).items())
        ),
        "request_error_stages": dict(
            sorted(
                Counter(
                    str(event["stage"]) for event in errors if event.get("stage")
                ).items()
            )
        ),
        "http_status_counts": dict(
            sorted(
                Counter(
                    str(event["http_status"])
                    for event in errors
                    if event.get("http_status") is not None
                ).items()
            )
        ),
        "provider_request_fingerprint_sample": sorted(
            {
                str(event["provider_request_id_sha256"])
                for event in errors
                if event.get("provider_request_id_sha256")
            }
        )[:8],
        "rate_limit_cooldown_seconds": (
            max(
                float(event["rate_limit_cooldown_seconds"])
                for event in rate_limits
                if event.get("rate_limit_cooldown_seconds") is not None
            )
            if any(
                event.get("rate_limit_cooldown_seconds") is not None
                for event in rate_limits
            )
            else None
        ),
        "rate_limit_new_concurrency": (
            min(
                int(event["rate_limit_new_concurrency"])
                for event in rate_limits
                if event.get("rate_limit_new_concurrency") is not None
            )
            if any(
                event.get("rate_limit_new_concurrency") is not None
                for event in rate_limits
            )
            else None
        ),
    }


def _bucket_safe_copy_concurrency(value: str) -> int:
    concurrency = _bounded_copy_concurrency(value)
    if concurrency not in {16, 32}:
        raise argparse.ArgumentTypeError(
            "bucket-safe adaptive Copy concurrency must be 16 or 32"
        )
    return concurrency


def _partition_capacity(total: int, parts: int, index: int) -> int:
    base, remainder = divmod(total, parts)
    return base + int(index < remainder)


class ShardedBatchCoordinator:
    """Roll fixed logical lanes over frozen batches without a global tail barrier."""

    def __init__(
        self,
        args: argparse.Namespace | SimpleNamespace,
        *,
        execute_batch: BatchExecutor,
    ) -> None:
        self.args = args
        self.execute_batch = execute_batch
        self.shard_count = int(args.shard_count)
        self.shard_size = int(args.shard_size)
        self.retry_workers = int(args.retry_concurrency)
        pool_ceiling = (
            int(args.max_pool_connections)
            if args.max_pool_connections is not None
            else 128
        )
        configured_maximum = int(
            getattr(args, "maximum_copy_concurrency", 128)
        )
        self.maximum_concurrency = next(
            (
                level
                for level in (128, 64, 32, 16)
                if pool_ceiling >= level and configured_maximum >= level
            ),
            0,
        )
        if self.maximum_concurrency == 0:
            raise ValueError("adaptive Copy connection pool must support at least 16")
        if self.shard_count <= 0:
            raise ValueError("copy shard count must be positive")
        if self.shard_size <= 0:
            raise ValueError("copy shard size must be positive")
        if not 0 < self.retry_workers < self.maximum_concurrency:
            raise ValueError("retry concurrency must be below total concurrency")
        self.bulk_workers = self.maximum_concurrency - self.retry_workers
        self.bulk_executor = ThreadPoolExecutor(
            max_workers=self.bulk_workers,
            thread_name_prefix="history-r2-copy-bulk",
        )
        self.retry_executor = ThreadPoolExecutor(
            max_workers=self.retry_workers,
            thread_name_prefix="history-r2-copy-retry",
        )
        self.limiter = AdaptiveConcurrencyLimiter(limit=self.maximum_concurrency)
        self._tasks: dict[int, asyncio.Task[dict[str, Any]]] = {}
        self._terminal_lanes: set[int] = set()
        self._finalized = False
        self._preflight_done = False
        self._live_request_events: deque[dict[str, Any]] = deque(maxlen=1000)

    def _record_request_event(self, event: dict[str, Any]) -> None:
        self._live_request_events.append(dict(event))

    def _with_live_request_events(self, summary: dict[str, Any]) -> dict[str, Any]:
        result = dict(summary)
        result["_copy_request_events"] = list(self._live_request_events)
        self._live_request_events.clear()
        return result

    def _batch_args(
        self, batch_args: argparse.Namespace | SimpleNamespace, lane: int
    ) -> SimpleNamespace:
        global_pool = int(
            batch_args.max_pool_connections
            or _resolve_copy_max_pool_connections(self.maximum_concurrency, None)
        )
        lane_concurrency = _partition_capacity(
            self.maximum_concurrency, self.shard_count, lane
        )
        lane_pool = _partition_capacity(global_pool, self.shard_count, lane)
        if lane_concurrency <= 0 or lane_pool < lane_concurrency:
            raise ValueError("copy shard capacity is smaller than its lane count")
        values = dict(vars(batch_args))
        values.update(
            {
                "limit": self.shard_size,
                "copy_concurrency": lane_concurrency,
                "max_pool_connections": lane_pool,
                "global_max_pool_connections": global_pool,
                "copy_shard_count": self.shard_count,
                "copy_shard_index": lane,
                "bulk_executor": self.bulk_executor,
                "retry_executor": self.retry_executor,
                "concurrency_limiter": self.limiter,
                "global_copy_concurrency": self.maximum_concurrency,
                "bulk_workers": self.bulk_workers,
                "retry_workers": self.retry_workers,
                "request_event_sink": self._record_request_event,
                "finalize_plan": False,
                "skip_global_preflight": True,
            }
        )
        return SimpleNamespace(**values)

    def _start_available_lanes(
        self, batch_args: argparse.Namespace | SimpleNamespace
    ) -> None:
        for lane in range(self.shard_count):
            if lane in self._terminal_lanes or lane in self._tasks:
                continue
            self._tasks[lane] = asyncio.create_task(
                self.execute_batch(self._batch_args(batch_args, lane))
            )

    async def execute_next(
        self, batch_args: argparse.Namespace | SimpleNamespace
    ) -> dict[str, Any]:
        if not self._preflight_done:
            preflight_values = dict(vars(batch_args))
            preflight_values.update(
                {
                    "preflight_only": True,
                    "skip_global_preflight": False,
                    "copy_shard_count": 1,
                    "copy_shard_index": 0,
                }
            )
            await self.execute_batch(SimpleNamespace(**preflight_values))
            self._preflight_done = True
        self.limiter.set_limit(int(batch_args.copy_concurrency))
        self._start_available_lanes(batch_args)
        while self._tasks:
            done, _pending = await asyncio.wait(
                set(self._tasks.values()), return_when=asyncio.FIRST_COMPLETED
            )
            completed_lanes = sorted(
                lane for lane, task in self._tasks.items() if task in done
            )
            lane = completed_lanes[0]
            task = self._tasks.pop(lane)
            summary = await task
            if int(summary.get("remaining", 1)) == 0:
                if self._tasks:
                    await asyncio.gather(*self._tasks.values(), return_exceptions=False)
                    self._tasks.clear()
                final_values = dict(vars(batch_args))
                final_values.update(
                    {
                        "limit": self.shard_size,
                        "copy_shard_count": 1,
                        "copy_shard_index": 0,
                        "finalize_plan": True,
                        "skip_global_preflight": True,
                    }
                )
                self._finalized = True
                final_summary = await self.execute_batch(
                    SimpleNamespace(**final_values)
                )
                return self._with_live_request_events(final_summary)
            if summary.get("shard_complete"):
                self._terminal_lanes.add(lane)
                self._start_available_lanes(batch_args)
                continue
            return self._with_live_request_events(summary)
        if not self._finalized:
            final_values = dict(vars(batch_args))
            final_values.update(
                {
                    "limit": self.shard_size,
                    "copy_shard_count": 1,
                    "copy_shard_index": 0,
                    "finalize_plan": True,
                    "skip_global_preflight": True,
                }
            )
            self._finalized = True
            final_summary = await self.execute_batch(SimpleNamespace(**final_values))
            return self._with_live_request_events(final_summary)
        return {
            "remaining": 0,
            "copied_objects": 0,
            "_copy_request_events": [],
            "r2_object_operation_latency_ms": {"p95": 0, "max": 0},
            "db_commit_latency_ms": {"p95": 0},
        }

    async def close(self) -> None:
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self.bulk_executor.shutdown(wait=True, cancel_futures=False)
        self.retry_executor.shutdown(wait=True, cancel_futures=False)


async def run_sharded_adaptive_copy(
    args: argparse.Namespace | SimpleNamespace,
    *,
    execute_batch: BatchExecutor = _execute_copy,
    sleep: Sleep = asyncio.sleep,
    pause_requested: Callable[[], bool] = lambda: False,
) -> dict[str, Any]:
    coordinator = ShardedBatchCoordinator(args, execute_batch=execute_batch)
    try:
        return await run_adaptive_copy(
            args,
            execute_batch=coordinator.execute_next,
            sleep=sleep,
            pause_requested=pause_requested,
        )
    finally:
        await coordinator.close()


async def run_adaptive_copy(
    args: argparse.Namespace | SimpleNamespace,
    *,
    execute_batch: BatchExecutor = _execute_copy,
    sleep: Sleep = asyncio.sleep,
    pause_requested: Callable[[], bool] = lambda: False,
) -> dict[str, Any]:
    configured_pool = args.max_pool_connections
    pool_ceiling = configured_pool if configured_pool is not None else 128
    configured_maximum = int(getattr(args, "maximum_copy_concurrency", 128))
    maximum_concurrency = next(
        (
            level
            for level in (128, 64, 32, 16)
            if pool_ceiling >= level and configured_maximum >= level
        ),
        0,
    )
    if maximum_concurrency == 0:
        raise ValueError("adaptive Copy connection pool must support at least 16")
    controller = AdaptiveCopyController(
        initial_concurrency=int(args.copy_concurrency),
        maximum_concurrency=maximum_concurrency,
    )
    _resolve_copy_max_pool_connections(controller.maximum_concurrency, configured_pool)
    systemic_windows = 0
    health = CopyHealthWindow()
    latency = CopyLatencyWindow(
        p95_lower_ms=R2_P95_LOWER_MS,
        p95_raise_ms=R2_P95_RAISE_MS,
        max_lower_ms=R2_MAX_LOWER_MS,
        max_raise_ms=R2_MAX_RAISE_MS,
        sustained_windows=R2_LATENCY_SUSTAINED_WINDOWS,
    )
    resource_gate = ResourceGate(
        max_cpu_percent=float(getattr(args, "max_cpu_percent", 70.0)),
        cpu_batches_to_pause=int(getattr(args, "cpu_batches_to_pause", 3)),
        db_commit_p95_baseline_ms=getattr(args, "db_commit_p95_baseline_ms", None),
        db_latency_multiplier=float(getattr(args, "db_latency_multiplier", 3.0)),
    )

    while True:
        concurrency = controller.concurrency
        batch_args = SimpleNamespace(
            plan_sha256=args.plan_sha256,
            confirm=args.confirm,
            config=args.config,
            artifact_digest=getattr(args, "artifact_digest", None),
            limit=args.limit,
            copy_concurrency=concurrency,
            max_pool_connections=configured_pool,
            next_plan_output=getattr(args, "next_plan_output", None),
            verification_output=getattr(args, "verification_output", None),
            object_max_retries=int(getattr(args, "object_max_retries", 5)),
            retry_base_seconds=float(getattr(args, "retry_base_seconds", 1.0)),
            retry_max_seconds=float(getattr(args, "retry_max_seconds", 16.0)),
            retry_jitter_ratio=float(getattr(args, "retry_jitter_ratio", 0.25)),
            rate_limit_cooldown_seconds=RATE_LIMIT_COOLDOWN_SECONDS,
        )
        cpu_started = time.process_time()
        wall_started = time.perf_counter()
        try:
            summary = await execute_batch(batch_args)
        except Exception as exc:  # noqa: BLE001 - classify at the batch boundary
            previous = controller.concurrency
            error_text = f"{type(exc).__name__}: {exc}"
            try:
                lowered = controller.record_failure(error_text)
            except RuntimeError:
                _emit(
                    {
                        "adaptive_event": "paused",
                        "reason": "non_transient_failure",
                        "copy_concurrency": previous,
                    }
                )
                raise
            if previous == 16:
                systemic_windows += 1
                if systemic_windows >= int(getattr(args, "circuit_breaker_windows", 3)):
                    return {
                        "status": "paused",
                        "reason": "systemic_transient_error_circuit_open",
                        "copy_concurrency": 16,
                        "max_pool_connections": _resolve_copy_max_pool_connections(
                            16, configured_pool
                        ),
                    }
            else:
                systemic_windows = 0
            if lowered < previous:
                health.reset()
                latency.reset()
            wait_seconds = {64: 30, 32: 60, 16: 120}[lowered]
            _emit(
                {
                    "adaptive_event": "lower" if lowered < previous else "retry",
                    "copy_concurrency": lowered,
                    "wait_seconds": wait_seconds,
                }
            )
            await sleep(wait_seconds)
            continue

        remaining = int(summary["remaining"])
        resource_sample = _resource_sample(
            cpu_started=cpu_started, wall_started=wall_started
        )
        db_commit_p95_ms = float(
            (summary.get("db_commit_latency_ms") or {}).get("p95", 0.0)
        )
        resource_reason = resource_gate.evaluate(
            capacity_cpu_percent=resource_sample.capacity_cpu_percent,
            fd_count=resource_sample.fd_count,
            fd_soft_limit=resource_sample.fd_soft_limit,
            db_commit_p95_ms=db_commit_p95_ms,
        )
        _emit(
            {
                "adaptive_event": "batch_resource",
                "process_cpu_percent": resource_sample.process_cpu_percent,
                "capacity_cpu_percent": resource_sample.capacity_cpu_percent,
                "available_cpu_count": resource_sample.available_cpu_count,
                "fd_count": resource_sample.fd_count,
                "fd_soft_limit": resource_sample.fd_soft_limit,
                "db_commit_p95_ms": db_commit_p95_ms,
            }
        )
        actual_pool = int(
            summary.get(
                "max_pool_connections",
                _resolve_copy_max_pool_connections(concurrency, configured_pool),
            )
        )
        all_request_events = list(summary.get("_copy_request_events") or [])
        request_events = [
            event
            for event in all_request_events
            if int(event.get("copy_concurrency", concurrency)) == concurrency
        ]
        stale_request_events = len(all_request_events) - len(request_events)
        health.extend(request_events)
        health_decision = health.decision(current_concurrency=concurrency)
        r2_latency = summary.get("r2_object_operation_latency_ms") or {}
        latency_decision = latency.decision(
            p95_ms=float(r2_latency.get("p95", 0.0)),
            max_ms=float(r2_latency.get("max", 0.0)),
        )
        _emit(
            {
                "adaptive_event": "batch_r2_health",
                "r2_p95_ms": latency_decision.p95_ms,
                "r2_max_ms": latency_decision.max_ms,
                "copy_objects_per_second": float(
                    summary.get("copy_objects_per_second", 0.0)
                ),
                "latency_action": latency_decision.action,
                "latency_reason": latency_decision.reason,
                "request_error_rate": health_decision.error_rate,
                "request_sample_count": health_decision.sample_count,
                "stale_request_events_ignored": stale_request_events,
                **_summarize_request_evidence(request_events),
            }
        )
        if health_decision.action == "systemic":
            systemic_windows += 1
            if concurrency > 16:
                lowered = controller.record_failure("ReadTimeoutError")
                health.reset()
                latency.reset()
                _emit(
                    {
                        "adaptive_event": "lower",
                        "reason": health_decision.reason,
                        "copy_concurrency": lowered,
                        "request_error_rate": health_decision.error_rate,
                        "request_sample_count": health_decision.sample_count,
                    }
                )
            elif systemic_windows >= int(getattr(args, "circuit_breaker_windows", 3)):
                return {
                    "status": "paused",
                    "reason": "systemic_transient_error_circuit_open",
                    "remaining": remaining,
                    "copy_concurrency": concurrency,
                    "max_pool_connections": actual_pool,
                }
        elif health_decision.action == "lower":
            systemic_windows = 0
            lowered = controller.record_failure(
                "SlowDown"
                if health_decision.reason == "rate_limit"
                else "ReadTimeoutError"
            )
            health.reset()
            latency.reset()
            _emit(
                {
                    "adaptive_event": "lower",
                    "reason": health_decision.reason,
                    "copy_concurrency": lowered,
                    "request_error_rate": health_decision.error_rate,
                    "request_sample_count": health_decision.sample_count,
                }
            )
        else:
            systemic_windows = 0
        if remaining == 0:
            return {
                "status": "completed",
                "remaining": 0,
                "copy_concurrency": concurrency,
                "max_pool_connections": actual_pool,
            }
        if resource_reason is not None:
            return {
                "status": "paused",
                "reason": resource_reason,
                "remaining": remaining,
                "copy_concurrency": concurrency,
                "max_pool_connections": actual_pool,
            }
        if pause_requested():
            return {
                "status": "paused",
                "reason": "graceful_pause_requested",
                "remaining": remaining,
                "copy_concurrency": concurrency,
                "max_pool_connections": actual_pool,
            }
        if health_decision.action == "raise":
            previous = controller.concurrency
            controller.clean_batches = controller.clean_batches_to_raise - 1
            raised = controller.record_success()
            if raised > previous:
                _emit(
                    {
                        "adaptive_event": "raise",
                        "reason": "healthy_request_window",
                        "copy_concurrency": raised,
                        "request_error_rate": health_decision.error_rate,
                        "request_sample_count": health_decision.sample_count,
                    }
                )
            health.reset()
            latency.reset()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--artifact-digest")
    parser.add_argument("--next-plan-output")
    parser.add_argument("--verification-output")
    parser.add_argument("--limit", type=int, default=1_000)
    parser.add_argument("--shard-count", type=int, default=10)
    parser.add_argument("--shard-size", type=int, default=100)
    parser.add_argument("--retry-concurrency", type=int, default=16)
    parser.add_argument(
        "--copy-concurrency", type=_bucket_safe_copy_concurrency, default=32
    )
    parser.add_argument(
        "--maximum-copy-concurrency",
        type=_bucket_safe_copy_concurrency,
        default=32,
    )
    parser.add_argument("--max-pool-connections", type=_positive_pool_connections)
    parser.add_argument("--circuit-breaker-windows", type=int, default=3)
    parser.add_argument("--object-max-retries", type=_bounded_copy_retries, default=5)
    parser.add_argument("--retry-base-seconds", type=_positive_float, default=1.0)
    parser.add_argument("--retry-max-seconds", type=_positive_float, default=16.0)
    parser.add_argument("--retry-jitter-ratio", type=_unit_ratio, default=0.25)
    parser.add_argument("--max-cpu-percent", type=float, default=70.0)
    parser.add_argument("--cpu-batches-to-pause", type=int, default=3)
    parser.add_argument("--db-commit-p95-baseline-ms", type=float)
    parser.add_argument("--db-latency-multiplier", type=float, default=3.0)
    return parser


async def _main_async(args: argparse.Namespace) -> int:
    pause = False
    loop = asyncio.get_running_loop()

    def request_pause() -> None:
        nonlocal pause
        pause = True
        _emit({"adaptive_event": "pause_requested"})

    for name in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(name, request_pause)
    result = await run_sharded_adaptive_copy(args, pause_requested=lambda: pause)
    _emit(result)
    if result["status"] == "completed":
        return 0
    if result.get("reason") == "graceful_pause_requested":
        return 0
    return 2


def main() -> None:
    args = _parser().parse_args()
    if args.circuit_breaker_windows <= 0:
        raise SystemExit("circuit breaker windows must be positive")
    raise SystemExit(asyncio.run(_main_async(args)))


if __name__ == "__main__":
    main()
