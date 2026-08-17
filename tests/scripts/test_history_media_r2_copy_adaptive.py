from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.history_media_r2_copy_adaptive import (
    CopyHealthWindow,
    ResourceGate,
    run_adaptive_copy,
)


def test_web_api_image_contains_adaptive_copy_runner():
    root = Path(__file__).resolve().parents[2]
    dockerfile = (root / "deploy/docker/Dockerfile.control-plane").read_text()

    assert "scripts/history_media_r2_copy_adaptive.py" in dockerfile


def test_database_migration_artifact_contains_frozen_history_r2_runner():
    root = Path(__file__).resolve().parents[2]
    dockerfile = (root / "deploy/docker/Dockerfile.migration").read_text()

    assert "scripts/history_media_r2_migration.py" in dockerfile
    assert "scripts/history_media_r2_copy_adaptive.py" in dockerfile
    assert "COPY shared /app/shared" in dockerfile


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
async def test_adaptive_runner_keeps_concurrency_for_one_timeout_in_1000_requests():
    calls = []

    async def execute_batch(args):
        calls.append(args.copy_concurrency)
        return {
            "remaining": 0 if len(calls) == 2 else 100,
            "copied_objects": 999,
            "_copy_request_events": [
                *({"at": 1.0, "kind": "ok"} for _ in range(999)),
                {"at": 1.0, "kind": "timeout_or_5xx"},
            ],
            "db_commit_latency_ms": {"p95": 0},
        }

    result = await run_adaptive_copy(
        SimpleNamespace(
            plan_sha256="a" * 64,
            confirm="COPY_HISTORY_MEDIA_" + "a" * 64,
            config="/tmp/config.json",
            limit=100,
            copy_concurrency=64,
            max_pool_connections=None,
            circuit_breaker_windows=3,
            max_cpu_percent=1000,
        ),
        execute_batch=execute_batch,
        sleep=asyncio.sleep,
    )

    assert calls == [64, 64]
    assert result["status"] == "completed"
    assert result["copy_concurrency"] == 64


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
            circuit_breaker_windows=3,
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
async def test_adaptive_runner_raises_on_low_nonzero_window_error_rate():
    calls = []

    async def execute_batch(args):
        calls.append(args.copy_concurrency)
        return {
            "remaining": 0 if len(calls) == 3 else 100,
            "copied_objects": 999,
            "_copy_request_events": [
                *({"at": 1.0, "kind": "ok"} for _ in range(999)),
                {"at": 1.0, "kind": "connection_transient"},
            ],
            "db_commit_latency_ms": {"p95": 0},
        }

    result = await run_adaptive_copy(
        SimpleNamespace(
            plan_sha256="d" * 64,
            confirm="COPY_HISTORY_MEDIA_" + "d" * 64,
            config="/tmp/config.json",
            limit=100,
            copy_concurrency=32,
            max_pool_connections=None,
            circuit_breaker_windows=3,
            max_cpu_percent=1000,
        ),
        execute_batch=execute_batch,
        sleep=asyncio.sleep,
    )

    assert calls == [32, 32, 64]
    assert result["copy_concurrency"] == 64


@pytest.mark.asyncio
async def test_adaptive_runner_lowers_immediately_for_rate_limit():
    calls = []

    async def execute_batch(args):
        calls.append(args.copy_concurrency)
        return {
            "remaining": 0 if len(calls) == 2 else 100,
            "copied_objects": 999,
            "_copy_request_events": [
                *({"at": 1.0, "kind": "ok"} for _ in range(999)),
                {"at": 1.0, "kind": "rate_limit"},
            ],
            "db_commit_latency_ms": {"p95": 0},
        }

    result = await run_adaptive_copy(
        SimpleNamespace(
            plan_sha256="c" * 64,
            confirm="COPY_HISTORY_MEDIA_" + "c" * 64,
            config="/tmp/config.json",
            limit=100,
            copy_concurrency=64,
            max_pool_connections=None,
            circuit_breaker_windows=3,
            max_cpu_percent=1000,
        ),
        execute_batch=execute_batch,
        sleep=asyncio.sleep,
    )

    assert calls == [64, 32]
    assert result["status"] == "completed"


def test_copy_health_window_lowers_only_after_sustained_half_percent_errors():
    health = CopyHealthWindow(max_requests=1000, max_age_seconds=60)
    health.extend(
        [*({"at": 1.0, "kind": "ok"} for _ in range(994))]
        + [*({"at": 1.0, "kind": "timeout_or_5xx"} for _ in range(6))]
    )

    decision = health.decision(current_concurrency=64)

    assert decision.action == "lower"
    assert decision.reason == "sustained_transient_error_rate"
    assert decision.error_rate == pytest.approx(0.006)


@pytest.mark.asyncio
async def test_adaptive_runner_opens_circuit_after_systemic_errors_at_minimum():
    calls = []

    async def execute_batch(args):
        calls.append(args.copy_concurrency)
        return {
            "remaining": 100,
            "copied_objects": 800,
            "_copy_request_events": [
                *({"at": float(len(calls)), "kind": "ok"} for _ in range(800)),
                *(
                    {"at": float(len(calls)), "kind": "timeout_or_5xx"}
                    for _ in range(200)
                ),
            ],
            "db_commit_latency_ms": {"p95": 0},
        }

    result = await run_adaptive_copy(
        SimpleNamespace(
            plan_sha256="c" * 64,
            confirm="COPY_HISTORY_MEDIA_" + "c" * 64,
            config="/tmp/config.json",
            limit=1000,
            copy_concurrency=8,
            max_pool_connections=None,
            circuit_breaker_windows=3,
            max_cpu_percent=1000,
        ),
        execute_batch=execute_batch,
        sleep=asyncio.sleep,
    )

    assert calls == [8, 8, 8]
    assert result["status"] == "paused"
    assert result["reason"] == "systemic_transient_error_circuit_open"
