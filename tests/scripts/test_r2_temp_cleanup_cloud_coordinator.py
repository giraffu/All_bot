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
