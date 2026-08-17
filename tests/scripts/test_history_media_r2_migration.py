from __future__ import annotations

import asyncio
import copy
import json
import subprocess
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

from scripts.history_media_r2_migration import (
    MIGRATION_DDL,
    AdaptiveCopyController,
    AdaptiveProbeController,
    AssetIdentity,
    CopyObjectCircuitBreaker,
    SourceFactCache,
    StreamingJsonArraySha256,
    _add_r2_custom_headers,
    _collect_copy_predecessor_recovery,
    _collect_probe_head_outcomes,
    _execute_copy_predecessor_recovery,
    _parser,
    _persist_copy_success,
    _persist_probe_batch,
    _probe_r2_rows,
    _probe_target_rows,
    _process_r2_custom_arguments,
    _resolve_copy_max_pool_connections,
    _resolve_probe_max_pool_connections,
    _r2_transport,
    _run_copy_group_batch,
    _runtime_identity,
    _s3_client,
    _timed_server_side_copy_with_retries,
    _validate_runtime_identity,
    _validate_r2_transport_runtime,
    build_candidate_keys,
    build_copy_plan,
    build_probe_plan,
    build_standard_target,
    build_copy_predecessor_recovery_plan,
    build_successor_copy_plan,
    build_successor_probe_plan,
    classify_copy_predecessor_recovery,
    classify_r2_head_outcomes,
    classify_reference,
    classify_target_status,
    evaluate_missing_round,
    group_copy_candidates,
    hash_body,
    history_assets_from_record,
    is_transient_copy_failure,
    normalize_asyncpg_dsn,
    normalized_history_cas_state,
    probe_plan_chain_sha256s,
    replace_asset_reference,
    server_side_copy_r2_object,
    validate_copy_gate,
    validate_copy_verification_heads,
    validate_probe_gate,
    validate_resume_identity,
    validate_switch_gate,
)


def _copy_head(*, marker: str | None, size: int = 100, etag: str = "etag"):
    metadata = {} if marker is None else {"allbot-copy-plan-sha256": marker}
    return {
        "ContentLength": size,
        "LastModified": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "ETag": etag,
        "Metadata": metadata,
    }


def test_copy_recovery_accepts_only_exact_current_or_direct_predecessor_marker():
    current = "c" * 64
    predecessor = "p" * 64
    source = _copy_head(marker=None)

    assert (
        classify_copy_predecessor_recovery(
            source_head=source,
            target_head=None,
            expected_size=100,
            expected_last_modified=source["LastModified"],
            expected_etag="etag",
            current_plan_sha256=current,
            predecessor_plan_sha256=predecessor,
        )
        == "missing"
    )
    assert (
        classify_copy_predecessor_recovery(
            source_head=source,
            target_head=_copy_head(marker=current),
            expected_size=100,
            expected_last_modified=source["LastModified"],
            expected_etag="etag",
            current_plan_sha256=current,
            predecessor_plan_sha256=predecessor,
        )
        == "current"
    )
    assert (
        classify_copy_predecessor_recovery(
            source_head=source,
            target_head=_copy_head(marker=predecessor),
            expected_size=100,
            expected_last_modified=source["LastModified"],
            expected_etag="etag",
            current_plan_sha256=current,
            predecessor_plan_sha256=predecessor,
        )
        == "predecessor"
    )

    with pytest.raises(RuntimeError, match="unrecognized copy plan marker"):
        classify_copy_predecessor_recovery(
            source_head=source,
            target_head=_copy_head(marker="x" * 64),
            expected_size=100,
            expected_last_modified=source["LastModified"],
            expected_etag="etag",
            current_plan_sha256=current,
            predecessor_plan_sha256=predecessor,
        )


def test_copy_recovery_rejects_changed_source_or_nonidentical_target():
    current = "c" * 64
    predecessor = "p" * 64
    expected_modified = datetime(2026, 1, 1, tzinfo=timezone.utc)

    with pytest.raises(RuntimeError, match="source identity changed"):
        classify_copy_predecessor_recovery(
            source_head=_copy_head(marker=None, size=101),
            target_head=_copy_head(marker=predecessor, size=101),
            expected_size=100,
            expected_last_modified=expected_modified,
            expected_etag="etag",
            current_plan_sha256=current,
            predecessor_plan_sha256=predecessor,
        )

    with pytest.raises(RuntimeError, match="target identity differs"):
        classify_copy_predecessor_recovery(
            source_head=_copy_head(marker=None),
            target_head=_copy_head(marker=predecessor, etag="different"),
            expected_size=100,
            expected_last_modified=expected_modified,
            expected_etag="etag",
            current_plan_sha256=current,
            predecessor_plan_sha256=predecessor,
        )


def test_copy_predecessor_recovery_plan_freezes_only_the_stopped_frontier():
    rows = [
        {
            "id": index,
            "history_id": 100 + index,
            "role": "output",
            "ordinal": 0,
            "original_ref": f"old-{index}.png",
            "target_key": f"task-results/t-{index}/primary.png",
            "source_name": "r2-user-data-prod",
            "source_key": f"old-{index}.png",
            "source_last_modified": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "source_etag": f"etag-{index}",
            "source_sha256": None,
            "target_sha256": None,
            "byte_size": 100 + index,
            "status": "failed" if index == 2 else "copy_required",
            "history_manifest_sha256": "f" * 64,
        }
        for index in range(1, 4)
    ]
    predecessor, _ = build_successor_copy_plan(
        predecessor_manifest=None,
        predecessor_plan_sha256=None,
        retained_rows=[],
        successor_rows=rows,
        run_id="11111111-1111-1111-1111-111111111111",
        history_watermark=103,
    )
    current, _ = build_successor_copy_plan(
        predecessor_manifest=predecessor,
        predecessor_plan_sha256=predecessor["plan_sha256"],
        retained_rows=[],
        successor_rows=rows,
    )
    frontier = {
        "batch_no": 1,
        "first_ledger_id": 1,
        "last_ledger_id": 3,
        "first_history_id": 101,
        "last_history_id": 103,
        "asset_count": 3,
        "history_count": 3,
        "rowset_sha256": "b" * 64,
        "cas_state_sha256": None,
    }

    recovery, batches = build_copy_predecessor_recovery_plan(
        current_manifest=current,
        current_plan_sha256=current["plan_sha256"],
        predecessor_plan_sha256=predecessor["plan_sha256"],
        frontier_batch=frontier,
        rows=rows,
        runtime_identity={"artifact_digest": "sha256:" + "d" * 64},
    )

    assert recovery["current_copy_plan_sha256"] == current["plan_sha256"]
    assert recovery["predecessor_copy_plan_sha256"] == predecessor["plan_sha256"]
    assert recovery["frontier_batch_no"] == 1
    assert recovery["count"] == 3
    assert recovery["batch_count"] == 1
    assert batches[0]["asset_count"] == 3
    assert recovery["plan_sha256"]

    with pytest.raises(RuntimeError, match="direct predecessor"):
        build_copy_predecessor_recovery_plan(
            current_manifest=current,
            current_plan_sha256=current["plan_sha256"],
            predecessor_plan_sha256="x" * 64,
            frontier_batch=frontier,
            rows=rows,
        )


def test_copy_recovery_commands_keep_a_separate_exact_copy_gate():
    recovery_plan = _parser().parse_args(
        [
            "plan-copy-recovery",
            "--run-id",
            "11111111-1111-1111-1111-111111111111",
            "--current-plan-sha256",
            "c" * 64,
            "--config",
            "/secure/config.json",
            "--artifact-digest",
            "sha256:" + "d" * 64,
            "--output",
            "/secure/recovery-plan.json",
        ]
    )
    assert recovery_plan.command == "plan-copy-recovery"

    execute = _parser().parse_args(
        [
            "execute-copy-recovery",
            "--plan-sha256",
            "r" * 64,
            "--confirm",
            "COPY_HISTORY_MEDIA_" + "r" * 64,
            "--config",
            "/secure/config.json",
            "--artifact-digest",
            "sha256:" + "d" * 64,
            "--concurrency",
            "128",
            "--receipt-output",
            "/secure/recovery-receipt.json",
            "--next-plan-output",
            "/secure/successor.json",
        ]
    )
    assert execute.command == "execute-copy-recovery"
    assert execute.concurrency == 128


