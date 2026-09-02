import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from scripts import r2_temp_cleanup as cleanup
from scripts.r2_temp_cleanup_cloud_coordinator import (
    CloudCleanupCoordinator,
    file_sha256,
)


def _inventory(path: Path, keys: list[str]) -> None:
    connection = sqlite3.connect(path)
    connection.execute(
        "create table objects(key text primary key,size integer not null,"
        "etag text not null,last_modified text not null) without rowid"
    )
    connection.executemany(
        "insert into objects values(?,?,?,?)",
        [(key, 10, "etag", "2026-08-01T00:00:00Z") for key in keys],
    )
    connection.commit()
    connection.close()
    path.chmod(0o600)


def test_database_migration_artifact_contains_cloud_cleanup_coordinator():
    root = Path(__file__).resolve().parents[2]
    dockerfile = (root / "deploy/docker/Dockerfile.migration").read_text()

    assert "scripts/r2_temp_cleanup_cloud_coordinator.py" in dockerfile


@pytest.mark.asyncio
async def test_delete_started_receipt_resumes_absent_and_present_objects(monkeypatch):
    objects = [
        {
            "key": "already-deleted",
            "durable_key": "durable-a",
            "byte_size": 10,
            "etag": "etag",
            "last_modified": "2026-08-01T00:00:00Z",
            "sha256": "same",
        },
        {
            "key": "still-present",
            "durable_key": "durable-b",
            "byte_size": 10,
            "etag": "etag",
            "last_modified": "2026-08-01T00:00:00Z",
            "sha256": "same",
        },
    ]
    plan = cleanup.seal_plan({
        "mode": "dry-run",
        "bucket": "user-data-prod",
        "objects": objects,
        "inventory": {"sha256": "inventory"},
    })
    receipt = {
        "mode": "execute",
        "status": "delete_started",
        "bucket": "user-data-prod",
        "objects": objects,
        "inventory": {"sha256": "inventory"},
    }

    async def no_history(_keys):
        return set()

    async def no_active(_keys):
        return set()

    async def no_business(_keys):
        return {}

    monkeypatch.setattr(cleanup, "_history_references", no_history)
    monkeypatch.setattr(cleanup, "_active_task_references", no_active)
    monkeypatch.setattr(cleanup, "_business_references", no_business)
    monkeypatch.setattr(
        cleanup,
        "_deleted_object_is_absent",
        lambda _client, _bucket, key: key == "already-deleted",
    )
    monkeypatch.setattr(
        cleanup, "_sha256_object", lambda _client, _bucket, _key: "same"
    )
    deleted = []

    async def delete_present(_client, _bucket, selected, *, concurrency):
        assert concurrency == 8
        deleted.extend(item["key"] for item in selected)
        return len(selected)

    monkeypatch.setattr(cleanup, "_delete_and_verify_candidates", delete_present)

    recovered = await cleanup.resume_delete_started(
        client=object(),
        plan=plan,
        receipt=receipt,
        concurrency=8,
    )

    assert deleted == ["still-present"]
    assert recovered["status"] == "completed"
    assert recovered["post_delete_verified_count"] == 2
    assert recovered["recovery"]["absent_before_recovery"] == 1
    assert recovered["recovery"]["present_before_recovery"] == 1


@pytest.mark.asyncio
async def test_delete_started_recovery_fails_closed_on_new_reference(monkeypatch):
    item = {
        "key": "source",
        "durable_key": "durable",
        "byte_size": 10,
        "etag": "etag",
        "last_modified": "2026-08-01T00:00:00Z",
        "sha256": "same",
    }
    plan = cleanup.seal_plan({
        "mode": "dry-run",
        "bucket": "user-data-prod",
        "objects": [item],
        "inventory": {"sha256": "inventory"},
    })
    receipt = {
        "status": "delete_started",
        "bucket": "user-data-prod",
        "objects": [item],
        "inventory": {"sha256": "inventory"},
    }

    async def referenced(_keys):
        return {"source"}

    async def no_active(_keys):
        return set()

    async def no_business(_keys):
        return {}

    monkeypatch.setattr(cleanup, "_history_references", referenced)
    monkeypatch.setattr(cleanup, "_active_task_references", no_active)
    monkeypatch.setattr(cleanup, "_business_references", no_business)

    with pytest.raises(RuntimeError, match="references appeared"):
        await cleanup.resume_delete_started(
            client=object(), plan=plan, receipt=receipt, concurrency=8
        )


