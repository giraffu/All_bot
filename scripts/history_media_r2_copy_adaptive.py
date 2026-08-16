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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.history_media_r2_migration import (
    AdaptiveCopyController,
    _bounded_copy_concurrency,
    _execute_copy,
    _positive_pool_connections,
    _resolve_copy_max_pool_connections,
)

BatchExecutor = Callable[[Any], Awaitable[dict[str, Any]]]
Sleep = Callable[[float], Awaitable[None]]


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
        cpu_percent: float,
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
        if cpu_percent > self.max_cpu_percent:
            self.high_cpu_batches += 1
        else:
            self.high_cpu_batches = 0
        if self.high_cpu_batches >= self.cpu_batches_to_pause:
            return "sustained_cpu_above_limit"
        return None


def _resource_sample(
    *, cpu_started: float, wall_started: float
) -> tuple[float, int, int]:
    wall_seconds = max(time.perf_counter() - wall_started, 1e-9)
    cpu_percent = max(0.0, (time.process_time() - cpu_started) / wall_seconds * 100)
    fd_count = len(os.listdir("/proc/self/fd"))
    fd_soft_limit = int(resource.getrlimit(resource.RLIMIT_NOFILE)[0])
    return round(cpu_percent, 3), fd_count, fd_soft_limit


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True), flush=True)


async def run_adaptive_copy(
    args: argparse.Namespace | SimpleNamespace,
    *,
    execute_batch: BatchExecutor = _execute_copy,
    sleep: Sleep = asyncio.sleep,
    pause_requested: Callable[[], bool] = lambda: False,
) -> dict[str, Any]:
    configured_pool = args.max_pool_connections
    maximum_concurrency = 128 if configured_pool is None or configured_pool >= 128 else 64
    controller = AdaptiveCopyController(
        initial_concurrency=int(args.copy_concurrency),
        maximum_concurrency=maximum_concurrency,
    )
    _resolve_copy_max_pool_connections(controller.maximum_concurrency, configured_pool)
    failures_at_eight = 0
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
            if previous == 8:
                failures_at_eight += 1
                if failures_at_eight >= int(args.max_failures_at_eight):
                    return {
                        "status": "paused",
                        "reason": "three_transient_failures_at_eight",
                        "copy_concurrency": 8,
                        "max_pool_connections": _resolve_copy_max_pool_connections(
                            8, configured_pool
                        ),
                    }
            else:
                failures_at_eight = 0
            wait_seconds = {64: 30, 32: 60, 16: 120, 8: 240}[lowered]
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
        cpu_percent, fd_count, fd_soft_limit = _resource_sample(
            cpu_started=cpu_started, wall_started=wall_started
        )
        db_commit_p95_ms = float(
            (summary.get("db_commit_latency_ms") or {}).get("p95", 0.0)
        )
        resource_reason = resource_gate.evaluate(
            cpu_percent=cpu_percent,
            fd_count=fd_count,
            fd_soft_limit=fd_soft_limit,
            db_commit_p95_ms=db_commit_p95_ms,
        )
        _emit(
            {
                "adaptive_event": "batch_resource",
                "cpu_percent": cpu_percent,
                "fd_count": fd_count,
                "fd_soft_limit": fd_soft_limit,
                "db_commit_p95_ms": db_commit_p95_ms,
            }
        )
        failures_at_eight = 0
        actual_pool = int(
            summary.get(
                "max_pool_connections",
                _resolve_copy_max_pool_connections(concurrency, configured_pool),
            )
        )
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
        previous = controller.concurrency
        raised = controller.record_success()
        if raised > previous:
            _emit({"adaptive_event": "raise", "copy_concurrency": raised})


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--artifact-digest")
    parser.add_argument("--next-plan-output")
    parser.add_argument("--verification-output")
    parser.add_argument("--limit", type=int, default=10_000)
    parser.add_argument(
        "--copy-concurrency", type=_bounded_copy_concurrency, default=64
    )
    parser.add_argument("--max-pool-connections", type=_positive_pool_connections)
    parser.add_argument("--max-failures-at-eight", type=int, default=3)
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
    result = await run_adaptive_copy(args, pause_requested=lambda: pause)
    _emit(result)
    if result["status"] == "completed":
        return 0
    if result.get("reason") == "graceful_pause_requested":
        return 0
    return 2


def main() -> None:
    args = _parser().parse_args()
    if args.max_failures_at_eight <= 0:
        raise SystemExit("max failures at eight must be positive")
    raise SystemExit(asyncio.run(_main_async(args)))


if __name__ == "__main__":
    main()