@pytest.mark.asyncio
async def test_copy_recovery_head_pool_exceeds_32_and_releases_threads():
    lock = threading.Lock()
    active = 0
    peak = 0
    modified = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def head(_client, _bucket, key):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            threading.Event().wait(0.04)
            return None if key.startswith("target-") else _copy_head(marker=None)
        finally:
            with lock:
                active -= 1

    groups = [
        [
            {
                "id": index,
                "history_id": index,
                "role": "output",
                "ordinal": 0,
                "source_key": f"source-{index}",
                "target_key": f"target-{index}",
                "byte_size": 100,
                "source_last_modified": modified,
                "source_etag": "etag",
            }
        ]
        for index in range(40)
    ]

    outcomes = await _collect_copy_predecessor_recovery(
        groups,
        client=object(),
        current_plan_sha256="c" * 64,
        predecessor_plan_sha256="p" * 64,
        concurrency=40,
        head_func=head,
    )

    assert len(outcomes) == 40
    assert {outcome for _group, outcome, _head in outcomes} == {"missing"}
    assert peak > 32
    assert not any(
        thread.name.startswith("history-r2-copy-recovery-head")
        for thread in threading.enumerate()
        if thread.is_alive()
    )


def test_copy_recovery_executor_is_head_only_and_uses_ledger_cas():
    import inspect

    source = inspect.getsource(_execute_copy_predecessor_recovery)
    for forbidden in (
        ".get_object(",
        ".copy_object(",
        ".list_objects",
        ".delete_object(",
    ):
        assert forbidden not in source
    assert "for update" in source.lower()
    assert "copy recovery rowset changed" in source
    assert "copy_plan_sha256=$5" in source
    assert "r2_copy_object_recovered_predecessor" in source


def test_copy_retries_one_transient_object_with_exponential_backoff(monkeypatch):
    calls = 0
    sleeps: list[float] = []

    def copy_object(_client, **_kwargs):
        nonlocal calls
        calls += 1
        if calls <= 3:
            raise RuntimeError("ReadTimeoutError")
        return {"etag": "target", "multipart": False, "recovered": False}

    monkeypatch.setattr(
        "scripts.history_media_r2_migration.server_side_copy_r2_object",
        copy_object,
    )

    result = _timed_server_side_copy_with_retries(
        object(),
        max_retries=5,
        retry_base_seconds=1,
        retry_max_seconds=16,
        sleep_fn=sleeps.append,
        jitter_fn=lambda delay: delay,
    )

    assert result["error"] is None
    assert result["attempt_count"] == 4
    assert [event["kind"] for event in result["request_events"]] == [
        "timeout_or_5xx",
        "timeout_or_5xx",
        "timeout_or_5xx",
        "ok",
    ]
    assert sleeps == [1, 2, 4]


def test_copy_exhausts_only_the_failed_object_after_five_retries(monkeypatch):
    sleeps: list[float] = []

    def copy_object(_client, **_kwargs):
        raise RuntimeError("Connection reset by peer")

    monkeypatch.setattr(
        "scripts.history_media_r2_migration.server_side_copy_r2_object",
        copy_object,
    )

    result = _timed_server_side_copy_with_retries(
        object(),
        max_retries=5,
        retry_base_seconds=1,
        retry_max_seconds=16,
        sleep_fn=sleeps.append,
        jitter_fn=lambda delay: delay,
    )

    assert isinstance(result["error"], RuntimeError)
    assert result["attempt_count"] == 6
    assert sleeps == [1, 2, 4, 8, 16]
    assert {event["kind"] for event in result["request_events"]} == {
        "connection_transient"
    }


@pytest.mark.asyncio
async def test_copy_persists_fast_success_before_slow_peer_finishes():
    slow_started = threading.Event()
    release_slow = threading.Event()
    queued_fast_persisted = asyncio.Event()
    persisted: list[int] = []
    worker_ids: set[int] = set()

    def copy_one(group):
        worker_ids.add(threading.get_ident())
        row_id = group[0]["id"]
        if row_id == 2:
            slow_started.set()
            assert release_slow.wait(5)
        return {
            "outcome": {"etag": f"target-{row_id}", "multipart": False},
            "error": None,
            "elapsed_ms": 1.0,
            "attempt_count": 1,
            "request_events": [{"at": 1.0, "kind": "ok"}],
        }

    async def persist_success(group, _outcome):
        persisted.append(group[0]["id"])
        if group[0]["id"] == 3:
            queued_fast_persisted.set()

    async def persist_failure(_group, _error):
        raise AssertionError("no object should fail")

    with ThreadPoolExecutor(max_workers=2) as executor:
        task = asyncio.create_task(
            _run_copy_group_batch(
                [[{"id": 1}], [{"id": 2}], [{"id": 3}]],
                executor=executor,
                copy_one=copy_one,
                persist_success=persist_success,
                persist_failure=persist_failure,
            )
        )
        assert await asyncio.to_thread(slow_started.wait, 2)
        await asyncio.wait_for(queued_fast_persisted.wait(), timeout=2)
        assert not task.done()
        release_slow.set()
        result = await task

    assert persisted == [1, 3, 2]
    assert result["copied_objects"] == 3
    assert worker_ids.isdisjoint(
        {thread.ident for thread in threading.enumerate() if thread.is_alive()}
    )


@pytest.mark.asyncio
async def test_copy_success_commit_fails_closed_after_plan_ownership_changes():
    class Conn:
        async def execute(self, _query, *_params):
            return "UPDATE 0"

    with pytest.raises(RuntimeError, match="ownership changed"):
        await _persist_copy_success(
            Conn(),
            [{"id": 1}],
            {"etag": "target", "multipart": False, "recovered": False},
            copy_plan_sha256="a" * 64,
        )


def test_successor_copy_plan_freezes_only_unfinished_predecessor_assets():
    rows = [
        {
            "id": index,
            "history_id": 100 + index,
            "role": "output",
            "ordinal": 0,
            "original_ref": f"old-{index}.png",
            "target_key": f"task-results/t-{index}/primary.png",
            "source_name": "r2-user-data-prod",
            "source_key": f"old-{index}.png",
            "source_last_modified": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "source_etag": f"etag-{index}",
            "source_sha256": None,
            "target_sha256": "copied" if index == 1 else None,
            "byte_size": 100 + index,
            "status": "copied_verified" if index == 1 else "copy_required",
            "history_manifest_sha256": "f" * 64,
        }
        for index in range(1, 4)
    ]
    predecessor, _ = build_successor_copy_plan(
        predecessor_manifest=None,
        predecessor_plan_sha256=None,
        retained_rows=[],
        successor_rows=rows,
        run_id="11111111-1111-1111-1111-111111111111",
        history_watermark=103,
        runtime_identity={"artifact_digest": "sha256:" + "a" * 64},
        batch_size=2,
    )

    successor, batches = build_successor_copy_plan(
        predecessor_manifest=predecessor,
        predecessor_plan_sha256=predecessor["plan_sha256"],
        retained_rows=[rows[0]],
        successor_rows=[{**rows[1], "status": "failed"}, rows[2]],
        runtime_identity={"artifact_digest": "sha256:" + "b" * 64},
        batch_size=1,
    )

    assert successor["predecessor_copy_plan_sha256s"] == [predecessor["plan_sha256"]]
    assert successor["retained_asset_count"] == 1
    assert successor["count"] == 2
    assert successor["conserved_asset_count"] == 3
    assert successor["intersection_asset_count"] == 0
    assert successor["counts"] == {"copy_required": 2}
    assert len(batches) == 2
    assert successor["batches_sha256"]


def test_successor_copy_plan_rejects_overlap_with_completed_assets():
    row = {
        "id": 1,
        "history_id": 1,
        "role": "output",
        "ordinal": 0,
        "target_key": "task-results/t/primary.png",
        "status": "copy_required",
    }
    predecessor, _ = build_successor_copy_plan(
        predecessor_manifest=None,
        predecessor_plan_sha256=None,
        retained_rows=[],
        successor_rows=[row],
        run_id="11111111-1111-1111-1111-111111111111",
        history_watermark=1,
    )

    with pytest.raises(RuntimeError, match="overlaps"):
        build_successor_copy_plan(
            predecessor_manifest=predecessor,
            predecessor_plan_sha256=predecessor["plan_sha256"],
            retained_rows=[row],
            successor_rows=[row],
        )


def test_copy_object_circuit_ignores_isolated_error_and_opens_on_systemic_windows():
    breaker = CopyObjectCircuitBreaker(max_error_rate=0.5, consecutive_windows=3)

    assert breaker.observe(copied_objects=63, failed_objects=1) is False
    assert breaker.observe(copied_objects=32, failed_objects=32) is False
    assert breaker.observe(copied_objects=31, failed_objects=33) is False
    assert breaker.observe(copied_objects=30, failed_objects=34) is True


