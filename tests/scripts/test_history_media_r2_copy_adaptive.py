from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.history_media_r2_copy_adaptive import (
    CopyHealthWindow,
    CopyLatencyWindow,
    RATE_LIMIT_COOLDOWN_SECONDS,
    ResourceGate,
    ResourceSample,
    ShardedBatchCoordinator,
    _parser,
    _available_cpu_count,
    _resource_sample,
    _summarize_request_evidence,
    run_adaptive_copy,
    run_sharded_adaptive_copy,
)


def test_adaptive_copy_cli_defaults_to_bucket_safe_shared_capacity():
    args = _parser().parse_args(
        [
            "--plan-sha256",
            "a" * 64,
            "--confirm",
            "COPY_HISTORY_MEDIA_" + "a" * 64,
            "--config",
            "/secure/config.json",
        ]
    )

    assert args.copy_concurrency == 32
    assert args.maximum_copy_concurrency == 32
    assert RATE_LIMIT_COOLDOWN_SECONDS == 60
    assert not hasattr(args, "rate_limit_cooldown_seconds")
    assert args.object_max_retries == 5
    assert args.shard_count == 10
    assert args.shard_size == 100
    assert args.retry_concurrency == 16
    assert not hasattr(args, "r2_p95_lower_ms")

    with pytest.raises(SystemExit):
        _parser().parse_args(
            [
                "--plan-sha256",
                "a" * 64,
                "--confirm",
                "COPY_HISTORY_MEDIA_" + "a" * 64,
                "--config",
                "/secure/config.json",
                "--copy-concurrency",
                "64",
            ]
        )


def test_request_evidence_summary_is_low_cardinality_and_contains_no_raw_id():
    raw_request_id = "provider-request-id-must-not-be-logged"
    summary = _summarize_request_evidence(
        [
            {
                "kind": "rate_limit",
                "stage": "copy_object",
                "http_status": 429,
                "provider_request_id_sha256": "a" * 64,
                "raw_request_id": raw_request_id,
            },
            {"kind": "ok"},
        ]
    )

    assert summary == {
        "request_error_kinds": {"rate_limit": 1},
        "request_error_stages": {"copy_object": 1},
        "http_status_counts": {"429": 1},
        "provider_request_fingerprint_sample": ["a" * 64],
        "rate_limit_cooldown_seconds": None,
        "rate_limit_new_concurrency": None,
    }
    assert raw_request_id not in json.dumps(summary)


@pytest.mark.asyncio
async def test_sharded_coordinator_caps_all_lanes_at_explicit_bucket_maximum():
    async def execute_batch(_args):
        return {"remaining": 0, "copied_objects": 0}

    args = SimpleNamespace(
        plan_sha256="f" * 64,
        confirm="COPY_HISTORY_MEDIA_" + "f" * 64,
        config="/tmp/config.json",
        limit=100,
        shard_count=10,
        shard_size=100,
        retry_concurrency=16,
        copy_concurrency=32,
        maximum_copy_concurrency=32,
        max_pool_connections=192,
    )
    coordinator = ShardedBatchCoordinator(args, execute_batch=execute_batch)
    try:
        assert coordinator.maximum_concurrency == 32
        assert coordinator.limiter.limit == 32
        assert coordinator.bulk_workers == 16
        assert coordinator.retry_workers == 16
    finally:
        await coordinator.close()


