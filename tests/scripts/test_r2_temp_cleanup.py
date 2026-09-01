import asyncio
import inspect
import sqlite3
import threading
import time
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import r2_temp_cleanup as cleanup_module

from scripts.r2_temp_cleanup import (
    Candidate,
    _eligible_candidates,
    _delete_and_verify_candidates,
    _verify_candidates,
    _matching_refs,
    select_duplicate_candidates,
    validate_delete_gate,
    _history_references,
    _active_task_references,
    _apply_delete_byte_cap,
    load_approved_plan,
    seal_plan,
)


def test_database_migration_artifact_contains_temp_cleanup_worker():
    root = Path(__file__).resolve().parents[2]
    dockerfile = (root / "deploy/docker/Dockerfile.migration").read_text()

    assert "scripts/r2_temp_cleanup.py" in dockerfile
    assert "scripts/refresh_r2_temp_cleanup_inventory.py" in dockerfile


def _inventory():
    db = sqlite3.connect(":memory:")
    db.execute(
        "create table objects(key text primary key,size integer,etag text,last_modified text)"
    )
    db.executemany(
        "insert into objects values(?,?,?,?)",
        [
            ("12345678-1234-1234-1234-123456789abc__raw.png", 10, "same", "2026-08-01T00:00:00Z"),
            ("42/output_images/raw.png", 10, "same", "2026-08-01T00:01:00Z"),
            ("only-root.png", 9, "unique", "2026-08-01T00:00:00Z"),
            ("temps/template.png", 10, "same", "2026-08-01T00:00:00Z"),
            ("young.png", 10, "young", "2026-08-06T12:00:00Z"),
            ("task-results/t/primary.png", 10, "young", "2026-08-06T12:00:00Z"),
        ],
    )
    return db


def test_selects_only_old_root_objects_with_a_durable_signature_twin():
    rows = select_duplicate_candidates(
        _inventory(), cutoff="2026-08-05T00:00:00Z", limit=100
    )
    assert [(row.key, row.durable_key) for row in rows] == [
        ("12345678-1234-1234-1234-123456789abc__raw.png", "42/output_images/raw.png")
    ]


def test_candidate_selection_materializes_an_indexed_durable_signature_lookup():
    db = _inventory()

    select_duplicate_candidates(db, cutoff="2026-08-05T00:00:00Z", limit=100)

    definition = db.execute(
        "select sql from sqlite_temp_master where name='cleanup_durable_twins'"
    ).fetchone()[0]
    assert "primarykey(size,etag)" in definition.replace(" ", "").lower()


def test_active_task_reference_matching_walks_nested_registry_payloads():
    key = "12345678-1234-1234-1234-123456789abc__raw.png"
    assert _matching_refs(
        {"task": {"saved_input_images": [f"user-data-prod/{key}"]}},
        {key, "unrelated.png"},
    ) == {key}


@pytest.mark.asyncio
async def test_active_task_reference_gate_uses_strict_atomic_query(monkeypatch):
    key = "12345678-1234-1234-1234-123456789abc__raw.png"

    async def snapshot(*, redis_url, redis_prefix, keys, socket_timeout):
        assert redis_url == "redis://runtime"
        assert redis_prefix == "prod:"
        assert keys == [key, "unrelated.png"]
        assert socket_timeout == 60
        return {key}

    monkeypatch.setenv("REDIS_URL", "redis://runtime")
    monkeypatch.setenv("REDIS_PREFIX", "prod:")

    assert await _active_task_references(
        [key, "unrelated.png"], lookup_func=snapshot
    ) == {key}


def test_cloud_cleanup_runtime_does_not_import_global_config_dependencies():
    runtime_source = "\n".join(
        (
            inspect.getsource(_history_references),
            inspect.getsource(_active_task_references),
        )
    )

    assert "src.database.core" not in runtime_source
    assert "TaskRegistry" not in runtime_source


