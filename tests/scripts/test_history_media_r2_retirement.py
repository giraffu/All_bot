from __future__ import annotations

import inspect
import json
import threading
import time
from argparse import Namespace
from datetime import datetime, timezone

import pytest
from botocore.exceptions import ClientError

from scripts.history_media_r2_retirement import (
    BULK_SOURCE_IDENTITY_POLICY,
    DURABILITY_NAS_ARCHIVE,
    DURABILITY_R2_PERSISTENT_TARGET,
    RETIREMENT_BLOCKER_INDEX_DDL,
    RETIREMENT_BLOCKER_SQL,
    RETIREMENT_BLOCKER_TIMEOUT_SECONDS,
    RETIREMENT_DDL,
    RetirementHeadConcurrencyController,
    _durability_archive_config,
    _delete_sources,
    _ensure_retirement_blocker_indexes,
    _expected_switch_counts,
    _head_candidates,
    _parser,
    _mark_retirement_plan_paused,
    _missing_retirement_blocker_indexes,
    _retirement_has_blockers,
    _retirement_head_controller,
    _retirement_object_identity,
    _retirement_runtime_identity,
    _s3_client,
    _validate_retirement_execution_policy,
    build_bulk_retirement_plan,
    build_bulk_retirement_successor_manifest,
    build_retirement_plan,
    classify_retirement_candidate,
    validate_delete_gate,
    validate_retirement_object_heads,
)


def _candidate(**overrides):
    value = {
        "source_name": "r2-user-data-prod",
        "source_key": "private/old-object.png",
        "byte_size": 100,
        "source_etag": "source-etag",
        "source_last_modified": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "asset_count": 1,
        "switched_asset_count": 1,
        "pending_copy_refs": 0,
        "unswitched_refs": 0,
        "target_collisions": 0,
        "live_history_refs": 0,
        "archive_verified_asset_count": 1,
        "archive_sha256": "a" * 64,
        "nas_bucket": "archive",
        "nas_key": "sha256/aa/" + "a" * 64,
        "targets": [
            {
                "target_key": "task-results/task/primary.png",
                "copy_plan_sha256": "c" * 64,
                "target_etag": "source-etag",
            }
        ],
    }
    value.update(overrides)
    return value


def test_retirement_head_concurrency_uses_error_rate_and_clean_windows():
    controller = RetirementHeadConcurrencyController(initial_concurrency=128)

    single_error = controller.observe(
        request_count=1000, transient_error_count=1, rate_limit_count=0
    )
    assert single_error.action == "hold"
    assert controller.current_concurrency == 128

    sustained_errors = controller.observe(
        request_count=1000, transient_error_count=6, rate_limit_count=0
    )
    assert sustained_errors.action == "lower"
    assert sustained_errors.reason == "sustained_transient_error_rate"
    assert controller.current_concurrency == 64

    first_clean = controller.observe(
        request_count=1000, transient_error_count=0, rate_limit_count=0
    )
    second_clean = controller.observe(
        request_count=1000, transient_error_count=0, rate_limit_count=0
    )
    assert first_clean.action == "hold"
    assert second_clean.action == "raise"
    assert controller.current_concurrency == 128

    rate_limited = controller.observe(
        request_count=1, transient_error_count=1, rate_limit_count=1
    )
    assert rate_limited.action == "lower"
    assert rate_limited.reason == "rate_limit"
    assert controller.current_concurrency == 64


def test_retirement_head_concurrency_opens_circuit_on_systemic_errors():
    controller = RetirementHeadConcurrencyController(initial_concurrency=128)

    decision = controller.observe(
        request_count=200, transient_error_count=20, rate_limit_count=0
    )

    assert decision.action == "systemic"
    assert decision.reason == "systemic_transient_error_rate"
    assert controller.current_concurrency == 128


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"pending_copy_refs": 1}, "pending_copy_source"),
        ({"unswitched_refs": 1}, "unswitched_reference"),
        ({"target_collisions": 1}, "source_is_target"),
        ({"live_history_refs": 1}, "live_history_reference"),
        ({"archive_verified_asset_count": 0}, "archive_incomplete"),
    ],
)
def test_retirement_candidate_fails_closed(overrides, reason):
    classification = classify_retirement_candidate(_candidate(**overrides))
    assert classification == reason


def test_retirement_candidate_requires_archive_coverage_for_every_asset():
    classification = classify_retirement_candidate(
        _candidate(asset_count=2, archive_verified_asset_count=1)
    )
    assert classification == "archive_incomplete"
    assert classify_retirement_candidate(_candidate()) == "eligible"


def test_r2_persistent_target_is_an_explicit_durability_basis_without_nas():
    candidate = _candidate(
        durability_basis=DURABILITY_R2_PERSISTENT_TARGET,
        archive_verified_asset_count=0,
        archive_sha256="",
        nas_bucket="",
        nas_key="",
    )

    assert classify_retirement_candidate(candidate) == "eligible"
    manifest, _frozen, _batches = build_retirement_plan(
        run_id="11111111-1111-1111-1111-111111111111",
        parent_copy_plan_sha256="p" * 64,
        parent_switch_plan_sha256s=["s" * 64],
        objects=[candidate],
        report_sha256="r" * 64,
        runtime_identity={"artifact_digest": "sha256:" + "f" * 64},
        durability_basis=DURABILITY_R2_PERSISTENT_TARGET,
    )

    assert manifest["durability_basis"] == DURABILITY_R2_PERSISTENT_TARGET
    assert manifest["schema"] == "allbot-history-media-r2-retirement-plan/v2"

    assert (
        classify_retirement_candidate(dict(candidate, targets=[]))
        == "persistent_target_missing"
    )


