from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.history_media_r2_copy_adaptive import ResourceGate, run_adaptive_copy


def test_web_api_image_contains_adaptive_copy_runner():
    root = Path(__file__).resolve().parents[2]
    dockerfile = (root / "deploy/docker/Dockerfile.control-plane").read_text()

    assert "scripts/history_media_r2_copy_adaptive.py" in dockerfile


def test_resource_gate_pauses_on_sustained_cpu_fd_or_db_regression():
    cpu_gate = ResourceGate(max_cpu_percent=70, cpu_batches_to_pause=3)
    assert cpu_gate.evaluate(cpu_percent=71, fd_count=10, fd_soft_limit=100) is None
    assert cpu_gate.evaluate(cpu_percent=75, fd_count=10, fd_soft_limit=100) is None
    assert (
        cpu_gate.evaluate(cpu_percent=80, fd_count=10, fd_soft_limit=100)
        == "sustained_cpu_above_limit"
    )

    fd_gate = ResourceGate()
    assert (
        fd_gate.evaluate(cpu_percent=1, fd_count=51, fd_soft_limit=100)
        == "fd_above_half_soft_limit"
    )

    db_gate = ResourceGate(db_commit_p95_baseline_ms=5, db_latency_multiplier=3)
    assert (
        db_gate.evaluate(
            cpu_percent=1,
            fd_count=10,
            fd_soft_limit=100,
            db_commit_p95_ms=16,
        )
        == "db_commit_latency_regressed"
    )


@pytest.mark.asyncio
async def test_adaptive_runner_lowers_after_transient_failure_and_retries_same_plan():
    calls = []
    sleeps = []

    async def execute_batch(args):
        calls.append(
            (args.plan_sha256, args.copy_concurrency, args.max_pool_connections)
        )
        if len(calls) == 1:
            raise RuntimeError("HTTPStatusCode: 503 ServiceUnavailable")
        return {"remaining": 0, "copied_objects": 25}

    async def sleep(seconds):
        sleeps.append(seconds)

    result = await run_adaptive_copy(
        SimpleNamespace(
            plan_sha256="a" * 64,
            confirm="COPY_HISTORY_MEDIA_" + "a" * 64,
            config="/tmp/config.json",
            limit=100,
            copy_concurrency=64,
            max_pool_connections=None,
            max_failures_at_eight=3,
        ),
        execute_batch=execute_batch,
        sleep=sleep,
    )

    assert calls == [("a" * 64, 64, None), ("a" * 64, 32, None)]
    assert sleeps == [60]
    assert result["status"] == "completed"
    assert result["copy_concurrency"] == 32


@pytest.mark.asyncio
async def test_adaptive_runner_finishes_current_batch_then_honors_pause():
    calls = []
    pause_requested = False

    async def execute_batch(args):
        nonlocal pause_requested
        calls.append(args.copy_concurrency)
        pause_requested = True
        return {"remaining": 900, "copied_objects": 100}

    result = await run_adaptive_copy(
        SimpleNamespace(
            plan_sha256="b" * 64,
            confirm="COPY_HISTORY_MEDIA_" + "b" * 64,
            config="/tmp/config.json",
            limit=100,
            copy_concurrency=64,
            max_pool_connections=96,
            max_failures_at_eight=3,
        ),
        execute_batch=execute_batch,
        sleep=asyncio.sleep,
        pause_requested=lambda: pause_requested,
    )

    assert calls == [64]
    assert result == {
        "status": "paused",
        "reason": "graceful_pause_requested",
        "remaining": 900,
        "copy_concurrency": 64,
        "max_pool_connections": 96,
    }


@pytest.mark.asyncio
async def test_adaptive_runner_pauses_after_repeated_transient_failures_at_eight():
    calls = []
    sleeps = []

    async def execute_batch(args):
        calls.append(args.copy_concurrency)
        raise RuntimeError("ReadTimeoutError")

    async def sleep(seconds):
        sleeps.append(seconds)

    result = await run_adaptive_copy(
        SimpleNamespace(
            plan_sha256="c" * 64,
            confirm="COPY_HISTORY_MEDIA_" + "c" * 64,
            config="/tmp/config.json",
            limit=100,
            copy_concurrency=64,
            max_pool_connections=None,
            max_failures_at_eight=3,
        ),
        execute_batch=execute_batch,
        sleep=sleep,
    )

    assert calls == [64, 32, 16, 8, 8, 8]
    assert sleeps == [60, 120, 240, 240, 240]
    assert result["status"] == "paused"
    assert result["reason"] == "three_transient_failures_at_eight"