@pytest.mark.asyncio
async def test_pending_probe_drift_defers_only_failed_keys_and_releases_frontier(
    tmp_path,
):
    state_root = tmp_path / "state"
    state_root.mkdir(mode=0o700)
    working = state_root / "working-inventory.sqlite3"
    _inventory(working, ["drifted", "still-safe"])
    plan = {
        "mode": "dry-run",
        "bucket": "user-data-prod",
        "objects": [
            {"key": "drifted", "durable_key": "durable-a"},
            {"key": "still-safe", "durable_key": "durable-b"},
        ],
        "plan_sha256": "plan-82",
    }
    plan_path = state_root / "plan-000082-10000.json"
    receipt_path = state_root / "execute-000082-10000.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    plan_path.chmod(0o600)
    state = {
        "schema": "allbot-r2-temp-cleanup-cloud-chain/v1",
        "working_inventory": str(working),
        "current_inventory_sha256": file_sha256(working),
        "next_sequence": 82,
        "pending": {
            "sequence": 82,
            "stage": 10000,
            "plan": str(plan_path),
            "plan_sha256": "plan-82",
            "receipt": str(receipt_path),
            "inventory_sha256_before": file_sha256(working),
        },
        "completed": [],
        "deferred": [],
        "current_pass": {
            "number": 1,
            "deleted_count": 10,
            "deleted_bytes": 100,
            "deferred_count": 0,
        },
        "finished": False,
    }
    (state_root / "chain-state.json").write_text(json.dumps(state), encoding="utf-8")
    (state_root / "chain-state.json").chmod(0o600)

    async def run_cleanup(args):
        assert args.execute is True
        receipt = {
            "mode": "execute",
            "status": "probe_failed",
            "approved_plan_sha256": "plan-82",
            "probe_failures": [{"key": "drifted", "error": "ClientError"}],
            "objects": [],
            "delete_count": 0,
        }
        Path(args.output).write_text(json.dumps(receipt), encoding="utf-8")
        Path(args.output).chmod(0o600)
        return receipt

    coordinator = CloudCleanupCoordinator(
        state_root=state_root,
        authorization_path=tmp_path / "authorization.json",
        cleanup_run_func=run_cleanup,
    )

    await coordinator._reconcile_pending(state)

    updated = json.loads((state_root / "chain-state.json").read_text())
    assert updated["pending"] is None
    assert updated["next_sequence"] == 83
    assert updated["completed"] == []
    assert updated["current_pass"]["deferred_count"] == 1
    assert updated["deferred"][-1]["reason"] == "execute_probe_failed"
    connection = sqlite3.connect(working)
    try:
        assert connection.execute("select key from objects order by key").fetchall() == [
            ("still-safe",)
        ]
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_plan_probe_drift_executes_verified_objects_and_defers_only_failure(
    tmp_path,
):
    state_root = tmp_path / "state"
    state_root.mkdir(mode=0o700)
    working = state_root / "working-inventory.sqlite3"
    _inventory(working, ["plan-drifted", "still-safe"])
    state = {
        "schema": "allbot-r2-temp-cleanup-cloud-chain/v1",
        "working_inventory": str(working),
        "current_inventory_sha256": file_sha256(working),
        "next_sequence": 94,
        "pending": None,
        "completed": [],
        "deferred": [],
        "current_pass": {
            "number": 1,
            "deleted_count": 10,
            "deleted_bytes": 100,
            "deferred_count": 0,
        },
        "finished": False,
    }

    async def run_cleanup(args):
        if not args.execute:
            plan = {
                "mode": "dry-run",
                "bucket": "user-data-prod",
                "cutoff": "2026-08-01T00:00:00Z",
                "candidate_count": 2,
                "delete_count": 1,
                "delete_bytes": 10,
                "probe_failures": [
                    {"key": "plan-drifted", "error": "ClientError"}
                ],
                "objects": [
                    {"key": "still-safe", "durable_key": "durable-b"}
                ],
                "plan_sha256": "plan-94",
            }
            Path(args.output).write_text(json.dumps(plan), encoding="utf-8")
            Path(args.output).chmod(0o600)
            return plan
        plan = json.loads(Path(args.approved_plan).read_text(encoding="utf-8"))
        receipt = {
            **plan,
            "mode": "execute",
            "status": "completed",
            "approved_plan_sha256": args.plan_sha256,
            "probe_failures": [],
            "post_delete_verified_count": 1,
        }
        Path(args.output).write_text(json.dumps(receipt), encoding="utf-8")
        Path(args.output).chmod(0o600)
        return receipt

    coordinator = CloudCleanupCoordinator(
        state_root=state_root,
        authorization_path=tmp_path / "authorization.json",
        cleanup_run_func=run_cleanup,
    )

    await coordinator.run_one_step(state)

    updated = json.loads((state_root / "chain-state.json").read_text())
    assert updated["pending"] is None
    assert updated["next_sequence"] == 95
    assert updated["current_pass"]["deleted_count"] == 11
    assert updated["current_pass"]["deferred_count"] == 1
    assert updated["completed"][-1]["deleted_count"] == 1
    assert updated["deferred"][-1]["reason"] == "plan_probe_failed"
    assert updated["deferred"][-1]["deferred_count"] == 1
    connection = sqlite3.connect(working)
    try:
        assert connection.execute("select key from objects").fetchall() == []
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_plan_and_execute_probe_drift_defer_both_failures_without_delete(
    tmp_path,
):
    state_root = tmp_path / "state"
    state_root.mkdir(mode=0o700)
    working = state_root / "working-inventory.sqlite3"
    _inventory(working, ["execute-drifted", "plan-drifted", "still-safe"])
    state = {
        "schema": "allbot-r2-temp-cleanup-cloud-chain/v1",
        "working_inventory": str(working),
        "current_inventory_sha256": file_sha256(working),
        "next_sequence": 94,
        "pending": None,
        "completed": [],
        "deferred": [],
        "current_pass": {
            "number": 1,
            "deleted_count": 10,
            "deleted_bytes": 100,
            "deferred_count": 0,
        },
        "finished": False,
    }

    async def run_cleanup(args):
        if not args.execute:
            plan = {
                "mode": "dry-run",
                "bucket": "user-data-prod",
                "cutoff": "2026-08-01T00:00:00Z",
                "candidate_count": 3,
                "delete_count": 2,
                "delete_bytes": 20,
                "probe_failures": [
                    {"key": "plan-drifted", "error": "ClientError"}
                ],
                "objects": [
                    {"key": "execute-drifted", "durable_key": "durable-a"},
                    {"key": "still-safe", "durable_key": "durable-b"},
                ],
                "plan_sha256": "plan-94",
            }
            Path(args.output).write_text(json.dumps(plan), encoding="utf-8")
            Path(args.output).chmod(0o600)
            return plan
        receipt = {
            "mode": "execute",
            "status": "probe_failed",
            "approved_plan_sha256": args.plan_sha256,
            "probe_failures": [
                {"key": "execute-drifted", "error": "ClientError"}
            ],
            "objects": [],
            "delete_count": 0,
        }
        Path(args.output).write_text(json.dumps(receipt), encoding="utf-8")
        Path(args.output).chmod(0o600)
        return receipt

    coordinator = CloudCleanupCoordinator(
        state_root=state_root,
        authorization_path=tmp_path / "authorization.json",
        cleanup_run_func=run_cleanup,
    )

    await coordinator.run_one_step(state)

    updated = json.loads((state_root / "chain-state.json").read_text())
    assert updated["pending"] is None
    assert updated["next_sequence"] == 95
    assert updated["completed"] == []
    assert updated["current_pass"]["deleted_count"] == 10
    assert updated["current_pass"]["deferred_count"] == 2
    assert updated["deferred"][-1]["reason"] == "plan_and_execute_probe_failed"
    assert updated["deferred"][-1]["plan_probe_failed_count"] == 1
    assert updated["deferred"][-1]["execute_probe_failed_count"] == 1
    connection = sqlite3.connect(working)
    try:
        assert connection.execute("select key from objects order by key").fetchall() == [
            ("still-safe",)
        ]
    finally:
        connection.close()