def test_r2_persistent_target_rowset_survives_postgres_blank_char_round_trip():
    frozen = _candidate(
        durability_basis=DURABILITY_R2_PERSISTENT_TARGET,
        archive_verified_asset_count=0,
        archive_sha256="",
        nas_bucket="",
        nas_key="",
    )
    database_round_trip = dict(frozen, archive_sha256=" " * 64)

    assert _retirement_object_identity(database_round_trip) == (
        _retirement_object_identity(frozen)
    )
    schema_upgraded_round_trip = dict(
        database_round_trip, scope_asset_count=0, scope_facts={}
    )
    assert _retirement_object_identity(schema_upgraded_round_trip) == (
        _retirement_object_identity(frozen)
    )


def test_r2_persistent_target_still_requires_exact_target_marker_and_size():
    candidate = _candidate(
        durability_basis=DURABILITY_R2_PERSISTENT_TARGET,
        archive_verified_asset_count=0,
        archive_sha256="",
        nas_bucket="",
        nas_key="",
    )
    source_head = {
        "ContentLength": 100,
        "ETag": '"source-etag"',
        "LastModified": candidate["source_last_modified"],
    }
    target_head = {
        "ContentLength": 100,
        "ETag": '"source-etag"',
        "Metadata": {"allbot-copy-plan-sha256": "c" * 64},
    }

    validate_retirement_object_heads(
        candidate,
        source_head=source_head,
        target_heads={candidate["targets"][0]["target_key"]: target_head},
        nas_head=None,
    )
    with pytest.raises(RuntimeError, match="target size"):
        validate_retirement_object_heads(
            candidate,
            source_head=source_head,
            target_heads={
                candidate["targets"][0]["target_key"]: dict(
                    target_head, ContentLength=99
                )
            },
            nas_head=None,
        )


def test_bulk_missing_source_etag_requires_exact_size_and_last_modified():
    candidate = _candidate(
        durability_basis=DURABILITY_R2_PERSISTENT_TARGET,
        archive_verified_asset_count=0,
        archive_sha256="",
        nas_bucket="",
        nas_key="",
        source_etag="",
        source_identity_policy=BULK_SOURCE_IDENTITY_POLICY,
    )
    source_head = {
        "ContentLength": 100,
        "ETag": '"live-etag-not-used-as-frozen-evidence"',
        "LastModified": candidate["source_last_modified"],
    }
    target_head = {
        "ContentLength": 100,
        "ETag": '"source-etag"',
        "Metadata": {"allbot-copy-plan-sha256": "c" * 64},
    }
    validate_retirement_object_heads(
        candidate,
        source_head=source_head,
        target_heads={candidate["targets"][0]["target_key"]: target_head},
        nas_head=None,
    )
    with pytest.raises(RuntimeError, match="last-modified"):
        validate_retirement_object_heads(
            candidate,
            source_head=dict(
                source_head,
                LastModified=datetime(2026, 1, 2, tzinfo=timezone.utc),
            ),
            target_heads={candidate["targets"][0]["target_key"]: target_head},
            nas_head=None,
        )
    with pytest.raises(RuntimeError, match="ETag evidence"):
        validate_retirement_object_heads(
            dict(candidate, source_identity_policy=""),
            source_head=source_head,
            target_heads={candidate["targets"][0]["target_key"]: target_head},
            nas_head=None,
        )


def test_nas_archive_remains_the_default_and_still_requires_readback():
    candidate = _candidate(durability_basis=DURABILITY_NAS_ARCHIVE)
    source_head = {
        "ContentLength": 100,
        "ETag": '"source-etag"',
        "LastModified": candidate["source_last_modified"],
    }
    target_head = {
        "ContentLength": 100,
        "ETag": '"source-etag"',
        "Metadata": {"allbot-copy-plan-sha256": "c" * 64},
    }
    with pytest.raises(RuntimeError, match="NAS archive object"):
        validate_retirement_object_heads(
            candidate,
            source_head=source_head,
            target_heads={candidate["targets"][0]["target_key"]: target_head},
            nas_head=None,
        )


def test_durability_config_is_fail_closed_and_runtime_identity_binds_mode():
    with pytest.raises(ValueError, match="required for nas-archive"):
        _durability_archive_config(DURABILITY_NAS_ARCHIVE, None)
    with pytest.raises(ValueError, match="not accepted"):
        _durability_archive_config(
            DURABILITY_R2_PERSISTENT_TARGET, "/secure/archive.json"
        )
    assert (
        _durability_archive_config(DURABILITY_R2_PERSISTENT_TARGET, None) is None
    )

    identity = _retirement_runtime_identity(
        artifact_digest="sha256:" + "f" * 64,
        r2_config={
            "target": {
                "endpoint": "https://r2.invalid",
                "bucket": "persistent",
            }
        },
        durability_basis=DURABILITY_R2_PERSISTENT_TARGET,
        archive_config=None,
    )
    assert identity["durability_basis"] == DURABILITY_R2_PERSISTENT_TARGET
    assert identity["retirement_execution_policy"] == {
        "scheduler": "request-phases-adaptive-v2",
        "head_concurrency": 128,
        "head_concurrency_levels": [128, 64, 32],
        "head_retry_attempts": 5,
        "head_lower_error_rate": 0.005,
        "head_raise_error_rate": 0.002,
        "head_systemic_error_rate": 0.1,
        "head_healthy_windows_to_raise": 2,
        "delete_concurrency": 8,
    }
    assert "nas_bucket" not in identity
    assert "nas_endpoint_sha256" not in identity

    manifest = {"runtime_identity": identity}
    _validate_retirement_execution_policy(
        manifest, Namespace(head_concurrency=128, delete_concurrency=8)
    )
    with pytest.raises(RuntimeError, match="execution policy"):
        _validate_retirement_execution_policy(
            manifest, Namespace(head_concurrency=32, delete_concurrency=8)
        )


def test_retirement_head_controller_persists_across_phases_and_batches():
    args = Namespace()
    controller = _retirement_head_controller(args, configured_concurrency=128)
    controller.observe(
        request_count=1000, transient_error_count=6, rate_limit_count=0
    )

    assert controller.current_concurrency == 64
    assert _retirement_head_controller(args, configured_concurrency=128) is controller
    with pytest.raises(RuntimeError, match="maximum changed"):
        _retirement_head_controller(args, configured_concurrency=64)