@pytest.mark.asyncio
async def test_probe_head_pool_reaches_128_real_blocking_workers_and_shuts_down():
    active = 0
    peak = 0
    worker_ids: set[int] = set()
    lock = threading.Lock()
    all_started = threading.Event()
    release = threading.Event()

    def blocking_head(_client, _bucket, _key):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            worker_ids.add(threading.get_ident())
            if active == 128:
                all_started.set()
        assert all_started.wait(10), "dedicated Probe pool never reached 128 workers"
        assert release.wait(10)
        with lock:
            active -= 1
        return None

    rows = [
        {
            "id": index,
            "original_ref": f"old-{index}.png",
            "target_key": f"task-inputs/r/{index}.png",
            "registry_task_id": "r",
        }
        for index in range(128)
    ]

    async def release_when_full():
        assert await asyncio.to_thread(all_started.wait, 10)
        release.set()

    release_task = asyncio.create_task(release_when_full())
    result = await _collect_probe_head_outcomes(
        rows,
        client=object(),
        concurrency=128,
        head_func=blocking_head,
    )
    await release_task

    assert peak == 128
    assert result.peak_workers == 128
    assert result.worker_threads == 128
    assert len(worker_ids) == 128
    assert not any(
        thread.name.startswith("history-r2-probe-head")
        for thread in threading.enumerate()
    )


@pytest.mark.asyncio
async def test_probe_head_pool_shuts_down_after_head_failure():
    def failing_head(_client, _bucket, _key):
        raise RuntimeError("HTTPStatusCode: 503")

    with pytest.raises(RuntimeError, match="503"):
        await _collect_probe_head_outcomes(
            [
                {
                    "id": 1,
                    "original_ref": "old.png",
                    "target_key": "task-inputs/r/0.png",
                    "registry_task_id": "r",
                }
            ],
            client=object(),
            concurrency=128,
            head_func=failing_head,
        )
    assert not any(
        thread.name.startswith("history-r2-probe-head")
        for thread in threading.enumerate()
    )


def test_probe_connection_pool_covers_every_adaptive_concurrency_level():
    for concurrency in (8, 16, 32, 64, 128):
        connections = _resolve_probe_max_pool_connections(concurrency)
        assert connections >= concurrency
        assert connections == 128
    with pytest.raises(ValueError, match="8, 16, 32, 64, or 128"):
        _resolve_probe_max_pool_connections(129)


def test_runtime_identity_binds_artifact_and_endpoints_without_credentials():
    identity = _runtime_identity(
        artifact_digest="sha256:" + "a" * 64,
        config={
            "target": {
                "bucket": "user-data-prod",
                "endpoint": "https://r2.example.invalid",
                "access_key": "do-not-leak",
            },
            "sources": [
                {
                    "name": "r2-user-data-prod",
                    "endpoint": "https://r2.example.invalid",
                    "secret_key": "do-not-leak",
                }
            ],
        },
    )

    assert identity["artifact_digest"] == "sha256:" + "a" * 64
    assert identity["bucket"] == "user-data-prod"
    assert "r2.example.invalid" not in json.dumps(identity)
    assert "do-not-leak" not in json.dumps(identity)

    _validate_runtime_identity(
        identity,
        artifact_digest="sha256:" + "a" * 64,
        config={
            "target": {
                "bucket": "user-data-prod",
                "endpoint": "https://r2.example.invalid",
                "access_key": "do-not-leak",
            },
            "sources": [
                {
                    "name": "r2-user-data-prod",
                    "endpoint": "https://r2.example.invalid",
                    "secret_key": "do-not-leak",
                }
            ],
        },
    )
    with pytest.raises(RuntimeError, match="runtime identity changed"):
        _validate_runtime_identity(
            identity,
            artifact_digest="sha256:" + "b" * 64,
            config={
                "target": {
                    "bucket": "user-data-prod",
                    "endpoint": "https://r2.example.invalid",
                },
                "sources": [
                    {
                        "name": "r2-user-data-prod",
                        "endpoint": "https://r2.example.invalid",
                    }
                ],
            },
        )


def test_runtime_identity_binds_explicit_r2_proxy_without_exposing_its_url():
    config = {
        "target": {
            "bucket": "user-data-prod",
            "endpoint": "https://r2.example.invalid",
        },
        "sources": [
            {
                "name": "r2-user-data-prod",
                "endpoint": "https://r2.example.invalid",
            }
        ],
        "r2_transport": {
            "mode": "https_proxy",
            "proxy_url": "http://127.0.0.1:7890",
        },
    }

    identity = _runtime_identity(
        artifact_digest="sha256:" + "a" * 64,
        config=config,
    )

    assert identity["r2_transport"] == {
        "mode": "https_proxy",
        "proxy_port": 7890,
        "proxy_sha256": identity["r2_transport"]["proxy_sha256"],
    }
    assert len(identity["r2_transport"]["proxy_sha256"]) == 64
    assert "127.0.0.1" not in json.dumps(identity)
    assert "http://" not in json.dumps(identity)

    direct_config = {key: value for key, value in config.items() if key != "r2_transport"}
    with pytest.raises(RuntimeError, match="runtime identity changed"):
        _validate_runtime_identity(
            identity,
            artifact_digest="sha256:" + "a" * 64,
            config=direct_config,
        )


@pytest.mark.parametrize(
    "transport",
    [
        {"mode": "https_proxy", "proxy_url": "http://127.0.0.1:7891"},
        {"mode": "https_proxy", "proxy_url": "http://localhost:7890"},
        {"mode": "https_proxy", "proxy_url": "https://127.0.0.1:7890"},
        {"mode": "https_proxy", "proxy_url": "http://user@127.0.0.1:7890"},
        {"mode": "direct", "proxy_url": "http://127.0.0.1:7890"},
        {"mode": "socks5", "proxy_url": "http://127.0.0.1:7890"},
    ],
)
def test_r2_proxy_rejects_every_noncanonical_transport(transport):
    with pytest.raises(ValueError):
        _r2_transport({"r2_transport": transport})


def test_r2_proxy_runtime_preflight_closes_probe_socket_and_fails_closed():
    class Connection:
        closed = False

        def close(self):
            self.closed = True

    connection = Connection()
    calls = []

    def connect(address, timeout):
        calls.append((address, timeout))
        return connection

    transport = _r2_transport(
        {
            "r2_transport": {
                "mode": "https_proxy",
                "proxy_url": "http://127.0.0.1:7890",
            }
        }
    )
    _validate_r2_transport_runtime(transport, create_connection=connect)

    assert calls == [(("127.0.0.1", 7890), 2.0)]
    assert connection.closed is True

    def unavailable(_address, _timeout):
        raise OSError("listener unavailable")

    with pytest.raises(RuntimeError, match="configured R2 proxy is unavailable"):
        _validate_r2_transport_runtime(transport, create_connection=unavailable)


def test_copy_stage_verification_requires_exact_marker_and_retained_source():
    modified = datetime(2026, 8, 9, tzinfo=timezone.utc)
    row = {
        "byte_size": 3,
        "source_last_modified": modified,
        "source_etag": "source",
    }
    validate_copy_verification_heads(
        row,
        source_head=_head(size=3, etag="source", modified=modified),
        target_head=_head(
            size=3,
            etag="target",
            metadata={"allbot-copy-plan-sha256": "a" * 64},
        ),
        copy_plan_sha256="a" * 64,
    )
    with pytest.raises(RuntimeError, match="source disappeared"):
        validate_copy_verification_heads(
            row,
            source_head=None,
            target_head=_head(size=3, etag="target"),
            copy_plan_sha256="a" * 64,
        )
    with pytest.raises(RuntimeError, match="marker changed"):
        validate_copy_verification_heads(
            row,
            source_head=_head(size=3, etag="source", modified=modified),
            target_head=_head(size=3, etag="target"),
            copy_plan_sha256="a" * 64,
        )


def test_probe_plan_is_compact_batched_and_exactly_gated():
    rows = [
        {
            "id": 7,
            "history_id": 9,
            "role": "input",
            "ordinal": 0,
            "original_ref": "old.png",
            "target_key": "task-inputs/r/0.png",
            "registry_task_id": "r",
        }
    ]
    manifest, batches = build_probe_plan(
        run_id="11111111-1111-1111-1111-111111111111",
        history_watermark=99,
        rows=rows,
        batch_size=10_000,
        runtime_identity={"script_sha256": "a" * 64},
    )

    assert manifest["schema"] == "allbot-history-media-r2-probe-plan/v1"
    assert manifest["asset_count"] == 1
    assert manifest["history_count"] == 1
    assert manifest["batch_count"] == 1
    assert batches[0]["first_ledger_id"] == 7
    assert "assets" not in manifest
    validate_probe_gate(
        expected_plan_sha256=manifest["plan_sha256"],
        supplied_plan_sha256=manifest["plan_sha256"],
        confirmation=f"PROBE_HISTORY_MEDIA_{manifest['plan_sha256']}",
    )
    with pytest.raises(ValueError, match="exact probe plan"):
        validate_probe_gate(
            expected_plan_sha256=manifest["plan_sha256"],
            supplied_plan_sha256=manifest["plan_sha256"],
            confirmation="yes",
        )