@pytest.mark.asyncio
async def test_sharded_runner_refills_a_fast_lane_before_the_slowest_lane_finishes():
    calls: list[tuple[int, int, int, int, int, int]] = []
    lane_calls = {0: 0, 1: 0}
    slow_lane_release = asyncio.Event()
    fast_lane_refilled = asyncio.Event()

    async def execute_batch(args):
        if getattr(args, "preflight_only", False):
            return {"preflight": "validated", "remaining": 100}
        if getattr(args, "finalize_plan", False):
            return {
                "remaining": 0,
                "copied_objects": 0,
                "_copy_request_events": [],
                "r2_object_operation_latency_ms": {"p95": 0, "max": 0},
                "db_commit_latency_ms": {"p95": 0},
            }
        lane = args.copy_shard_index
        lane_calls[lane] += 1
        calls.append(
            (
                lane,
                lane_calls[lane],
                args.bulk_executor._max_workers,
                args.retry_executor._max_workers,
                args.copy_concurrency,
                args.max_pool_connections,
                args.global_max_pool_connections,
            )
        )
        if lane == 0 and lane_calls[lane] == 1:
            await slow_lane_release.wait()
        if lane == 1 and lane_calls[lane] == 2:
            fast_lane_refilled.set()
            slow_lane_release.set()
        return {
            "remaining": 0 if lane == 0 else 100,
            "copied_objects": 1,
            "_copy_request_events": [{"at": float(len(calls)), "kind": "ok"}],
            "r2_object_operation_latency_ms": {"p95": 1, "max": 1},
            "db_commit_latency_ms": {"p95": 0},
        }

    result = await asyncio.wait_for(
        run_sharded_adaptive_copy(
            SimpleNamespace(
                plan_sha256="7" * 64,
                confirm="COPY_HISTORY_MEDIA_" + "7" * 64,
                config="/tmp/config.json",
                limit=1_000,
                shard_count=2,
                shard_size=1_000,
                retry_concurrency=4,
                copy_concurrency=16,
                max_pool_connections=24,
                circuit_breaker_windows=3,
                max_cpu_percent=1000,
            ),
            execute_batch=execute_batch,
            sleep=asyncio.sleep,
        ),
        timeout=2,
    )

    assert fast_lane_refilled.is_set()
    assert calls[:3] == [
        (0, 1, 12, 4, 8, 12, 24),
        (1, 1, 12, 4, 8, 12, 24),
        (1, 2, 12, 4, 8, 12, 24),
    ]
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_sharded_coordinator_reports_one_live_health_window_across_lanes():
    both_lanes_started = asyncio.Event()
    release_lane = asyncio.Event()
    lane_count = 0

    async def execute_batch(args):
        nonlocal lane_count
        if getattr(args, "preflight_only", False):
            return {"preflight": "validated", "remaining": 100}
        lane_count += 1
        args.request_event_sink(
            {
                "at": float(args.copy_shard_index),
                "kind": "ok",
                "copy_concurrency": 16,
            }
        )
        if lane_count == 2:
            both_lanes_started.set()
        await both_lanes_started.wait()
        if args.copy_shard_index == 1:
            await release_lane.wait()
        return {
            "remaining": 100,
            "copied_objects": 1,
            "_copy_request_events": [{"at": 999.0, "kind": "timeout"}],
            "r2_object_operation_latency_ms": {"p95": 1, "max": 1},
            "db_commit_latency_ms": {"p95": 0},
        }

    args = SimpleNamespace(
        plan_sha256="8" * 64,
        confirm="COPY_HISTORY_MEDIA_" + "8" * 64,
        config="/tmp/config.json",
        limit=1_000,
        shard_count=2,
        shard_size=1_000,
        retry_concurrency=4,
        copy_concurrency=16,
        max_pool_connections=24,
    )
    coordinator = ShardedBatchCoordinator(args, execute_batch=execute_batch)
    try:
        summary = await coordinator.execute_next(args)
        assert summary["_copy_request_events"] == [
            {"at": 0.0, "kind": "ok", "copy_concurrency": 16},
            {"at": 1.0, "kind": "ok", "copy_concurrency": 16},
        ]
    finally:
        release_lane.set()
        await coordinator.close()