@pytest.mark.asyncio
async def test_r2_persistent_target_head_gate_never_requires_nas_client():
    candidate = _candidate(
        durability_basis=DURABILITY_R2_PERSISTENT_TARGET,
        archive_verified_asset_count=0,
        archive_sha256="",
        nas_bucket="",
        nas_key="",
    )

    class R2:
        def head_object(self, *, Bucket, Key):
            del Bucket
            if Key == candidate["source_key"]:
                return {
                    "ContentLength": 100,
                    "ETag": '"source-etag"',
                    "LastModified": candidate["source_last_modified"],
                }
            assert Key == candidate["targets"][0]["target_key"]
            return {
                "ContentLength": 100,
                "ETag": '"source-etag"',
                "Metadata": {"allbot-copy-plan-sha256": "c" * 64},
            }

    recovered = await _head_candidates(
        [candidate],
        r2_client=R2(),
        r2_bucket="persistent",
        nas_client=None,
        concurrency=1,
    )
    assert recovered == 0


@pytest.mark.asyncio
async def test_retirement_head_gate_uses_request_level_concurrency_above_delete_cap():
    candidates = [
        _candidate(
            source_key=f"private/source-{index}.png",
            durability_basis=DURABILITY_R2_PERSISTENT_TARGET,
            targets=[
                {
                    "target_key": f"task-results/task-{index}/primary.png",
                    "copy_plan_sha256": "c" * 64,
                    "target_etag": "source-etag",
                }
            ],
        )
        for index in range(128)
    ]

    class R2:
        def __init__(self):
            self.active = 0
            self.peak = 0
            self.lock = threading.Lock()
            self.release = threading.Event()

        def head_object(self, *, Bucket, Key):
            del Bucket
            with self.lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
                if self.peak >= 128:
                    self.release.set()
            assert self.release.wait(timeout=2)
            try:
                if Key.startswith("private/source-"):
                    return {
                        "ContentLength": 100,
                        "ETag": '"source-etag"',
                        "LastModified": candidates[0]["source_last_modified"],
                    }
                return {
                    "ContentLength": 100,
                    "ETag": '"source-etag"',
                    "Metadata": {"allbot-copy-plan-sha256": "c" * 64},
                }
            finally:
                with self.lock:
                    self.active -= 1

    r2 = R2()
    recovered = await _head_candidates(
        candidates,
        r2_client=r2,
        r2_bucket="persistent",
        nas_client=None,
        concurrency=128,
    )

    assert recovered == 0
    assert r2.peak == 128
    assert not any(
        thread.name.startswith("history-r2-retirement-head")
        for thread in threading.enumerate()
    )


@pytest.mark.asyncio
async def test_retirement_head_gate_retries_only_failures_and_lowers_on_error_rate():
    candidates = [
        _candidate(
            source_key=f"private/source-{index}.png",
            durability_basis=DURABILITY_R2_PERSISTENT_TARGET,
            targets=[
                {
                    "target_key": f"task-results/task-{index}/primary.png",
                    "copy_plan_sha256": "c" * 64,
                    "target_etag": "source-etag",
                }
            ],
        )
        for index in range(100)
    ]

    class R2:
        def __init__(self):
            self.attempts = {}
            self.lock = threading.Lock()

        def head_object(self, *, Bucket, Key):
            del Bucket
            with self.lock:
                attempt = self.attempts.get(Key, 0) + 1
                self.attempts[Key] = attempt
            if Key in {"private/source-0.png", "private/source-1.png"} and attempt == 1:
                raise ClientError(
                    {
                        "Error": {"Code": "InternalError"},
                        "ResponseMetadata": {"HTTPStatusCode": 500},
                    },
                    "HeadObject",
                )
            if Key.startswith("private/source-"):
                return {
                    "ContentLength": 100,
                    "ETag": '"source-etag"',
                    "LastModified": candidates[0]["source_last_modified"],
                }
            return {
                "ContentLength": 100,
                "ETag": '"source-etag"',
                "Metadata": {"allbot-copy-plan-sha256": "c" * 64},
            }

    sleeps = []

    async def no_sleep(delay):
        sleeps.append(delay)

    r2 = R2()
    controller = RetirementHeadConcurrencyController(initial_concurrency=128)
    recovered = await _head_candidates(
        candidates,
        r2_client=r2,
        r2_bucket="persistent",
        nas_client=None,
        concurrency=128,
        controller=controller,
        retry_sleep=no_sleep,
    )

    assert recovered == 0
    assert controller.current_concurrency == 64
    assert sum(r2.attempts.values()) == 202
    assert sorted(r2.attempts.values()).count(2) == 2
    assert sleeps and sleeps[0] >= 1
    assert not any(
        thread.name.startswith("history-r2-retirement-head")
        for thread in threading.enumerate()
    )


@pytest.mark.asyncio
async def test_retirement_head_gate_lowers_immediately_on_rate_limit():
    candidate = _candidate(durability_basis=DURABILITY_R2_PERSISTENT_TARGET)

    class R2:
        def __init__(self):
            self.attempts = {}

        def head_object(self, *, Bucket, Key):
            del Bucket
            attempt = self.attempts.get(Key, 0) + 1
            self.attempts[Key] = attempt
            if Key == candidate["source_key"] and attempt == 1:
                raise ClientError(
                    {
                        "Error": {"Code": "SlowDown"},
                        "ResponseMetadata": {"HTTPStatusCode": 429},
                    },
                    "HeadObject",
                )
            if Key == candidate["source_key"]:
                return {
                    "ContentLength": 100,
                    "ETag": '"source-etag"',
                    "LastModified": candidate["source_last_modified"],
                }
            return {
                "ContentLength": 100,
                "ETag": '"source-etag"',
                "Metadata": {"allbot-copy-plan-sha256": "c" * 64},
            }

    async def no_sleep(_delay):
        return None

    r2 = R2()
    controller = RetirementHeadConcurrencyController(initial_concurrency=128)
    recovered = await _head_candidates(
        [candidate],
        r2_client=r2,
        r2_bucket="persistent",
        nas_client=None,
        concurrency=128,
        controller=controller,
        retry_sleep=no_sleep,
    )

    assert recovered == 0
    assert controller.current_concurrency == 64
    assert sum(r2.attempts.values()) == 3