def test_successor_probe_excludes_completed_assets_and_conserves_root_plan():
    rows = [
        {
            "id": index,
            "history_id": index,
            "role": "input",
            "ordinal": 0,
            "original_ref": f"old-{index}.png",
            "target_key": f"task-inputs/r/{index}.png",
            "registry_task_id": "r",
            "history_manifest_sha256": str(index) * 64,
        }
        for index in range(1, 5)
    ]
    predecessor, predecessor_batches = build_probe_plan(
        run_id="11111111-1111-1111-1111-111111111111",
        history_watermark=99,
        rows=rows,
        batch_size=2,
        runtime_identity={"artifact_digest": "sha256:" + "a" * 64},
    )
    predecessor_before = copy.deepcopy(predecessor)
    retained_batch = {
        **predecessor_batches[0],
        "plan_sha256": predecessor["plan_sha256"],
        "outcome_counts": {"pending_probe": 2},
    }

    successor, successor_batches = build_successor_probe_plan(
        predecessor_manifest=predecessor,
        predecessor_plan_sha256=predecessor["plan_sha256"],
        retained_rows=rows[:2],
        successor_rows=rows[2:],
        retained_batches=[retained_batch],
        batch_size=2,
        runtime_identity={"artifact_digest": "sha256:" + "b" * 64},
    )

    assert predecessor == predecessor_before
    assert successor["schema"] == "allbot-history-media-r2-probe-successor-plan/v1"
    assert successor["predecessor_probe_plan_sha256"] == predecessor["plan_sha256"]
    assert successor["predecessor_probe_plan_sha256s"] == [predecessor["plan_sha256"]]
    assert successor["root_asset_count"] == 4
    assert successor["retained_asset_count"] == 2
    assert successor["asset_count"] == 2
    assert successor["retained_asset_count"] + successor["asset_count"] == 4
    assert successor["intersection_asset_count"] == 0
    assert successor["retained_batch_count"] == 1
    assert successor["batch_count"] == 1
    assert successor["retained_outcome_counts"] == {"pending_probe": 2}
    assert successor["rowset_sha256"] == successor_batches[0]["rowset_sha256"]
    assert successor["batches_sha256"]
    assert successor["retained_rowset_sha256"]
    assert successor["retained_batches_sha256"]
    assert probe_plan_chain_sha256s(successor) == (
        predecessor["plan_sha256"],
        successor["plan_sha256"],
    )


def test_successor_probe_rejects_overlap_count_drift_and_wrong_predecessor_sha():
    rows = [
        {
            "id": index,
            "history_id": index,
            "role": "input",
            "ordinal": 0,
            "original_ref": f"old-{index}.png",
            "target_key": f"task-inputs/r/{index}.png",
            "registry_task_id": "r",
            "history_manifest_sha256": str(index) * 64,
        }
        for index in range(1, 4)
    ]
    predecessor, predecessor_batches = build_probe_plan(
        run_id="11111111-1111-1111-1111-111111111111",
        history_watermark=99,
        rows=rows,
        batch_size=1,
    )
    retained_batch = {
        **predecessor_batches[0],
        "plan_sha256": predecessor["plan_sha256"],
        "outcome_counts": {"pending_probe": 1},
    }
    kwargs = {
        "predecessor_manifest": predecessor,
        "predecessor_plan_sha256": predecessor["plan_sha256"],
        "retained_rows": rows[:1],
        "successor_rows": rows[1:],
        "retained_batches": [retained_batch],
        "batch_size": 1,
    }

    with pytest.raises(RuntimeError, match="overlaps predecessor"):
        build_successor_probe_plan(
            **{**kwargs, "successor_rows": rows},
        )
    with pytest.raises(RuntimeError, match="does not conserve"):
        build_successor_probe_plan(
            **{**kwargs, "successor_rows": rows[2:]},
        )
    with pytest.raises(RuntimeError, match="predecessor plan identity"):
        build_successor_probe_plan(
            **{**kwargs, "predecessor_plan_sha256": "f" * 64},
        )


@pytest.mark.asyncio
async def test_interrupted_probe_batch_cannot_commit_after_predecessor_superseded():
    class Transaction:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    class Conn:
        def __init__(self):
            self.queries: list[str] = []

        def transaction(self):
            return Transaction()

        async def execute(self, query, *_args):
            self.queries.append(query)
            if "analytics_history_media_migration_plan_batches" in query:
                return "UPDATE 0"
            return "UPDATE 1"

        async def executemany(self, *_args):
            return None

    conn = Conn()
    with pytest.raises(RuntimeError, match="no longer pending"):
        await _persist_probe_batch(
            conn,  # type: ignore[arg-type]
            run_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
            plan_sha="a" * 64,
            batch_no=3,
            rows=[{"id": 7, "catalog_asset_id": 11}],
            outcomes=[
                {
                    "id": 7,
                    "status": "pending_probe",
                    "source_key": None,
                    "byte_size": None,
                    "last_modified": None,
                    "etag": None,
                    "attempts": [],
                }
            ],
        )
    batch_query = next(
        query
        for query in conn.queries
        if "analytics_history_media_migration_plan_batches" in query
    )
    assert "status='pending'" in batch_query


def test_probe_head_outcomes_do_not_treat_system_errors_as_missing():
    modified = datetime(2026, 8, 9, tzinfo=timezone.utc)
    rows = [
        {
            "id": 1,
            "original_ref": "old.png",
            "target_key": "task-inputs/r/0.png",
            "registry_task_id": "r",
        }
    ]
    outcomes = classify_r2_head_outcomes(
        rows,
        {
            "task-inputs/r/0.png": None,
            "old.png": _head(size=3, etag="source", modified=modified),
            "history/r/old.png": None,
        },
    )
    assert outcomes == [
        {
            "id": 1,
            "status": "copy_required",
            "source_key": "old.png",
            "byte_size": 3,
            "last_modified": modified,
            "etag": "source",
            "attempts": [("old.png", "found")],
        }
    ]


def test_probe_adaptive_concurrency_can_recover_up_to_128():
    controller = AdaptiveProbeController(initial_concurrency=64)
    assert controller.record_failure("HTTPStatusCode: 503") == 32
    assert controller.record_success() == 32
    assert controller.record_success() == 32
    assert controller.record_success() == 64
    assert controller.record_success() == 64
    assert controller.record_success() == 64
    assert controller.record_success() == 128


def test_normalized_history_cas_accepts_only_original_current_or_completed_paths():
    ledger = [
        {
            "role": "input",
            "ordinal": 0,
            "original_ref": "old-in.png",
            "target_key": "task-inputs/r/0.png",
            "selected": True,
            "switch_completed_at": None,
            "switch_plan_sha256": None,
        },
        {
            "role": "output",
            "ordinal": 0,
            "original_ref": "old-out.png",
            "target_key": "task-results/b/primary.png",
            "selected": False,
            "switch_completed_at": datetime(2026, 8, 16, tzinfo=timezone.utc),
            "switch_plan_sha256": "b" * 64,
        },
    ]
    current = {
        ("input", 0): "task-inputs/r/0.png",
        ("output", 0): "task-results/b/primary.png",
    }
    first = normalized_history_cas_state(7, current, ledger)
    current[("input", 0)] = "old-in.png"
    assert normalized_history_cas_state(7, current, ledger) == first
    current[("output", 0)] = "unknown.png"
    with pytest.raises(RuntimeError, match="unknown History media state"):
        normalized_history_cas_state(7, current, ledger)


def _head(
    *,
    size: int,
    etag: str,
    modified: datetime | None = None,
    metadata: dict[str, str] | None = None,
):
    return {
        "ContentLength": size,
        "ETag": f'"{etag}"',
        "LastModified": modified or datetime(2026, 8, 9, tzinfo=timezone.utc),
        "Metadata": metadata or {},
    }


def test_server_side_copy_uses_r2_copy_object_without_reading_media():
    plan_sha = "a" * 64

    class Client:
        def __init__(self):
            self.copy_calls = []
            self.head_calls = 0

        def head_object(self, *, Bucket, Key):
            self.head_calls += 1
            if Key == "old/file.mp4":
                return _head(size=123, etag="source-etag")
            if self.copy_calls:
                return _head(
                    size=123,
                    etag="source-etag",
                    metadata={"allbot-copy-plan-sha256": plan_sha},
                )
            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "missing"}},
                "HeadObject",
            )

        def copy_object(self, **kwargs):
            self.copy_calls.append(kwargs)
            return {"CopyObjectResult": {"ETag": '"source-etag"'}}

        def get_object(self, **_kwargs):  # pragma: no cover - forbidden behavior
            raise AssertionError("server-side migration must not download media")

        def upload_fileobj(self, *_args, **_kwargs):  # pragma: no cover
            raise AssertionError("server-side migration must not upload media")

    client = Client()
    result = server_side_copy_r2_object(
        client,
        bucket="user-data-prod",
        source_key="old/file.mp4",
        target_key="task-results/backend/primary.mp4",
        expected_size=123,
        expected_last_modified=datetime(2026, 8, 9, tzinfo=timezone.utc),
        copy_plan_sha256=plan_sha,
    )

    assert result == {
        "byte_size": 123,
        "source_etag": "source-etag",
        "etag": "source-etag",
        "multipart": False,
        "recovered": False,
    }
    assert client.copy_calls == [
        {
            "Bucket": "user-data-prod",
            "Key": "task-results/backend/primary.mp4",
            "CopySource": {"Bucket": "user-data-prod", "Key": "old/file.mp4"},
            "CopySourceIfMatch": "source-etag",
            "MetadataDirective": "COPY",
            "Metadata": {"allbot-copy-plan-sha256": plan_sha},
            "custom_headers": {
                "cf-copy-destination-if-none-match": "*",
                "x-amz-metadata-directive": "MERGE",
            },
        }
    ]