def test_business_references_block_an_otherwise_verified_duplicate():
    candidate = Candidate(
        key="12345678-1234-1234-1234-123456789abc__raw.png",
        durable_key="task-results/task/primary.png",
        byte_size=10,
        etag="same",
        last_modified="2026-08-01T00:00:00Z",
    )
    eligible, blocked = _eligible_candidates(
        [candidate],
        set(),
        set(),
        {candidate.key},
    )
    assert eligible == []
    assert blocked == {candidate.key}


def test_history_reference_query_scans_each_history_role_once():
    source = inspect.getsource(_history_references)
    assert "regexp_replace" in source
    assert "like '%/'||candidate.key" not in source


def test_temp_delete_gate_is_bucket_and_confirmation_scoped():
    validate_delete_gate(
        bucket="user-data-prod",
        enabled=True,
        confirmation="DELETE_VERIFIED_TEMP_R2_user-data-prod",
    )
    with pytest.raises(ValueError):
        validate_delete_gate(
            bucket="user-data",
            enabled=True,
            confirmation="DELETE_VERIFIED_TEMP_R2_user-data",
        )


def test_sha_verification_uses_bounded_parallel_reads(monkeypatch):
    active = 0
    maximum = 0
    lock = threading.Lock()

    def fake_sha256(_client, _bucket, _key):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return "same"

    monkeypatch.setattr("scripts.r2_temp_cleanup._sha256_object", fake_sha256)
    candidates = [
        Candidate(
            key=f"source-{index}",
            durable_key=f"durable-{index}",
            byte_size=10,
            etag="same",
            last_modified="2026-08-01T00:00:00Z",
        )
        for index in range(8)
    ]

    verified, failures = asyncio.run(
        _verify_candidates(object(), "user-data-prod", candidates, concurrency=3)
    )

    assert len(verified) == 8
    assert failures == []
    assert 1 < maximum <= 3


def test_post_delete_verification_is_bounded_and_ordered_per_object(monkeypatch):
    active = 0
    maximum = 0
    events = []
    lock = threading.Lock()

    class Client:
        def delete_object(self, *, Bucket, Key):
            nonlocal active, maximum
            assert Bucket == "user-data-prod"
            with lock:
                active += 1
                maximum = max(maximum, active)
                events.append((Key, "delete"))
            time.sleep(0.02)
            with lock:
                active -= 1

    def fake_absent(_client, _bucket, key):
        with lock:
            events.append((key, "absent"))
        return True

    def fake_sha(_client, _bucket, key):
        with lock:
            events.append((key.removeprefix("durable-"), "durable_sha"))
        return "same"

    monkeypatch.setattr(
        "scripts.r2_temp_cleanup._deleted_object_is_absent", fake_absent
    )
    monkeypatch.setattr("scripts.r2_temp_cleanup._sha256_object", fake_sha)
    objects = [
        {
            "key": f"source-{index}",
            "durable_key": f"durable-source-{index}",
            "sha256": "same",
        }
        for index in range(8)
    ]

    verified = asyncio.run(
        _delete_and_verify_candidates(
            Client(), "user-data-prod", objects, concurrency=3
        )
    )

    assert verified == 8
    assert 1 < maximum <= 3
    for item in objects:
        key = item["key"]
        assert [event for event_key, event in events if event_key == key] == [
            "delete",
            "absent",
            "durable_sha",
        ]


def test_daily_delete_byte_cap_stops_before_crossing_limit():
    verified = [
        {"key": "one", "byte_size": 30},
        {"key": "two", "byte_size": 25},
        {"key": "three", "byte_size": 10},
    ]

    selected, blocked = _apply_delete_byte_cap(verified, max_bytes=50)

    assert [item["key"] for item in selected] == ["one"]
    assert [item["key"] for item in blocked] == ["two", "three"]
    assert sum(item["byte_size"] for item in selected) == 30