@pytest.mark.asyncio
async def test_retirement_head_gate_opens_circuit_and_releases_threads():
    candidates = [
        _candidate(
            source_key=f"private/source-{index}.png",
            durability_basis=DURABILITY_R2_PERSISTENT_TARGET,
            targets=[
                {
                    "target_key": f"task-results/task-{index}/primary.png",
                    "copy_plan_sha256": "c" * 64,
                    "target_etag": "source-etag",
                }
            ],
        )
        for index in range(100)
    ]

    class R2:
        def head_object(self, *, Bucket, Key):
            del Bucket
            if Key.startswith("private/source-") and int(Key.split("-")[-1][:-4]) < 20:
                raise ClientError(
                    {
                        "Error": {"Code": "InternalError"},
                        "ResponseMetadata": {"HTTPStatusCode": 500},
                    },
                    "HeadObject",
                )
            if Key.startswith("private/source-"):
                return {
                    "ContentLength": 100,
                    "ETag": '"source-etag"',
                    "LastModified": candidates[0]["source_last_modified"],
                }
            return {
                "ContentLength": 100,
                "ETag": '"source-etag"',
                "Metadata": {"allbot-copy-plan-sha256": "c" * 64},
            }

    with pytest.raises(RuntimeError, match="systemic retirement HEAD failure"):
        await _head_candidates(
            candidates,
            r2_client=R2(),
            r2_bucket="persistent",
            nas_client=None,
            concurrency=128,
            controller=RetirementHeadConcurrencyController(
                initial_concurrency=128
            ),
        )
    assert not any(
        thread.name.startswith("history-r2-retirement-head")
        for thread in threading.enumerate()
    )