def test_server_side_copy_recovers_same_plan_target_without_copying_again():
    plan_sha = "b" * 64

    class Client:
        def __init__(self):
            self.copy_calls = []

        def head_object(self, *, Bucket, Key):
            if Key == "old.png":
                return _head(size=3, etag="source")
            return _head(
                size=3,
                etag="existing",
                metadata={"allbot-copy-plan-sha256": plan_sha},
            )

        def copy_object(self, **kwargs):
            self.copy_calls.append(kwargs)

    client = Client()
    result = server_side_copy_r2_object(
        client,
        bucket="user-data-prod",
        source_key="old.png",
        target_key="new.png",
        expected_size=3,
        expected_last_modified=datetime(2026, 8, 9, tzinfo=timezone.utc),
        expected_etag="source",
        copy_plan_sha256=plan_sha,
    )

    assert result["recovered"] is True
    assert result["etag"] == "existing"
    assert client.copy_calls == []


def test_server_side_copy_recovers_destination_precondition_race():
    plan_sha = "f" * 64

    class Client:
        def __init__(self):
            self.raced = False

        def head_object(self, *, Bucket, Key):
            if Key == "old.png":
                return _head(size=3, etag="source")
            if self.raced:
                return _head(
                    size=3,
                    etag="target",
                    metadata={"allbot-copy-plan-sha256": plan_sha},
                )
            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "missing"}},
                "HeadObject",
            )

        def copy_object(self, **_kwargs):
            self.raced = True
            raise ClientError(
                {"Error": {"Code": "PreconditionFailed", "Message": "exists"}},
                "CopyObject",
            )

    result = server_side_copy_r2_object(
        Client(),
        bucket="user-data-prod",
        source_key="old.png",
        target_key="new.png",
        expected_size=3,
        expected_last_modified=datetime(2026, 8, 9, tzinfo=timezone.utc),
        expected_etag="source",
        copy_plan_sha256=plan_sha,
    )

    assert result["recovered"] is True


def test_server_side_copy_fails_closed_when_existing_target_has_other_plan():
    class Client:
        def head_object(self, *, Bucket, Key):
            if Key == "old.png":
                return _head(size=3, etag="source")
            return _head(
                size=3,
                etag="existing",
                metadata={"allbot-copy-plan-sha256": "c" * 64},
            )

    with pytest.raises(RuntimeError, match="different or missing copy plan marker"):
        server_side_copy_r2_object(
            Client(),
            bucket="user-data-prod",
            source_key="old.png",
            target_key="new.png",
            expected_size=3,
            expected_last_modified=datetime(2026, 8, 9, tzinfo=timezone.utc),
            expected_etag="source",
            copy_plan_sha256="b" * 64,
        )


def test_server_side_copy_binds_the_frozen_source_etag():
    class Client:
        def head_object(self, *, Bucket, Key):
            return _head(size=3, etag="changed")

    with pytest.raises(RuntimeError, match="ETag changed"):
        server_side_copy_r2_object(
            Client(),
            bucket="user-data-prod",
            source_key="old.png",
            target_key="new.png",
            expected_size=3,
            expected_last_modified=datetime(2026, 8, 9, tzinfo=timezone.utc),
            expected_etag="frozen",
            copy_plan_sha256="d" * 64,
        )


def test_copy_candidates_deduplicate_identical_targets_and_reject_conflicts():
    modified = datetime(2026, 8, 9, tzinfo=timezone.utc)
    base = {
        "source_name": "r2-user-data-prod",
        "source_key": "old.png",
        "target_key": "task-results/backend/primary.png",
        "byte_size": 3,
        "source_last_modified": modified,
        "source_etag": "source",
    }
    groups = group_copy_candidates([{**base, "id": 1}, {**base, "id": 2}])

    assert len(groups) == 1
    assert [row["id"] for row in groups[0]] == [1, 2]

    with pytest.raises(RuntimeError, match="conflicting frozen sources"):
        group_copy_candidates(
            [{**base, "id": 1}, {**base, "id": 2, "source_key": "other.png"}]
        )


def test_r2_custom_headers_survive_boto_parameter_validation():
    context = {}
    params = {"Bucket": "user-data-prod", "custom_headers": {"x-test": "value"}}

    _process_r2_custom_arguments(params, context)
    request = {"headers": {}}
    _add_r2_custom_headers(request, context)

    assert "custom_headers" not in params
    assert request["headers"] == {"x-test": "value"}


@pytest.mark.asyncio
async def test_copy_success_marks_every_duplicate_ledger_row():
    class Conn:
        def __init__(self):
            self.calls = []

        async def execute(self, query, *params):
            self.calls.append((query, params))

    conn = Conn()
    await _persist_copy_success(
        conn,
        [{"id": 1}, {"id": 2}],
        {"etag": "target", "multipart": False, "recovered": False},
    )

    assert conn.calls[0][1][0] == [1, 2]
    assert conn.calls[0][1][1:] == ("target", "r2_copy_object")


def test_execute_copy_concurrency_is_bounded():
    base = [
        "execute-copy",
        "--plan-sha256",
        "a" * 64,
        "--confirm",
        "COPY_HISTORY_MEDIA_" + "a" * 64,
        "--config",
        "/tmp/config.json",
    ]
    args = _parser().parse_args([*base, "--copy-concurrency", "64"])
    assert args.copy_concurrency == 64
    assert args.max_pool_connections is None
    assert (
        _parser()
        .parse_args([*base, "--copy-concurrency", "64", "--max-pool-connections", "96"])
        .max_pool_connections
        == 96
    )
    with pytest.raises(SystemExit):
        _parser().parse_args([*base, "--copy-concurrency", "0"])
    assert (
        _parser().parse_args([*base, "--copy-concurrency", "128"]).copy_concurrency
        == 128
    )
    with pytest.raises(SystemExit):
        _parser().parse_args([*base, "--copy-concurrency", "129"])
    parsed = _parser().parse_args(
        [
            *base,
            "--object-max-retries",
            "5",
            "--retry-base-seconds",
            "1",
            "--retry-max-seconds",
            "16",
            "--retry-jitter-ratio",
            "0.25",
        ]
    )
    assert parsed.object_max_retries == 5
    with pytest.raises(SystemExit):
        _parser().parse_args([*base, "--object-max-retries", "-1"])
    with pytest.raises(SystemExit):
        _parser().parse_args([*base, "--retry-jitter-ratio", "1.1"])


def test_copy_client_pool_defaults_to_one_and_a_half_times_concurrency(monkeypatch):
    captured = {}

    class Events:
        def register(self, *_args):
            return None

    class Client:
        meta = type("Meta", (), {"events": Events()})()

    def fake_client(*_args, **kwargs):
        captured.update(kwargs)
        return Client()

    monkeypatch.setattr("scripts.history_media_r2_migration.boto3.client", fake_client)
    pool = _resolve_copy_max_pool_connections(64, None)
    _s3_client(
        {
            "endpoint": "https://example.invalid",
            "access_key": "key",
            "secret_key": "secret",
        },
        max_pool_connections=pool,
    )

    assert pool == 96
    assert captured["config"].max_pool_connections == 96
    assert captured["config"].proxies == {}
    with pytest.raises(ValueError, match="not be smaller"):
        _resolve_copy_max_pool_connections(64, 63)


def test_copy_client_uses_only_the_frozen_explicit_https_proxy(monkeypatch):
    captured = {}

    class Events:
        def register(self, *_args):
            return None

    class Client:
        meta = type("Meta", (), {"events": Events()})()

    monkeypatch.setattr(
        "scripts.history_media_r2_migration.boto3.client",
        lambda *_args, **kwargs: captured.update(kwargs) or Client(),
    )
    transport = _r2_transport(
        {
            "r2_transport": {
                "mode": "https_proxy",
                "proxy_url": "http://127.0.0.1:7890",
            }
        }
    )

    _s3_client(
        {
            "endpoint": "https://example.invalid",
            "access_key": "key",
            "secret_key": "secret",
        },
        max_pool_connections=128,
        transport=transport,
    )

    assert captured["config"].proxies == {
        "https": "http://127.0.0.1:7890"
    }