@pytest.mark.asyncio
async def test_adaptive_runner_ignores_request_events_from_an_old_concurrency_epoch():
    calls = []

    async def execute_batch(args):
        calls.append(args.copy_concurrency)
        if len(calls) == 1:
            events = [
                *(
                    {"at": 1.0, "kind": "ok", "copy_concurrency": 128}
                    for _ in range(994)
                ),
                *(
                    {"at": 1.0, "kind": "timeout", "copy_concurrency": 128}
                    for _ in range(6)
                ),
            ]
        elif len(calls) == 2:
            events = [
                *(
                    {"at": 1.5, "kind": "ok", "copy_concurrency": 128}
                    for _ in range(999)
                ),
                {"at": 1.5, "kind": "rate_limit", "copy_concurrency": 128},
            ]
        else:
            events = [
                {"at": 2.0, "kind": "ok", "copy_concurrency": 64} for _ in range(200)
            ]
        return {
            "remaining": 0 if len(calls) == 3 else 100,
            "copied_objects": 1000,
            "_copy_request_events": events,
            "db_commit_latency_ms": {"p95": 0},
        }

    result = await run_adaptive_copy(
        SimpleNamespace(
            plan_sha256="6" * 64,
            confirm="COPY_HISTORY_MEDIA_" + "6" * 64,
            config="/tmp/config.json",
            limit=1_000,
            copy_concurrency=128,
            max_pool_connections=192,
            circuit_breaker_windows=3,
            max_cpu_percent=1000,
        ),
        execute_batch=execute_batch,
        sleep=asyncio.sleep,
    )

    assert calls == [128, 64, 64]
    assert result["status"] == "completed"


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
        cpu_gate.evaluate(capacity_cpu_percent=71, fd_count=10, fd_soft_limit=100)
        is None
    )
    assert (
        cpu_gate.evaluate(capacity_cpu_percent=75, fd_count=10, fd_soft_limit=100)
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
        gate.evaluate(capacity_cpu_percent=75, fd_count=2, fd_soft_limit=1024) is None
    )
    assert (
        gate.evaluate(capacity_cpu_percent=75, fd_count=2, fd_soft_limit=1024) is None
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
async def test_adaptive_runner_does_not_downshift_for_one_timeout_in_1000_requests():
    calls = []

    async def execute_batch(args):
        calls.append(args.copy_concurrency)
        return {
            "remaining": 0 if len(calls) == 2 else 100,
            "copied_objects": 999,
            "_copy_request_events": [
                *({"at": 1.0, "kind": "ok"} for _ in range(999)),
                {"at": 1.0, "kind": "timeout"},
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

    assert calls == [64, 128]
    assert result["status"] == "completed"
    assert result["copy_concurrency"] == 128


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

    assert calls == [32, 64, 128]
    assert result["copy_concurrency"] == 128


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
        + [*({"at": 1.0, "kind": "timeout"} for _ in range(6))]
    )

    decision = health.decision(current_concurrency=64)

    assert decision.action == "lower"
    assert decision.reason == "sustained_transient_error_rate"
    assert decision.error_rate == pytest.approx(0.006)


def test_copy_health_window_uses_rate_for_5xx_and_timeout_but_rate_limit_is_immediate():
    server_error = CopyHealthWindow(max_requests=1000, max_age_seconds=60)
    server_error.extend(
        [*({"at": 1.0, "kind": "ok"} for _ in range(999))]
        + [{"at": 1.0, "kind": "server_5xx"}]
    )

    decision = server_error.decision(current_concurrency=128)

    assert decision.action == "raise"

    sustained_server_errors = CopyHealthWindow(max_requests=1000, max_age_seconds=60)
    sustained_server_errors.extend(
        [*({"at": 1.0, "kind": "ok"} for _ in range(994))]
        + [*({"at": 1.0, "kind": "server_5xx"} for _ in range(6))]
    )
    sustained = sustained_server_errors.decision(current_concurrency=128)

    assert sustained.action == "lower"
    assert sustained.reason == "sustained_transient_error_rate"

    timeout = CopyHealthWindow(max_requests=1000, max_age_seconds=60)
    timeout.extend(
        [*({"at": 1.0, "kind": "ok"} for _ in range(999))]
        + [{"at": 1.0, "kind": "timeout"}]
    )

    assert timeout.decision(current_concurrency=128).action == "raise"

    rate_limit = CopyHealthWindow(max_requests=1000, max_age_seconds=60)
    rate_limit.extend([{"at": 1.0, "kind": "rate_limit"}])
    immediate = rate_limit.decision(current_concurrency=128)

    assert immediate.action == "lower"
    assert immediate.reason == "rate_limit"


def test_copy_health_window_can_raise_after_time_window_without_1000_requests():
    health = CopyHealthWindow(
        max_requests=1000,
        max_age_seconds=60,
        minimum_samples=200,
        minimum_observation_seconds=30,
    )
    health.extend([{"at": float(second), "kind": "ok"} for second in range(31)])

    decision = health.decision(current_concurrency=16)

    assert decision.action == "raise"
    assert decision.sample_count == 31


def test_copy_health_window_reset_discards_pre_downshift_errors():
    health = CopyHealthWindow(max_requests=1000, max_age_seconds=60)
    health.extend(
        [*({"at": 1.0, "kind": "ok"} for _ in range(994))]
        + [*({"at": 1.0, "kind": "timeout"} for _ in range(6))]
    )
    assert health.decision(current_concurrency=128).action == "lower"

    health.reset()
    health.extend([{"at": float(second), "kind": "ok"} for second in range(31)])

    decision = health.decision(current_concurrency=64)
    assert decision.action == "raise"
    assert decision.error_rate == 0


def test_copy_latency_window_observes_tail_without_controlling_concurrency():
    latency = CopyLatencyWindow(
        p95_lower_ms=8_000,
        p95_raise_ms=5_000,
        max_lower_ms=120_000,
        sustained_windows=2,
    )

    first = latency.decision(p95_ms=9_000, max_ms=30_000)
    second = latency.decision(p95_ms=9_500, max_ms=35_000)
    recovered = latency.decision(p95_ms=4_000, max_ms=20_000)
    extreme = latency.decision(p95_ms=4_000, max_ms=120_001)

    assert first.action == "hold"
    assert second.action == "hold"
    assert second.reason == "sustained_r2_p95_observed"
    assert recovered.action == "raise"
    assert extreme.action == "hold"
    assert extreme.reason == "r2_extreme_long_tail_observed"


@pytest.mark.asyncio
async def test_adaptive_runner_does_not_downshift_for_latency_without_errors():
    calls = []

    async def execute_batch(args):
        calls.append(args.copy_concurrency)
        return {
            "remaining": 0 if len(calls) == 4 else 100,
            "copied_objects": 100,
            "_copy_request_events": [
                *({"at": float(len(calls)), "kind": "ok"} for _ in range(1000))
            ],
            "r2_object_operation_latency_ms": {
                "p95": 25_000,
                "max": 180_000,
            },
            "db_commit_latency_ms": {"p95": 0},
        }

    result = await run_adaptive_copy(
        SimpleNamespace(
            plan_sha256="f" * 64,
            confirm="COPY_HISTORY_MEDIA_" + "f" * 64,
            config="/tmp/config.json",
            limit=100,
            copy_concurrency=128,
            max_pool_connections=192,
            circuit_breaker_windows=3,
            max_cpu_percent=1000,
        ),
        execute_batch=execute_batch,
        sleep=asyncio.sleep,
    )

    assert calls == [128, 128, 128, 128]
    assert result["status"] == "completed"
    assert result["copy_concurrency"] == 128


@pytest.mark.asyncio
async def test_adaptive_runner_resets_observation_after_downshift_and_recovers():
    calls = []

    async def execute_batch(args):
        calls.append(args.copy_concurrency)
        if len(calls) == 1:
            events = [{"at": 1.0, "kind": "rate_limit"}]
        else:
            events = [{"at": float(second), "kind": "ok"} for second in range(31)]
        return {
            "remaining": 0 if len(calls) == 3 else 100,
            "copied_objects": len(events),
            "_copy_request_events": events,
            "r2_object_operation_latency_ms": {
                "p95": 25_000,
                "max": 180_000,
            },
            "db_commit_latency_ms": {"p95": 0},
        }

    result = await run_adaptive_copy(
        SimpleNamespace(
            plan_sha256="9" * 64,
            confirm="COPY_HISTORY_MEDIA_" + "9" * 64,
            config="/tmp/config.json",
            limit=100,
            copy_concurrency=128,
            max_pool_connections=192,
            circuit_breaker_windows=3,
            max_cpu_percent=1000,
        ),
        execute_batch=execute_batch,
        sleep=asyncio.sleep,
    )

    assert calls == [128, 64, 128]
    assert result["status"] == "completed"


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
                *({"at": float(len(calls)), "kind": "timeout"} for _ in range(200)),
            ],
            "db_commit_latency_ms": {"p95": 0},
        }

    result = await run_adaptive_copy(
        SimpleNamespace(
            plan_sha256="c" * 64,
            confirm="COPY_HISTORY_MEDIA_" + "c" * 64,
            config="/tmp/config.json",
            limit=1000,
            copy_concurrency=16,
            max_pool_connections=None,
            circuit_breaker_windows=3,
            max_cpu_percent=1000,
        ),
        execute_batch=execute_batch,
        sleep=asyncio.sleep,
    )

    assert calls == [16, 16, 16]
    assert result["status"] == "paused"
    assert result["reason"] == "systemic_transient_error_circuit_open"