@pytest.mark.asyncio
async def test_execute_probe_drift_writes_zero_delete_receipt_instead_of_exiting(
    tmp_path, monkeypatch
):
    inventory = tmp_path / "inventory.sqlite3"
    connection = sqlite3.connect(inventory)
    connection.execute(
        "create table objects(key text primary key,size integer,etag text,last_modified text)"
    )
    connection.executemany(
        "insert into objects values(?,?,?,?)",
        [
            ("source", 10, "same", "2026-08-01T00:00:00Z"),
            ("task-results/durable", 10, "same", "2026-08-01T00:00:00Z"),
        ],
    )
    connection.commit()
    connection.close()
    inventory.chmod(0o600)
    plan = seal_plan(
        {
            "mode": "dry-run",
            "bucket": "user-data-prod",
            "cutoff": "2026-08-05T00:00:00Z",
            "objects": [
                {
                    "key": "source",
                    "durable_key": "task-results/durable",
                    "byte_size": 10,
                    "etag": "same",
                    "last_modified": "2026-08-01T00:00:00Z",
                    "sha256": "before",
                }
            ],
            "inventory": {"sha256": cleanup_module._file_sha256(inventory)},
        }
    )
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    output = tmp_path / "receipt.json"

    async def no_references(_keys):
        return set()

    async def no_business_references(_keys):
        return {}

    async def drifted(*_args, **_kwargs):
        return [], [{"key": "source", "error": "ClientError"}]

    monkeypatch.setattr(cleanup_module, "_history_references", no_references)
    monkeypatch.setattr(cleanup_module, "_active_task_references", no_references)
    monkeypatch.setattr(
        cleanup_module, "_business_references", no_business_references
    )
    monkeypatch.setattr(cleanup_module, "_r2_client", lambda: object())
    monkeypatch.setattr(cleanup_module, "_verify_candidates", drifted)
    monkeypatch.setattr(
        cleanup_module,
        "_delete_and_verify_candidates",
        lambda *_args, **_kwargs: pytest.fail("probe drift must not enter delete"),
    )
    monkeypatch.setenv("R2_TEMP_CLEANUP_ENABLED", "true")
    args = SimpleNamespace(
        inventory=str(inventory),
        output=str(output),
        bucket="user-data-prod",
        limit=10000,
        min_age_hours=24,
        verification_concurrency=8,
        max_delete_bytes=50 * 1024**3,
        execute=True,
        approved_plan=str(plan_path),
        plan_sha256=plan["plan_sha256"],
        confirm=f"DELETE_VERIFIED_TEMP_R2_user-data-prod:{plan['plan_sha256']}",
    )

    receipt = await cleanup_module.run(args)

    assert receipt["status"] == "probe_failed"
    assert receipt["delete_count"] == 0
    assert receipt["objects"] == []
    assert receipt["probe_failures"] == [
        {"key": "source", "error": "ClientError"}
    ]
    assert json.loads(output.read_text())["status"] == "probe_failed"


def test_cleanup_plan_is_sealed_and_tampering_is_rejected(tmp_path):
    plan = seal_plan({"mode": "dry-run", "objects": [{"key": "safe"}]})
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")

    assert load_approved_plan(str(path), plan["plan_sha256"])["objects"] == [
        {"key": "safe"}
    ]
    plan["objects"][0]["key"] = "changed"
    path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(SystemExit, match="modified"):
        load_approved_plan(str(path), plan["plan_sha256"])


def test_execute_confirmation_is_bound_to_plan_sha():
    validate_delete_gate(
        bucket="user-data-prod",
        enabled=True,
        confirmation="DELETE_VERIFIED_TEMP_R2_user-data-prod:abc",
        plan_sha256="abc",
    )
    with pytest.raises(ValueError):
        validate_delete_gate(
            bucket="user-data-prod",
            enabled=True,
            confirmation="DELETE_VERIFIED_TEMP_R2_user-data-prod:def",
            plan_sha256="abc",
        )