@pytest.mark.parametrize(
    "error_text",
    [
        "An error occurred (429) when calling CopyObject",
        "HTTPStatusCode: 503 ServiceUnavailable",
        "ReadTimeoutError: read timed out",
    ],
)
def test_adaptive_copy_lowers_one_level_for_transient_r2_failures(error_text):
    controller = AdaptiveCopyController(initial_concurrency=64)

    assert is_transient_copy_failure(error_text) is True
    assert controller.record_failure(error_text) == 32


def test_adaptive_copy_uses_64_32_16_8_and_requires_three_clean_batches_to_raise():
    controller = AdaptiveCopyController(initial_concurrency=64)

    assert controller.record_failure("HTTPStatusCode: 503") == 32
    assert controller.record_failure("ConnectTimeoutError") == 16
    assert controller.record_failure("SlowDown") == 8
    assert controller.record_success() == 8
    assert controller.record_success() == 8
    assert controller.record_success() == 16


def test_adaptive_copy_rejects_non_transient_failures():
    controller = AdaptiveCopyController(initial_concurrency=64)

    with pytest.raises(RuntimeError, match="non-transient"):
        controller.record_failure("AccessDenied: source identity changed")


def test_copy_resume_after_object_write_before_ledger_commit_uses_plan_marker():
    plan_sha = "9" * 64

    class Client:
        def __init__(self):
            self.copy_calls = 0
            self.target_exists = False

        def head_object(self, *, Bucket, Key):
            if Key == "old.png":
                return _head(size=3, etag="source")
            if self.target_exists:
                return _head(
                    size=3,
                    etag="target",
                    metadata={"allbot-copy-plan-sha256": plan_sha},
                )
            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "missing"}},
                "HeadObject",
            )

        def copy_object(self, **_kwargs):
            self.copy_calls += 1
            self.target_exists = True

    client = Client()
    kwargs = {
        "bucket": "user-data-prod",
        "source_key": "old.png",
        "target_key": "new.png",
        "expected_size": 3,
        "expected_last_modified": datetime(2026, 8, 9, tzinfo=timezone.utc),
        "expected_etag": "source",
        "copy_plan_sha256": plan_sha,
    }

    first = server_side_copy_r2_object(client, **kwargs)
    resumed = server_side_copy_r2_object(client, **kwargs)

    assert first["recovered"] is False
    assert resumed["recovered"] is True
    assert client.copy_calls == 1


def test_large_server_side_copy_uses_multipart_copy_without_media_body():
    part_size = 512 * 1024 * 1024
    total_size = part_size + 7

    class Client:
        def __init__(self):
            self.created = False
            self.create_kwargs = None
            self.parts = []

        def head_object(self, *, Bucket, Key):
            if Key == "old/large.bin":
                return _head(size=total_size, etag="large-source")
            if self.created:
                return _head(
                    size=total_size,
                    etag="multipart-target",
                    metadata={"allbot-copy-plan-sha256": "e" * 64},
                )
            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "missing"}},
                "HeadObject",
            )

        def create_multipart_upload(self, **kwargs):
            self.created = True
            self.create_kwargs = kwargs
            return {"UploadId": "upload-1"}

        def upload_part_copy(self, **kwargs):
            self.parts.append(kwargs)
            return {"CopyPartResult": {"ETag": f'"part-{kwargs["PartNumber"]}"'}}

        def complete_multipart_upload(self, **kwargs):
            self.completed = kwargs

        def abort_multipart_upload(self, **_kwargs):  # pragma: no cover
            raise AssertionError("successful multipart copy must not abort")

    client = Client()
    result = server_side_copy_r2_object(
        client,
        bucket="user-data-prod",
        source_key="old/large.bin",
        target_key="new/large.bin",
        expected_size=total_size,
        expected_last_modified=datetime(2026, 8, 9, tzinfo=timezone.utc),
        copy_plan_sha256="e" * 64,
        single_copy_limit=part_size,
        multipart_part_size=part_size,
    )

    assert result["multipart"] is True
    assert client.create_kwargs["custom_headers"] == {"If-None-Match": "*"}
    assert [part["CopySourceRange"] for part in client.parts] == [
        f"bytes=0-{part_size - 1}",
        f"bytes={part_size}-{total_size - 1}",
    ]
    assert client.completed["MultipartUpload"]["Parts"] == [
        {"ETag": "part-1", "PartNumber": 1},
        {"ETag": "part-2", "PartNumber": 2},
    ]


def test_execute_copy_has_no_client_side_media_transfer_path():
    import inspect

    import scripts.history_media_r2_migration as module

    source = inspect.getsource(module._execute_copy)
    timed_source = inspect.getsource(module._timed_server_side_copy_with_retries)
    forbidden = (
        "_read_s3_sha",
        "_open_source_body",
        "NamedTemporaryFile",
        "upload_fileobj",
    )
    assert not any(name in source + timed_source for name in forbidden)
    assert "_timed_server_side_copy_with_retries" in source
    assert "server_side_copy_r2_object" in timed_source


def test_execute_copy_sizes_worker_pool_to_requested_concurrency():
    import inspect

    import scripts.history_media_r2_migration as module

    source = inspect.getsource(module._execute_copy)
    group_source = inspect.getsource(module._run_copy_group_batch)

    assert "ThreadPoolExecutor(max_workers=args.copy_concurrency)" in source
    assert "loop.run_in_executor" in group_source
    assert "asyncio.as_completed" in group_source
    assert "copy_executor" in source


def test_seed_uses_one_bulk_copy_stage_per_history_batch():
    import inspect

    import scripts.history_media_r2_migration as module

    source = inspect.getsource(module._seed)
    assert "copy_records_to_table" in source
    assert "BACKEND_BATCH_SQL" in source
    assert "for asset in assets" in source
    assert "await conn.fetchrow(BACKEND" not in source
    assert (
        "select id from analytics_media_asset_catalog where history_id=$1" not in source
    )


def test_initial_probe_does_not_starve_pending_rows_with_deferred_failures():
    import inspect

    import scripts.history_media_r2_migration as module

    source = inspect.getsource(module._probe)
    assert "m.status='pending_probe'" in source
    assert "args.recheck_deferred" in source
    assert "remaining_pending" in source
    assert "args.target_only" in source
    assert "target_checked_at is null" in source


def test_receipt_only_probe_is_fail_closed_and_skips_legacy_sources():
    import inspect

    import scripts.history_media_r2_migration as module

    source = inspect.getsource(module._probe)
    assert "args.receipt_only" in source
    assert "a.status='archived_verified'" in source
    assert "SYSTEMIC_NAS_RECEIPT_QUERY_FAILURE" in source
    assert "if args.receipt_only" in source