def test_cloud_coordinator_advances_canaries_and_repeats_fresh_pass(tmp_path):
    state_root = tmp_path / "state"
    state_root.mkdir(mode=0o700)
    refreshes = []
    plans = []

    def refresh(state_dir: Path):
        refreshes.append(len(refreshes) + 1)
        path = state_dir / f"inventory-{len(refreshes)}.sqlite3"
        _inventory(path, ["source", "durable"])
        return {
            "path": str(path),
            "sha256": file_sha256(path),
            "object_count": 2,
            "bytes": 20,
        }

    async def run_cleanup(args):
        if not args.execute:
            plans.append(args.limit)
            connection = sqlite3.connect(args.inventory)
            source_exists = bool(
                connection.execute(
                    "select 1 from objects where key='source'"
                ).fetchone()
            )
            connection.close()
            delete_count = 1 if len(refreshes) == 1 and source_exists else 0
            report = {
                "mode": "dry-run",
                "candidate_count": delete_count,
                "verified_count": delete_count,
                "delete_count": delete_count,
                "delete_bytes": delete_count * 10,
                "referenced_blocked_count": 0,
                "probe_failures": [],
                "objects": (
                    [
                        {
                            "key": "source",
                            "durable_key": "durable",
                            "byte_size": 10,
                            "etag": "etag",
                            "last_modified": "2026-08-01T00:00:00Z",
                            "sha256": "same",
                        }
                    ]
                    if delete_count
                    else []
                ),
                "inventory": {"sha256": file_sha256(Path(args.inventory))},
                "plan_sha256": f"plan-{len(plans)}",
            }
            Path(args.output).write_text(json.dumps(report), encoding="utf-8")
            Path(args.output).chmod(0o600)
            return report
        plan = json.loads(Path(args.approved_plan).read_text(encoding="utf-8"))
        receipt = {
            **plan,
            "mode": "execute",
            "status": "completed",
            "approved_plan_sha256": args.plan_sha256,
            "post_delete_verified_count": len(plan["objects"]),
        }
        Path(args.output).write_text(json.dumps(receipt), encoding="utf-8")
        Path(args.output).chmod(0o600)
        return receipt

    coordinator = CloudCleanupCoordinator(
        state_root=state_root,
        authorization_path=tmp_path / "authorization.json",
        refresh_inventory_func=refresh,
        cleanup_run_func=run_cleanup,
    )
    (tmp_path / "authorization.json").write_text(
        json.dumps(
            {
                "bucket": "user-data-prod",
                "delegates_exact_child_phase_tokens": True,
                "scope_expansion_allowed": False,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "authorization.json").chmod(0o600)

    asyncio.run(coordinator.run_until_complete(max_steps=10))

    state = json.loads((state_root / "chain-state.json").read_text())
    assert state["finished"] is True
    assert state["completed"][0]["stage"] == 100
    assert refreshes == [1, 2]
    assert plans == [100, 1000, 1000]
    assert state["passes"][0]["deleted_count"] == 1
    assert state["passes"][1]["deleted_count"] == 0