def test_retirement_r2_connection_pool_covers_head_concurrency(monkeypatch):
    captured = {}

    def fake_client(*_args, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(
        "scripts.history_media_r2_retirement.boto3.client", fake_client
    )
    _s3_client(
        {
            "endpoint": "https://r2.invalid",
            "access_key": "test",
            "secret_key": "test",
        },
        max_connections=128,
    )

    assert captured["config"].max_pool_connections == 128


@pytest.mark.asyncio
async def test_retirement_delete_pool_stays_bounded_and_is_released():
    class R2:
        def __init__(self):
            self.active = 0
            self.peak = 0
            self.lock = threading.Lock()

        def delete_object(self, *, Bucket, Key):
            del Bucket, Key
            with self.lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
            try:
                time.sleep(0.02)
            finally:
                with self.lock:
                    self.active -= 1

    r2 = R2()
    await _delete_sources(
        [
            {"source_key": f"private/source-{index}.png"}
            for index in range(32)
        ],
        r2_client=r2,
        r2_bucket="persistent",
        concurrency=8,
    )

    assert r2.peak == 8
    assert not any(
        thread.name.startswith("history-r2-retirement-delete")
        for thread in threading.enumerate()
    )


def test_retirement_plan_is_object_deduplicated_and_does_not_leak_keys():
    objects = [
        _candidate(),
        _candidate(
            source_key="private/larger.mp4",
            byte_size=1000,
            targets=[
                {
                    "target_key": "task-results/task-2/primary.mp4",
                    "copy_plan_sha256": "d" * 64,
                    "target_etag": "source-etag",
                }
            ],
        ),
    ]
    manifest, frozen, batches = build_retirement_plan(
        run_id="11111111-1111-1111-1111-111111111111",
        parent_copy_plan_sha256="p" * 64,
        parent_switch_plan_sha256s=["s" * 64],
        objects=objects,
        report_sha256="r" * 64,
        runtime_identity={"artifact_digest": "sha256:" + "f" * 64},
        durability_basis=DURABILITY_NAS_ARCHIVE,
        batch_size=1,
    )

    assert manifest["object_count"] == 2
    assert manifest["total_bytes"] == 1100
    assert manifest["batch_count"] == 2
    assert frozen[0]["byte_size"] == 1000
    assert batches[0]["object_count"] == 1
    serialized = json.dumps(manifest)
    assert "private/" not in serialized
    assert "task-results/" not in serialized
    assert manifest["plan_sha256"]

    with pytest.raises(RuntimeError, match="duplicate old source"):
        build_retirement_plan(
            run_id=manifest["run_id"],
            parent_copy_plan_sha256="p" * 64,
            parent_switch_plan_sha256s=["s" * 64],
            objects=[objects[0], dict(objects[0])],
            report_sha256="r" * 64,
            runtime_identity={},
            durability_basis=DURABILITY_NAS_ARCHIVE,
        )


def test_bulk_retirement_plan_freezes_two_switch_ranges_under_one_token():
    first = _candidate(
        durability_basis=DURABILITY_R2_PERSISTENT_TARGET,
        archive_verified_asset_count=0,
        archive_sha256="",
        nas_bucket="",
        nas_key="",
        scope_asset_count=3,
        scope_switch_counts={"a" * 64: 3},
        retirement_disposition="eligible",
    )
    second = _candidate(
        source_key="private/second.mp4",
        byte_size=200,
        durability_basis=DURABILITY_R2_PERSISTENT_TARGET,
        archive_verified_asset_count=0,
        archive_sha256="",
        nas_bucket="",
        nas_key="",
        scope_asset_count=2,
        scope_switch_counts={"b" * 64: 2},
        retirement_disposition="deferred",
    )
    third = _candidate(
        source_key="private/third.png",
        byte_size=50,
        durability_basis=DURABILITY_R2_PERSISTENT_TARGET,
        archive_verified_asset_count=0,
        archive_sha256="",
        nas_bucket="",
        nas_key="",
        scope_asset_count=2,
        scope_switch_counts={"a" * 64: 1, "b" * 64: 1},
        retirement_disposition="retained_target",
    )

    manifest, frozen, batches = build_bulk_retirement_plan(
        run_id="11111111-1111-1111-1111-111111111111",
        parent_copy_plan_sha256s=["c" * 64, "d" * 64],
        switch_scope_counts={"a" * 64: 4, "b" * 64: 3},
        switch_scope_rowset_sha256s={"a" * 64: "e" * 64, "b" * 64: "f" * 64},
        asset_scope_sha256="1" * 64,
        objects=[first, second, third],
        runtime_identity={"artifact_digest": "sha256:" + "9" * 64},
        canary_size=1,
        batch_size=2,
    )

    assert manifest["schema"] == "allbot-history-media-r2-bulk-retirement-plan/v2"
    assert manifest["execution_mode"] == "bulk"
    assert manifest["asset_coordinate_count"] == 7
    assert manifest["asset_scope_algorithm"] == "history-r2-bulk-scope-merkle-v1"
    assert manifest["source_identity_policy"] == BULK_SOURCE_IDENTITY_POLICY
    assert manifest["object_count"] == 3
    assert manifest["canary_object_count"] == 1
    assert manifest["batch_count"] == 3
    assert manifest["eligible_object_count"] == 1
    assert manifest["deferred_object_count"] == 1
    assert manifest["retained_target_object_count"] == 1
    assert batches[0]["is_canary"] is True
    assert batches[0]["object_count"] == 1
    assert batches[0]["disposition"] == "eligible"
    assert batches[1]["disposition"] == "deferred"
    assert batches[1]["object_count"] == 1
    assert batches[2]["disposition"] == "retained_target"
    assert batches[2]["is_retained"] is True
    assert [item["retirement_disposition"] for item in frozen] == [
        "eligible",
        "deferred",
        "retained_target",
    ]
    assert manifest["eligible_asset_coordinate_count"] == 3
    assert manifest["deferred_asset_coordinate_count"] == 2
    assert manifest["retained_target_asset_coordinate_count"] == 2
    assert sum(item["scope_asset_count"] for item in frozen) == 7
    assert validate_delete_gate(
        expected_plan_sha256=manifest["plan_sha256"],
        supplied_plan_sha256=manifest["plan_sha256"],
        confirmation="DELETE_HISTORY_MEDIA_" + manifest["plan_sha256"],
    ) is None
    serialized = json.dumps(manifest)
    assert "private/" not in serialized
    assert "task-results/" not in serialized


def test_bulk_retirement_dispositions_are_frozen_and_fail_closed():
    base = _candidate(
        durability_basis=DURABILITY_R2_PERSISTENT_TARGET,
        archive_verified_asset_count=0,
        archive_sha256="",
        nas_bucket="",
        nas_key="",
        scope_asset_count=1,
        scope_switch_counts={"a" * 64: 1},
    )
    kwargs = {
        "run_id": "11111111-1111-1111-1111-111111111111",
        "parent_copy_plan_sha256s": ["c" * 64],
        "switch_scope_counts": {"a" * 64: 1},
        "switch_scope_rowset_sha256s": {"a" * 64: "e" * 64},
        "asset_scope_sha256": "1" * 64,
        "runtime_identity": {},
    }
    with pytest.raises(RuntimeError, match="disposition is invalid"):
        build_bulk_retirement_plan(
            **kwargs, objects=[dict(base, retirement_disposition="unknown")]
        )
    with pytest.raises(RuntimeError, match="no immediately eligible"):
        build_bulk_retirement_plan(
            **kwargs, objects=[dict(base, retirement_disposition="deferred")]
        )
    eligible_identity = _retirement_object_identity(
        dict(base, retirement_disposition="eligible")
    )
    retained_identity = _retirement_object_identity(
        dict(base, retirement_disposition="retained_target")
    )
    assert eligible_identity != retained_identity


def test_bulk_retirement_plan_rejects_scope_count_drift_and_duplicate_switches():
    candidate = _candidate(
        durability_basis=DURABILITY_R2_PERSISTENT_TARGET,
        archive_verified_asset_count=0,
        archive_sha256="",
        nas_bucket="",
        nas_key="",
        scope_asset_count=1,
        scope_switch_counts={"a" * 64: 1},
    )
    kwargs = {
        "run_id": "11111111-1111-1111-1111-111111111111",
        "parent_copy_plan_sha256s": ["c" * 64],
        "switch_scope_counts": {"a" * 64: 2},
        "switch_scope_rowset_sha256s": {"a" * 64: "e" * 64},
        "asset_scope_sha256": "1" * 64,
        "objects": [candidate],
        "runtime_identity": {},
    }
    with pytest.raises(RuntimeError, match="asset coordinate count"):
        build_bulk_retirement_plan(**kwargs)
    with pytest.raises(ValueError, match="unique Switch"):
        build_bulk_retirement_plan(
            **dict(kwargs, switch_plan_sha256s=["a" * 64, "a" * 64])
        )


def test_bulk_retirement_successor_preserves_completed_objects_and_conserves_scope():
    predecessor = {
        "schema": "allbot-history-media-r2-bulk-retirement-plan/v2",
        "execution_mode": "bulk",
        "durability_basis": DURABILITY_R2_PERSISTENT_TARGET,
        "run_id": "11111111-1111-1111-1111-111111111111",
        "parent_copy_plan_sha256s": ["c" * 64],
        "parent_switch_plan_sha256s": ["s" * 64],
        "switch_scopes": [
            {
                "switch_plan_sha256": "s" * 64,
                "asset_coordinate_count": 10,
                "rowset_sha256": "r" * 64,
            }
        ],
        "asset_coordinate_count": 10,
        "asset_scope_sha256": "a" * 64,
        "asset_scope_algorithm": "history-r2-bulk-scope-merkle-v1",
        "source_identity_policy": BULK_SOURCE_IDENTITY_POLICY,
        "object_count": 8,
        "total_bytes": 800,
        "batch_size": 1000,
        "plan_sha256": "p" * 64,
    }
    batches = [
        {
            "batch_no": 0,
            "is_canary": True,
            "disposition": "eligible",
            "is_retained": False,
            "object_count": 5,
            "asset_coordinate_count": 7,
            "total_bytes": 500,
            "rowset_sha256": "b" * 64,
        }
    ]

    manifest = build_bulk_retirement_successor_manifest(
        predecessor_manifest=predecessor,
        predecessor_plan_sha256="p" * 64,
        predecessor_completed_batches_sha256="d" * 64,
        predecessor_retained_object_count=3,
        predecessor_retained_asset_coordinate_count=3,
        remaining_object_count=5,
        remaining_asset_coordinate_count=7,
        remaining_total_bytes=500,
        remaining_rowset_sha256="e" * 64,
        batches=batches,
        disposition_summary={
            "eligible": {"object_count": 5, "asset_coordinate_count": 7}
        },
        runtime_identity={"artifact_digest": "sha256:" + "f" * 64},
    )

    assert manifest["schema"] == "allbot-history-media-r2-bulk-retirement-plan/v3"
    assert manifest["predecessor_plan_sha256"] == "p" * 64
    assert manifest["root_object_count"] == 8
    assert manifest["root_asset_coordinate_count"] == 10
    assert manifest["predecessor_retained_object_count"] == 3
    assert manifest["object_count"] == 5
    assert manifest["asset_coordinate_count"] == 7
    assert manifest["retained_target_object_count"] == 0
    assert manifest["plan_sha256"]

    with pytest.raises(RuntimeError, match="object conservation"):
        build_bulk_retirement_successor_manifest(
            predecessor_manifest=predecessor,
            predecessor_plan_sha256="p" * 64,
            predecessor_completed_batches_sha256="d" * 64,
            predecessor_retained_object_count=2,
            predecessor_retained_asset_coordinate_count=3,
            remaining_object_count=5,
            remaining_asset_coordinate_count=7,
            remaining_total_bytes=500,
            remaining_rowset_sha256="e" * 64,
            batches=batches,
            disposition_summary={
                "eligible": {"object_count": 5, "asset_coordinate_count": 7}
            },
            runtime_identity={},
        )


def test_bulk_switch_count_parser_is_exact_and_fail_closed():
    assert _expected_switch_counts(["a" * 64 + "=1828075"]) == {
        "a" * 64: 1828075
    }
    for invalid in ("a=1", "A" * 64 + "=1", "a" * 64 + "=0"):
        with pytest.raises(ValueError):
            _expected_switch_counts([invalid])
    with pytest.raises(ValueError, match="unique"):
        _expected_switch_counts(["a" * 64 + "=1", "a" * 64 + "=1"])


def test_delete_gate_is_distinct_from_copy_and_switch_tokens():
    plan = "a" * 64
    validate_delete_gate(
        expected_plan_sha256=plan,
        supplied_plan_sha256=plan,
        confirmation=f"DELETE_HISTORY_MEDIA_{plan}",
    )
    for wrong in (f"COPY_HISTORY_MEDIA_{plan}", f"SWITCH_HISTORY_MEDIA_{plan}"):
        with pytest.raises(ValueError, match="exact retirement plan"):
            validate_delete_gate(
                expected_plan_sha256=plan,
                supplied_plan_sha256=plan,
                confirmation=wrong,
            )


def test_retirement_head_validation_requires_source_target_marker_and_nas_sha():
    candidate = _candidate()
    source_head = {
        "ContentLength": 100,
        "ETag": '"source-etag"',
        "LastModified": candidate["source_last_modified"],
        "Metadata": {},
    }
    target_head = {
        "ContentLength": 100,
        "ETag": '"source-etag"',
        "Metadata": {"allbot-copy-plan-sha256": "c" * 64},
    }
    nas_head = {
        "ContentLength": 100,
        "Metadata": {"sha256": "a" * 64},
    }

    validate_retirement_object_heads(
        candidate,
        source_head=source_head,
        target_heads={candidate["targets"][0]["target_key"]: target_head},
        nas_head=nas_head,
    )

    bad_target = dict(target_head, Metadata={"allbot-copy-plan-sha256": "x" * 64})
    with pytest.raises(RuntimeError, match="target marker"):
        validate_retirement_object_heads(
            candidate,
            source_head=source_head,
            target_heads={candidate["targets"][0]["target_key"]: bad_target},
            nas_head=nas_head,
        )


def test_retirement_execute_surface_only_heads_and_deletes():
    import scripts.history_media_r2_retirement as module

    source = inspect.getsource(module._execute_delete)
    for forbidden in ("get_object", "list_objects", "copy_object"):
        assert forbidden not in source
    assert "_delete_sources" in source
    assert source.count("_head_candidates") == 2
    delete_source = inspect.getsource(module._delete_sources)
    assert "delete_object" in delete_source
    assert delete_source.count("delete_object") == 1
    delete_call = delete_source[delete_source.index("delete_object") :]
    assert 'Key=str(candidate["source_key"])' in delete_call[:400]
    assert "validate_delete_gate" in source
    assert "_retirement_has_blockers" in source
    assert "target_key" in inspect.getsource(module._head_candidates)
    blocker_source = RETIREMENT_BLOCKER_SQL
    assert "copy_required" in blocker_source
    assert "switch_completed_at" in blocker_source

    bulk_source = inspect.getsource(module._execute_bulk_delete)
    assert "_execute_delete" in bulk_source
    assert "_bulk_global_preflight" in bulk_source
    assert "while True" in bulk_source
    assert "confirm" not in bulk_source.replace("args.confirm", "")
    assert "systemctl" not in bulk_source
    assert "list_objects" not in bulk_source
    assert "delete_bucket" not in bulk_source

    planner_source = inspect.getsource(module._plan_bulk_delete)
    assert "_bulk_scope_fingerprint" in planner_source
    assert "_prepare_bulk_retirement_stage" in planner_source
    assert "_bulk_production_has_live_refs" in planner_source
    assert "_materialize_bulk_retirement_order" in planner_source
    assert planner_source.index("_bulk_production_has_live_refs") < planner_source.index(
        "_materialize_bulk_retirement_order"
    )
    assert "scope still has a live History reference" not in planner_source
    assert "retained_source_is_target" in planner_source
    assert "$3::integer" in planner_source
    for forbidden in ("get_object", "list_objects", "delete_object"):
        assert forbidden not in planner_source
    stage_source = inspect.getsource(module._prepare_bulk_retirement_stage)
    assert "bulk_retirement_blockers" in stage_source
    assert "retirement_disposition" in stage_source
    assert "retained_target" in stage_source
    assert "for candidate" not in stage_source
    live_ref_source = inspect.getsource(module._bulk_production_has_live_refs)
    assert "retirement_disposition='eligible'" in live_ref_source
    assert "source_key_sha256 bytea" in live_ref_source
    assert "create unique index" in live_ref_source
    assert "analyze bulk_retirement_source_keys" in live_ref_source
    assert "set local work_mem='256MB'" in live_ref_source
    assert "max_parallel_workers_per_gather=0" in live_ref_source
    assert "sha256(convert_to" in live_ref_source
    assert "source_key text" not in live_ref_source
    assert "bulk_retirement_live_source_hashes" in live_ref_source
    assert "update bulk_retirement_candidates" in live_ref_source
    assert "retirement_disposition='deferred'" in live_ref_source

    scope_source = inspect.getsource(module._bulk_scope_fingerprint)
    assert "10000" in scope_source
    assert "sha256" in scope_source
    assert ".cursor(" not in scope_source
    preflight_source = inspect.getsource(module._bulk_global_preflight)
    assert "_bulk_plan_coverage_counts" in preflight_source
    assert "batches_sha256" in preflight_source
    finalizer_source = inspect.getsource(module._finalize_bulk_delete)
    assert "retained_target_object_count" in finalizer_source
    assert "blocked_count" in finalizer_source

    successor_source = inspect.getsource(module._plan_bulk_delete_successor)
    assert "status='planned'" in successor_source
    assert "_completed_retirement_batch_proof" in successor_source
    assert "_bulk_predecessor_retained_counts" in successor_source
    assert "set status='paused'" in successor_source
    assert "_bulk_production_has_live_refs" not in successor_source
    assert "_live_reference_counts" in source
    assert "retirement_execution_policy" in inspect.getsource(
        module._retirement_runtime_identity
    )


@pytest.mark.asyncio
async def test_retirement_blocker_gate_is_one_bounded_set_query_for_1000_sources():
    class Ledger:
        def __init__(self):
            self.calls = []

        async def fetchval(self, query, *args, **kwargs):
            self.calls.append((query, args, kwargs))
            return True

    ledger = Ledger()
    objects = [
        {"source_name": "source", "source_key": f"old-{index}"}
        for index in range(1000)
    ]

    assert await _retirement_has_blockers(ledger, objects) is True
    assert len(ledger.calls) == 1
    query, args, kwargs = ledger.calls[0]
    assert query == RETIREMENT_BLOCKER_SQL
    assert len(args[0]) == 1000
    assert len(args[1]) == 1000
    assert kwargs["timeout"] == RETIREMENT_BLOCKER_TIMEOUT_SECONDS


def test_retirement_blocker_query_is_set_based_early_exit_and_has_indexes():
    normalized = " ".join(RETIREMENT_BLOCKER_SQL.lower().split())

    assert "selected as materialized" in normalized
    assert normalized.count("join analytics_history_media_r2_migrations") == 3
    assert "union all" in normalized
    assert "select exists" in normalized
    assert "limit 1" in normalized
    assert "count(*)" not in normalized
    assert "from selected s where exists" not in normalized

    index_sql = " ".join(statement.lower() for _, statement in RETIREMENT_BLOCKER_INDEX_DDL)
    assert "(source_name,source_key)" in index_sql.replace(" ", "")
    assert "status in ('copy_required','failed')" in index_sql
    assert "switch_completed_at is null" in index_sql
    assert "(target_key)" in index_sql.replace(" ", "")
    assert all("concurrently" in statement.lower() for _, statement in RETIREMENT_BLOCKER_INDEX_DDL)


@pytest.mark.asyncio
async def test_retirement_pause_reconnects_after_the_execution_connection_is_lost():
    class Connection:
        def __init__(self):
            self.executed = []
            self.closed = False

        async def execute(self, query, *args):
            self.executed.append((query, args))

        async def close(self):
            self.closed = True

    connection = Connection()
    attempts = 0

    async def connect(_name):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionError("transient tunnel loss")
        return connection

    delays = []

    async def delay(seconds):
        delays.append(seconds)

    await _mark_retirement_plan_paused(
        "a" * 64,
        connect_func=connect,
        sleep_func=delay,
        attempts=3,
    )

    assert attempts == 2
    assert delays == [1]
    assert connection.closed is True
    assert connection.executed[0][1] == ("a" * 64,)


@pytest.mark.asyncio
async def test_retirement_blocker_indexes_are_prepared_concurrently_and_verified():
    class Ledger:
        def __init__(self):
            self.executed = []

        async def execute(self, query, **kwargs):
            self.executed.append((query, kwargs))

        async def fetch(self, query, names):
            assert "idx.indisvalid" in query
            return [{"indexname": names[0]}, {"indexname": names[2]}]

    ledger = Ledger()
    await _ensure_retirement_blocker_indexes(ledger, timeout_seconds=900)

    assert len(ledger.executed) == 3
    assert all(call[1]["timeout"] == 900 for call in ledger.executed)
    assert await _missing_retirement_blocker_indexes(ledger) == (
        RETIREMENT_BLOCKER_INDEX_DDL[1][0],
    )


def test_retirement_report_is_read_only_and_plan_freeze_owns_schema_changes():
    import scripts.history_media_r2_retirement as module

    report_source = inspect.getsource(module._report)
    assert "RETIREMENT_DDL" not in report_source
    assert ".execute(" not in report_source
    assert "object_keys_redacted" in report_source


def test_retirement_tables_and_script_are_preserved_and_shipped():
    root = __import__("pathlib").Path(__file__).resolve().parents[2]
    shadow = (root / "scripts/run_local_analytics_shadow_pipeline.py").read_text()
    dockerfile = (root / "deploy/docker/Dockerfile.migration").read_text()

    for table in (
        "analytics_history_media_r2_retirement_plans",
        "analytics_history_media_r2_retirement_batches",
        "analytics_history_media_r2_retirement_objects",
    ):
        assert table in shadow
    assert "scripts/history_media_r2_retirement.py" in dockerfile
    assert "scripts/media_archive_worker.py" in dockerfile


def test_retirement_cli_and_local_ledger_tables_are_explicit():
    prepare = _parser().parse_args(
        ["prepare-delete-indexes", "--timeout-seconds", "900"]
    )
    report = _parser().parse_args(
        [
            "report",
            "--parent-copy-plan-sha256",
            "a" * 64,
            "--output",
            "/secure/report.json",
        ]
    )
    plan = _parser().parse_args(
        [
            "plan-delete",
            "--parent-copy-plan-sha256",
            "a" * 64,
            "--report",
            "/secure/report.json",
            "--history-id-file",
            "/secure/archive-canary.ids",
            "--config",
            "/secure/r2.json",
            "--artifact-digest",
            "sha256:" + "b" * 64,
            "--durability-basis",
            DURABILITY_R2_PERSISTENT_TARGET,
            "--output",
            "/secure/delete-plan.json",
        ]
    )
    execute = _parser().parse_args(
        [
            "execute-delete",
            "--plan-sha256",
            "a" * 64,
            "--confirm",
            "DELETE_HISTORY_MEDIA_" + "a" * 64,
            "--config",
            "/secure/r2.json",
            "--artifact-digest",
            "sha256:" + "b" * 64,
            "--durability-basis",
            DURABILITY_R2_PERSISTENT_TARGET,
        ]
    )
    bulk_plan = _parser().parse_args(
        [
            "plan-bulk-delete",
            "--switch-plan-sha256",
            "a" * 64,
            "--expected-switch-asset-count",
            "a" * 64 + "=1828075",
            "--switch-plan-sha256",
            "b" * 64,
            "--expected-switch-asset-count",
            "b" * 64 + "=796955",
            "--config",
            "/secure/r2.json",
            "--artifact-digest",
            "sha256:" + "b" * 64,
            "--output",
            "/secure/bulk-delete-plan.json",
        ]
    )
    bulk_execute = _parser().parse_args(
        [
            "execute-bulk-delete",
            "--plan-sha256",
            "a" * 64,
            "--confirm",
            "DELETE_HISTORY_MEDIA_" + "a" * 64,
            "--config",
            "/secure/r2.json",
            "--artifact-digest",
            "sha256:" + "b" * 64,
        ]
    )
    bulk_successor = _parser().parse_args(
        [
            "plan-bulk-delete-successor",
            "--predecessor-plan-sha256",
            "a" * 64,
            "--config",
            "/secure/r2.json",
            "--artifact-digest",
            "sha256:" + "b" * 64,
            "--output",
            "/secure/bulk-delete-successor.json",
        ]
    )

    assert report.command == "report"
    assert prepare.command == "prepare-delete-indexes"
    assert prepare.timeout_seconds == 900
    assert not hasattr(report, "confirm")
    assert plan.history_id_file == "/secure/archive-canary.ids"
    assert plan.archive_config is None
    assert plan.durability_basis == DURABILITY_R2_PERSISTENT_TARGET
    assert execute.archive_config is None
    assert execute.durability_basis == DURABILITY_R2_PERSISTENT_TARGET
    assert execute.head_concurrency == 128
    assert execute.delete_concurrency == 8
    assert bulk_plan.switch_plan_sha256 == ["a" * 64, "b" * 64]
    assert bulk_plan.expected_switch_asset_count == [
        "a" * 64 + "=1828075",
        "b" * 64 + "=796955",
    ]
    assert bulk_plan.canary_size == 100
    assert bulk_execute.command == "execute-bulk-delete"
    assert bulk_execute.confirm == "DELETE_HISTORY_MEDIA_" + "a" * 64
    assert bulk_execute.head_concurrency == 128
    assert bulk_execute.delete_concurrency == 8
    with pytest.raises(SystemExit):
        _parser().parse_args(
            [
                "execute-bulk-delete",
                "--plan-sha256",
                "a" * 64,
                "--confirm",
                "DELETE_HISTORY_MEDIA_" + "a" * 64,
                "--config",
                "/secure/r2.json",
                "--artifact-digest",
                "sha256:" + "b" * 64,
                "--head-concurrency",
                "129",
            ]
        )
    assert bulk_successor.predecessor_plan_sha256 == "a" * 64
    assert bulk_successor.canary_size == 100
    assert "analytics_history_media_r2_retirement_plans" in RETIREMENT_DDL
    assert "analytics_history_media_r2_retirement_objects" in RETIREMENT_DDL
    assert "analytics_history_media_r2_retirement_batches" in RETIREMENT_DDL
    assert "scope_asset_count" in RETIREMENT_DDL
    assert "asset_coordinate_count" in RETIREMENT_DDL
    assert "is_canary" in RETIREMENT_DDL
