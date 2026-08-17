from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.history_media_r2_copy_adaptive import (
    CopyHealthWindow,
    ResourceGate,
    ResourceSample,
    _available_cpu_count,
    _resource_sample,
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
    assert (
        cpu_gate.evaluate(
            capacity_cpu_percent=71, fd_count=10, fd_soft_limit=100
        )
        is None
    )
    assert (
        cpu_gate.evaluate(
            capacity_cpu_percent=75, fd_count=10, fd_soft_limit=100
        )
        is None
    )
    assert (
        cpu_gate.evaluate(capacity_cpu_percent=80, fd_count=10, fd_soft_limit=100)
        == "sustained_cpu_above_limit"
    )

    fd_gate = ResourceGate()
    assert (
        fd_gate.evaluate(capacity_cpu_percent=1, fd_count=51, fd_soft_limit=100)
        == "fd_above_half_soft_limit"
    )

    db_gate = ResourceGate(db_commit_p95_baseline_ms=5, db_latency_multiplier=3)
    assert (
        db_gate.evaluate(
            capacity_cpu_percent=1,
            fd_count=10,
            fd_soft_limit=100,
            db_commit_p95_ms=16,
        )
        == "db_commit_latency_regressed"
    )


def test_resource_sample_normalizes_process_cpu_to_available_capacity(monkeypatch):
    import scripts.history_media_r2_copy_adaptive as runner

    monkeypatch.setattr(runner.os, "sched_getaffinity", lambda _pid: set(range(32)))
    monkeypatch.setattr(runner.time, "perf_counter", lambda: 10.0)
    monkeypatch.setattr(runner.time, "process_time", lambda: 9.36)
    monkeypatch.setattr(runner.os, "listdir", lambda _path: ["1", "2"])
    monkeypatch.setattr(runner.resource, "getrlimit", lambda _kind: (1024, 1024))

    sample = _resource_sample(cpu_started=0.0, wall_started=0.0)

    assert sample.process_cpu_percent == pytest.approx(93.6)
    assert sample.capacity_cpu_percent == pytest.approx(2.925)
    assert sample.available_cpu_count == 32
    assert sample.fd_count == 2
    assert sample.fd_soft_limit == 1024

    gate = ResourceGate(max_cpu_percent=70, cpu_batches_to_pause=3)
    for _ in range(3):
        assert (
            gate.evaluate(
                capacity_cpu_percent=sample.capacity_cpu_percent,
                fd_count=sample.fd_count,
                fd_soft_limit=sample.fd_soft_limit,
            )
            is None
        )


def test_resource_gate_still_pauses_on_genuine_capacity_saturation():
    gate = ResourceGate(max_cpu_percent=70, cpu_batches_to_pause=3)

    assert (
        gate.evaluate(capacity_cpu_percent=75, fd_count=2, fd_soft_limit=1024)
        is None
    )
    assert (
        gate.evaluate(capacity_cpu_percent=75, fd_count=2, fd_soft_limit=1024)
        is None
    )
    assert (
        gate.evaluate(capacity_cpu_percent=75, fd_count=2, fd_soft_limit=1024)
        == "sustained_cpu_above_limit"
    )


def test_available_cpu_count_prefers_cpuset_and_falls_back(monkeypatch):
    import scripts.history_media_r2_copy_adaptive as runner

    monkeypatch.setattr(runner.os, "sched_getaffinity", lambda _pid: {2, 4, 6})
    assert _available_cpu_count() == 3

    def unavailable(_pid):
        raise OSError("affinity unavailable")

    monkeypatch.setattr(runner.os, "sched_getaffinity", unavailable)
    monkeypatch.setattr(runner.os, "cpu_count", lambda: 8)
    assert _available_cpu_count() == 8

    monkeypatch.setattr(runner.os, "cpu_count", lambda: None)
    assert _available_cpu_count() == 1


def test_resource_sample_preserves_single_cpu_gate_semantics(monkeypatch):
    import scripts.history_media_r2_copy_adaptive as runner

    monkeypatch.setattr(runner.os, "sched_getaffinity", lambda _pid: {0})
    monkeypatch.setattr(runner.time, "perf_counter", lambda: 4.0)
    monkeypatch.setattr(runner.time, "process_time", lambda: 3.0)
    monkeypatch.setattr(runner.os, "listdir", lambda _path: [])
    monkeypatch.setattr(runner.resource, "getrlimit", lambda _kind: (1024, 1024))

    sample = _resource_sample(cpu_started=0.0, wall_started=0.0)

    assert sample.process_cpu_percent == 75
    assert sample.capacity_cpu_percent == 75


@pytest.mark.asyncio
async def test_adaptive_runner_logs_raw_and_capacity_cpu(monkeypatch, capsys):
    import scripts.history_media_r2_copy_adaptive as runner

    monkeypatch.setattr(
        runner,
        "_resource_sample",
        lambda **_kwargs: ResourceSample(
            process_cpu_percent=93.6,
            capacity_cpu_percent=2.925,
            available_cpu_count=32,
            fd_count=12,
            fd_soft_limit=1024,
        ),
    )

    async def execute_batch(_args):
        return {"remaining": 0, "copied_objects": 1}

    result = await run_adaptive_copy(
        SimpleNamespace(
            plan_sha256="e" * 64,
            confirm="COPY_HISTORY_MEDIA_" + "e" * 64,
            config="/tmp/config.json",
            limit=1,
            copy_concurrency=128,
            max_pool_connections=192,
            circuit_breaker_windows=3,
        ),
        execute_batch=execute_batch,
        sleep=asyncio.sleep,
    )

    emitted = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    resource_event = next(
        event for event in emitted if event.get("adaptive_event") == "batch_resource"
    )
    assert resource_event["process_cpu_percent"] == 93.6
    assert resource_event["capacity_cpu_percent"] == 2.925
    assert resource_event["available_cpu_count"] == 32
    assert result["status"] == "completed"


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