def test_probe_cli_exposes_receipt_only_mode():
    script = (
        Path(__file__).resolve().parents[2] / "scripts/history_media_r2_migration.py"
    )
    result = subprocess.run(
        [sys.executable, str(script), "probe", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--receipt-only" in result.stdout


def test_frozen_copy_plan_cannot_bypass_incomplete_probe_batches():
    import inspect

    import scripts.history_media_r2_migration as module

    source = inspect.getsource(module._create_plan)
    assert "PROBE_NOT_COMPLETE" in source
    assert '"pending_at_freeze"' in source
    assert '"run_status_at_freeze"' in source
    assert '"partial_scope"' in source

    script = (
        Path(__file__).resolve().parents[2] / "scripts/history_media_r2_migration.py"
    )
    result = subprocess.run(
        [sys.executable, str(script), "plan-copy", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--allow-incomplete" not in result.stdout


def test_plan_and_report_stream_rowsets_instead_of_fetching_all_rows():
    import inspect

    import scripts.history_media_r2_migration as module

    assert "_stream_plan_rowset" in inspect.getsource(module._create_plan)
    assert "_stream_plan_rowset" in inspect.getsource(module._report)
    assert "_stream_plan_rowset" in inspect.getsource(module._execute_copy)
    assert "limit $3" in inspect.getsource(module._execute_copy)


def test_streaming_json_array_digest_matches_materialized_digest():
    rows = [{"a": 1}, {"a": 2, "b": "x"}]
    digest = StreamingJsonArraySha256()
    for row in rows:
        digest.add(row)
    import hashlib

    payload = json.dumps(
        rows, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()
    assert digest.hexdigest() == hashlib.sha256(payload).hexdigest()
    assert digest.count == 2


def test_asyncpg_dsn_normalizes_web_ssl_query_parameter():
    dsn, ssl_mode = normalize_asyncpg_dsn(
        "postgresql+asyncpg://user:secret@db.example/prod?ssl=require&x=1"
    )
    assert dsn == "postgresql://user:secret@db.example/prod?x=1"
    assert ssl_mode == "require"


@pytest.mark.asyncio
async def test_target_only_probe_deduplicates_keys_and_persists_serially():
    class Body(BytesIO):
        def close(self):
            super().close()

    class Client:
        def __init__(self):
            self.head_calls = 0
            self.get_calls = 0

        def head_object(self, *, Bucket, Key):
            self.head_calls += 1
            assert Bucket == "user-data-prod"
            return {
                "ContentLength": 3,
                "LastModified": datetime(2026, 8, 9, tzinfo=timezone.utc),
            }

        def get_object(self, *, Bucket, Key):
            self.get_calls += 1
            return {"Body": Body(b"abc")}

    class Conn:
        def __init__(self):
            self.calls = []

        async def execute(self, query, *params):
            self.calls.append(("execute", query, params))

        async def executemany(self, query, params):
            self.calls.append(("executemany", query, list(params)))

    client = Client()
    conn = Conn()
    rows = [
        {"id": 1, "catalog_asset_id": 11, "target_key": "task-inputs/r/0.png"},
        {"id": 2, "catalog_asset_id": 12, "target_key": "task-inputs/r/0.png"},
    ]
    assert (
        await _probe_target_rows(
            conn,
            rows,
            target_client=client,
            concurrency=8,  # type: ignore[arg-type]
        )
        == 3
    )
    assert client.head_calls == 1
    assert client.get_calls == 1
    assert any("target_verified" in query for _kind, query, _params in conn.calls)


@pytest.mark.asyncio
async def test_r2_only_probe_resolves_old_keys_with_head_only():
    class Client:
        def __init__(self):
            self.head_calls = []
            self.get_calls = []

        def head_object(self, *, Bucket, Key):
            self.head_calls.append((Bucket, Key))
            if Key == "7/output_images/old.png":
                return {
                    "ContentLength": 3,
                    "ETag": '"source-etag"',
                    "LastModified": datetime(2026, 8, 9, tzinfo=timezone.utc),
                }
            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "missing"}},
                "HeadObject",
            )

        def get_object(self, *, Bucket, Key):
            self.get_calls.append((Bucket, Key))
            raise AssertionError("R2 key resolution must not download object bodies")

    class Conn:
        def __init__(self):
            self.calls = []

        async def execute(self, query, *params):
            self.calls.append(("execute", query, params))

        async def executemany(self, query, params):
            self.calls.append(("executemany", query, list(params)))

    client = Client()
    conn = Conn()
    rows = [
        {
            "id": 1,
            "run_id": "run",
            "catalog_asset_id": 11,
            "target_key": "task-results/backend/primary.png",
            "original_ref": "7/output_images/old.png",
            "registry_task_id": "registry",
        },
        {
            "id": 2,
            "run_id": "run",
            "catalog_asset_id": 12,
            "target_key": "task-results/backend/primary.png",
            "original_ref": "7/output_images/old.png",
            "registry_task_id": "registry",
        },
    ]

    assert (
        await _probe_r2_rows(
            conn,
            rows,
            r2_client=client,
            concurrency=8,  # type: ignore[arg-type]
        )
        == 0
    )
    assert len(client.head_calls) == 4
    assert client.get_calls == []
    assert any("copy_required" in query for _kind, query, _params in conn.calls)
    assert any("source_etag" in query for _kind, query, _params in conn.calls)
    assert any("r2_checked_at" in query for _kind, query, _params in conn.calls)
    assert not any("source_missing" in query for _kind, query, _params in conn.calls)


def test_frozen_probe_executor_has_only_head_object_storage_io():
    import inspect

    import scripts.history_media_r2_migration as module

    source = inspect.getsource(module._execute_probe) + inspect.getsource(
        module._collect_probe_head_outcomes
    )
    assert "_head_s3_identity" in source
    for forbidden in ("get_object", "copy_object", "upload_fileobj", "delete_object"):
        assert forbidden not in source


def test_migration_ledger_is_independent_and_bound_to_history_watermark():
    assert "analytics_history_media_migration_runs" in MIGRATION_DDL
    assert "analytics_history_media_r2_migrations" in MIGRATION_DDL
    assert "history_watermark" in MIGRATION_DDL
    assert "unique (run_id, history_id, role, ordinal)" in MIGRATION_DDL
    assert "copy_plan_sha256" in MIGRATION_DDL
    assert "switch_plan_sha256" in MIGRATION_DDL
    assert "r2_checked_at" in MIGRATION_DDL
    assert "analytics_history_media_migration_plan_batches" in MIGRATION_DDL
    assert "probe_plan_sha256" in MIGRATION_DDL
    assert "('probe','copy','switch')" in MIGRATION_DDL
    assert "'paused','superseded'" in MIGRATION_DDL


def test_copy_and_switch_plans_are_strictly_parent_scoped_and_exclude_completed_assets():
    import inspect

    import scripts.history_media_r2_migration as module

    source = inspect.getsource(module._create_plan)
    assert "probe_plan_sha256=any($2::text[])" in source
    assert "copy_plan_sha256=$2" in source
    assert "switch_completed_at is null" in source
    assert "COPY_PLAN_HAS_UNSUPPORTED_MULTIPART_OBJECTS" in source
    switch_source = inspect.getsource(module._execute_switch)
    assert "switch plan rowset changed" in switch_source
    assert "predecessor switch plan identity changed" in switch_source
    assert "switch batch production CAS state changed" in switch_source
    assert "set local lock_timeout = '10s'" in switch_source
    assert "_verify_switch_plan" in switch_source
    verification_source = inspect.getsource(module._verify_switch_plan)
    assert "len(gallery_samples) < 32" in verification_source
    assert "len(owner_samples) < 64" in verification_source
    assert "switch verification found an old History reference" in verification_source


def test_successor_freeze_supersedes_only_unfinished_batches_and_copy_uses_chain():
    import inspect

    import scripts.history_media_r2_migration as module

    successor_source = inspect.getsource(module._create_successor_probe_plan)
    assert "for update" in successor_source.lower()
    assert "probe_plan_sha256 is null" in successor_source
    assert "status='pending_probe'" in successor_source
    assert "status='superseded'" in successor_source
    assert "status<>'completed'" in successor_source
    assert "successor Probe asset conservation failed" in successor_source

    copy_source = inspect.getsource(module._create_plan)
    assert "probe_plan_sha256=any($2::text[])" in copy_source
    assert "probe_chain_plan_sha256s" in copy_source

    parsed = _parser().parse_args(
        [
            "plan-probe-successor",
            "--run-id",
            "11111111-1111-1111-1111-111111111111",
            "--predecessor-plan-sha256",
            "a" * 64,
            "--config",
            "/secure/config.json",
            "--artifact-digest",
            "sha256:" + "b" * 64,
            "--output",
            "/secure/successor.json",
        ]
    )
    assert parsed.command == "plan-probe-successor"


def test_copy_execution_recomputes_frozen_rowset_in_ledger_id_order():
    import inspect

    import scripts.history_media_r2_migration as module

    source = inspect.getsource(module._execute_copy)
    rowset_check = source.split("if rowset_sha !=", 1)[0].rsplit(
        "await _stream_plan_rowset", 1
    )[1]

    assert "order by id" in rowset_check
    assert "order by history_id,role,ordinal" not in rowset_check


def test_copy_replacement_plan_retains_completed_and_supersedes_only_remainder():
    import inspect

    import scripts.history_media_r2_migration as module

    parsed = _parser().parse_args(
        [
            "plan-copy",
            "--run-id",
            "11111111-1111-1111-1111-111111111111",
            "--parent-plan-sha256",
            "a" * 64,
            "--supersedes-plan-sha256",
            "b" * 64,
            "--config",
            "/secure/config.json",
            "--artifact-digest",
            "sha256:" + "c" * 64,
            "--output",
            "/secure/replacement.json",
        ]
    )
    assert parsed.supersedes_plan_sha256 == "b" * 64

    source = inspect.getsource(module._replace_unexecuted_copy_plan)
    assert "for update" in source.lower()
    assert "copy_completed_at is not null" in source
    assert "status='failed'" in source
    assert '{"pending", "completed"}' in source
    assert "status<>'completed'" in source
    assert "copy_plan_sha256=$4" in source
    assert "retained_assets" in source
    assert "conserved_asset_count" in source

    execute_source = inspect.getsource(module._execute_copy)
    assert "copy plan has been superseded" in execute_source
    assert "existing copy plan must be explicitly superseded" in inspect.getsource(
        module._reject_unacknowledged_copy_replan
    )

    assert (
        "drop constraint if exists "
        "analytics_history_media_migration_plans_run_id_plan_type_rowset_sha256_key"
        in MIGRATION_DDL
    )


def test_copy_successor_verification_and_switch_aggregate_the_full_plan_chain():
    import inspect

    import scripts.history_media_r2_migration as module

    verify_source = inspect.getsource(module._verify_copy_plan_objects)
    planner_source = inspect.getsource(module._create_plan)
    execute_source = inspect.getsource(module._execute_copy)

    assert "copy_plan_sha256=any($2::text[])" in verify_source
    assert 'copy_plan_sha256=str(row["copy_plan_sha256"])' in verify_source
    assert '"copy_chain_plan_sha256s"' in planner_source
    assert "predecessor Copy chain is not terminal" in planner_source
    assert "copy_plan_sha256=any($2::text[])" in planner_source
    assert "copy plan batches identity changed" in execute_source


def test_standard_targets_require_explicit_dual_ids():
    input_asset = AssetIdentity(1, "input", 2, "7/input_images/a.JPEG")
    output_asset = AssetIdentity(1, "output", 0, "7/output_images/result.png")
    extra_asset = AssetIdentity(1, "extra:mask preview", 3, "mask.webp")

    assert (
        build_standard_target(
            input_asset, registry_task_id="registry-1", backend_task_id=None
        )
        == "task-inputs/registry-1/2.jpeg"
    )
    assert (
        build_standard_target(
            output_asset, registry_task_id="registry-1", backend_task_id="backend-1"
        )
        == "task-results/backend-1/primary.png"
    )
    assert (
        build_standard_target(
            extra_asset, registry_task_id="registry-1", backend_task_id="backend-1"
        )
        == "task-results/backend-1/extras/extra-mask-preview-3.webp"
    )
    assert (
        build_standard_target(
            output_asset, registry_task_id="registry-1", backend_task_id=None
        )
        is None
    )
    assert (
        build_standard_target(
            input_asset, registry_task_id=None, backend_task_id="backend-1"
        )
        is None
    )


def test_external_and_unmanaged_references_are_blocked():
    assert classify_reference("https://third-party.example/file.png") == "blocked"
    assert classify_reference("data:image/png;base64,AAAA") == "blocked"
    assert classify_reference("7/input_images/a.png") == "managed"
    assert classify_reference("task-results/backend/primary.png") == "managed"


def test_candidate_order_is_deterministic_and_deduplicated():
    assert build_candidate_keys("7/input_images/a.png", "registry-1") == (
        "7/input_images/a.png",
        "history/registry-1/a.png",
        "a.png",
    )
    assert build_candidate_keys("a.png", "registry-1") == (
        "a.png",
        "history/registry-1/a.png",
    )


def test_history_json_text_keeps_nested_extra_assets():
    assets = history_assets_from_record(
        {
            "id": 7,
            "input_file": "a.png|b.png",
            "output_file": "result.png",
            "extra_outputs": '{"preview":{"nested":[{"path":"x.png"}]}}',
        }
    )
    assert [(item.role, item.ordinal) for item in assets] == [
        ("input", 0),
        ("input", 1),
        ("output", 0),
        ("extra:preview", 0),
    ]


def test_full_sha_hashes_stream_and_counts_bytes():
    digest, byte_size = hash_body(BytesIO(b"abc"), chunk_size=2)
    assert digest == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert byte_size == 3


def test_target_status_requires_full_digest_equality():
    assert classify_target_status(source_sha256="a" * 64, target_sha256=None) == (
        "copy_required",
        None,
    )
    assert classify_target_status(source_sha256="a" * 64, target_sha256="a" * 64) == (
        "target_verified",
        None,
    )
    assert classify_target_status(source_sha256="a" * 64, target_sha256="b" * 64) == (
        "target_conflict",
        "TARGET_SHA256_CONFLICT",
    )


def test_resume_must_keep_frozen_history_watermark():
    assert validate_resume_identity(stored_watermark=99, requested_watermark=None) == 99
    with pytest.raises(ValueError, match="frozen History watermark"):
        validate_resume_identity(stored_watermark=99, requested_watermark=100)


def test_source_fact_cache_reuses_only_unchanged_head_identity():
    cache = SourceFactCache()
    last_modified = datetime(2026, 8, 8, tzinfo=timezone.utc)
    cache.remember(
        source="r2-user-data-prod",
        key="a.png",
        byte_size=3,
        last_modified=last_modified,
        sha256="a" * 64,
    )
    assert (
        cache.lookup(
            source="r2-user-data-prod",
            key="a.png",
            byte_size=3,
            last_modified=last_modified,
        )
        == "a" * 64
    )
    assert (
        cache.lookup(
            source="r2-user-data-prod",
            key="a.png",
            byte_size=4,
            last_modified=last_modified,
        )
        is None
    )
    assert (
        cache.lookup(
            source="r2-user-data-prod",
            key="a.png",
            byte_size=3,
            last_modified=last_modified + timedelta(seconds=1),
        )
        is None
    )


def test_missing_confirmation_requires_all_not_found_twice_and_24_hours():
    now = datetime(2026, 8, 9, tzinfo=timezone.utc)
    assert evaluate_missing_round(
        statuses=("not_found", "not_found"),
        previous_rounds=0,
        first_missing_at=None,
        now=now,
    ) == ("provisional_missing", 1, now)
    assert (
        evaluate_missing_round(
            statuses=("not_found", "not_found"),
            previous_rounds=1,
            first_missing_at=now - timedelta(hours=24),
            now=now,
        )[0]
        == "confirmed_lost"
    )
    assert (
        evaluate_missing_round(
            statuses=("not_found", "source_offline"),
            previous_rounds=1,
            first_missing_at=now - timedelta(days=2),
            now=now,
        )[0]
        == "source_offline"
    )


def test_copy_plan_is_compact_stable_and_exactly_gated():
    rows = [
        {
            "history_id": 9,
            "role": "input",
            "ordinal": 0,
            "target_key": "task-inputs/r/0.png",
            "source_sha256": "a" * 64,
            "byte_size": 3,
            "status": "copy_required",
        }
    ]
    manifest = build_copy_plan(
        run_id="11111111-1111-1111-1111-111111111111",
        history_watermark=99,
        rows=rows,
        sha_bytes_read=6,
    )
    assert "objects" not in manifest
    assert manifest["counts"] == {"copy_required": 1}
    assert manifest["bytes"] == {"copy_required": 3}
    assert len(manifest["rowset_sha256"]) == 64
    assert len(manifest["plan_sha256"]) == 64
    assert len(json.dumps(manifest)) < 4096

    validate_copy_gate(
        expected_plan_sha256=manifest["plan_sha256"],
        supplied_plan_sha256=manifest["plan_sha256"],
        confirmation=f"COPY_HISTORY_MEDIA_{manifest['plan_sha256']}",
    )
    with pytest.raises(ValueError, match="exact copy plan"):
        validate_copy_gate(
            expected_plan_sha256=manifest["plan_sha256"],
            supplied_plan_sha256="b" * 64,
            confirmation="yes",
        )


def test_switch_gate_binds_manifest_cas_hash():
    validate_switch_gate(
        expected_plan_sha256="a" * 64,
        supplied_plan_sha256="a" * 64,
        expected_manifest_sha256="b" * 64,
        actual_manifest_sha256="b" * 64,
        confirmation=f"SWITCH_HISTORY_MEDIA_{'a' * 64}",
    )
    with pytest.raises(ValueError, match="History media manifest changed"):
        validate_switch_gate(
            expected_plan_sha256="a" * 64,
            supplied_plan_sha256="a" * 64,
            expected_manifest_sha256="b" * 64,
            actual_manifest_sha256="c" * 64,
            confirmation=f"SWITCH_HISTORY_MEDIA_{'a' * 64}",
        )


def test_history_reference_replacement_preserves_unselected_assets():
    history = {
        "input_file": "old-a.png|old-b.png",
        "output_file": "old-output.png",
        "extra_outputs": {
            "preview": {
                "first": {"path": "one.png", "label": "one"},
                "nested": [{"path": "two.png"}],
            }
        },
    }
    replace_asset_reference(history, "input", 1, "task-inputs/r/1.png")
    replace_asset_reference(
        history, "extra:preview", 1, "task-results/b/extras/extra-preview-1.png"
    )
    assert history["input_file"] == "old-a.png|task-inputs/r/1.png"
    assert history["output_file"] == "old-output.png"
    assert history["extra_outputs"]["preview"]["first"]["path"] == "one.png"
    assert history["extra_outputs"]["preview"]["nested"][0]["path"].startswith(
        "task-results/"
    )


def test_script_has_no_bucket_list_or_delete_operation():
    import inspect

    import scripts.history_media_r2_migration as module

    source = inspect.getsource(module)
    forbidden = ("list_objects", "get_paginator", "delete_object", "delete_objects")
    assert not any(name in source for name in forbidden)


def test_cli_is_directly_executable_and_exposes_all_phases():
    script = (
        Path(__file__).resolve().parents[2] / "scripts/history_media_r2_migration.py"
    )
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    for command in (
        "seed",
        "probe",
        "plan-probe",
        "plan-probe-successor",
        "execute-probe",
        "plan-copy",
        "execute-copy",
        "plan-switch",
        "execute-switch",
        "report",
    ):
        assert command in result.stdout
