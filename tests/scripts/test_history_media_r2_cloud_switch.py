from __future__ import annotations

import inspect
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ARTIFACT = "sha256:" + "a" * 64
PLAN = "b" * 64
PREDECESSOR = "c" * 64
ROUTE = "d" * 64
WORKER = "sgp1-control-history-switch"


def _ledger_row(index: int, *, selected: bool = True) -> dict[str, object]:
    return {
        "id": index,
        "history_id": 100 + index,
        "role": "output",
        "ordinal": 0,
        "original_ref": f"legacy-{index}.png",
        "target_key": f"task-results/backend-{index}/primary.png",
        "switch_plan_sha256": PLAN if selected else None,
        "switch_completed_at": None,
        "selected": selected,
    }


def _task(rows: list[dict[str, object]] | None = None) -> dict[str, object]:
    from scripts.history_media_r2_cloud_switch import build_switch_task_bundle

    rows = rows or [_ledger_row(1)]
    return build_switch_task_bundle(
        rows=rows,
        plan_sha256=PLAN,
        predecessor_plan_sha256=PREDECESSOR,
        artifact_digest=ARTIFACT,
        worker_id=WORKER,
        production_route_sha256=ROUTE,
        batch_no=7,
        batch_rowset_sha256="e" * 64,
        cas_state_sha256="f" * 64,
        task_id="11111111-1111-4111-8111-111111111111",
    )


def test_successor_manifest_conserves_predecessor_and_has_zero_overlap() -> None:
    from scripts.history_media_r2_cloud_switch import (
        build_cloud_switch_successor_manifest,
    )

    predecessor = {
        "plan_sha256": PREDECESSOR,
        "run_id": "11111111-1111-4111-8111-111111111111",
        "history_watermark": 999,
        "count": 3,
        "parent_copy_plan_sha256": "1" * 64,
        "copy_chain_plan_sha256s": ["1" * 64],
    }
    retained = [_ledger_row(1)]
    successor = [_ledger_row(2), _ledger_row(3)]
    successor[0]["byte_size"] = 20
    successor[1]["byte_size"] = 30
    batches = [
        {
            "batch_no": 0,
            "first_ledger_id": 2,
            "last_ledger_id": 3,
            "first_history_id": 102,
            "last_history_id": 103,
            "asset_count": 2,
            "history_count": 2,
            "rowset_sha256": "2" * 64,
            "cas_state_sha256": "3" * 64,
        }
    ]

    manifest = build_cloud_switch_successor_manifest(
        predecessor_manifest=predecessor,
        retained_rows=retained,
        successor_rows=successor,
        batches=batches,
        artifact_digest=ARTIFACT,
        worker_id=WORKER,
        production_route_sha256=ROUTE,
        cloud_switch_script_sha256="4" * 64,
    )

    assert manifest["retained_asset_count"] == 1
    assert manifest["count"] == 2
    assert manifest["conserved_asset_count"] == 3
    assert manifest["intersection_asset_count"] == 0
    assert manifest["predecessor_switch_plan_sha256"] == PREDECESSOR
    assert manifest["switch_execution"]["production_route_sha256"] == ROUTE

    with pytest.raises(RuntimeError, match="overlap"):
        build_cloud_switch_successor_manifest(
            predecessor_manifest=predecessor,
            retained_rows=retained,
            successor_rows=[retained[0], successor[0]],
            batches=batches,
            artifact_digest=ARTIFACT,
            worker_id=WORKER,
            production_route_sha256=ROUTE,
            cloud_switch_script_sha256="4" * 64,
        )


def test_switch_task_and_receipt_bind_all_execution_identity() -> None:
    from scripts.history_media_r2_cloud_switch import (
        build_switch_receipt,
        validate_switch_receipt,
        validate_switch_task_gate,
    )

    task = _task()
    validate_switch_task_gate(
        task,
        plan_sha256=PLAN,
        confirm=f"SWITCH_HISTORY_MEDIA_{PLAN}",
        artifact_digest=ARTIFACT,
        worker_id=WORKER,
        production_route_sha256=ROUTE,
    )
    for override in (
        {"plan_sha256": "0" * 64},
        {"confirm": "SWITCH_HISTORY_MEDIA_" + "0" * 64},
        {"artifact_digest": "sha256:" + "0" * 64},
        {"worker_id": "other-worker"},
        {"production_route_sha256": "0" * 64},
    ):
        arguments = {
            "plan_sha256": PLAN,
            "confirm": f"SWITCH_HISTORY_MEDIA_{PLAN}",
            "artifact_digest": ARTIFACT,
            "worker_id": WORKER,
            "production_route_sha256": ROUTE,
            **override,
        }
        with pytest.raises(ValueError):
            validate_switch_task_gate(task, **arguments)

    expired = _task()
    expired["lease_expires_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    ).isoformat()
    with pytest.raises(ValueError, match="lease expired"):
        validate_switch_task_gate(
            expired,
            plan_sha256=PLAN,
            confirm=f"SWITCH_HISTORY_MEDIA_{PLAN}",
            artifact_digest=ARTIFACT,
            worker_id=WORKER,
            production_route_sha256=ROUTE,
        )
    receipt = build_switch_receipt(
        task,
        histories_updated=1,
        post_state_sha256="9" * 64,
    )
    validate_switch_receipt(task, receipt)

    for field, changed in (
        ("plan_sha256", "0" * 64),
        ("artifact_digest", "sha256:" + "0" * 64),
        ("worker_id", "other-worker"),
        ("production_route_sha256", "0" * 64),
        ("batch_rowset_sha256", "0" * 64),
        ("cas_state_sha256", "0" * 64),
    ):
        altered = json.loads(json.dumps(receipt))
        altered[field] = changed
        with pytest.raises(ValueError, match="identity"):
            validate_switch_receipt(task, altered)


@pytest.mark.asyncio
async def test_cloud_batch_allows_idempotent_selected_targets_and_updates_once() -> (
    None
):
    from scripts.history_media_r2_cloud_switch import (
        apply_switch_task_to_production,
        switch_task_cas_sha256,
    )

    row = _ledger_row(1)
    task = _task([row])
    original = str(row["original_ref"])
    target = str(row["target_key"])

    class Transaction:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    class Production:
        def __init__(self, value: str) -> None:
            self.value = value
            self.updates = 0

        def transaction(self):
            return Transaction()

        async def execute(self, query, *args):
            if query.startswith("set local"):
                return "SET"
            assert "update history" in query.lower()
            self.value = args[2]
            self.updates += 1
            return "UPDATE 1"

        async def fetch(self, _query, _history_ids):
            return [
                {
                    "id": 101,
                    "input_file": None,
                    "output_file": self.value,
                    "extra_outputs": {},
                }
            ]

    production = Production(original)
    task["cas_state_sha256"] = switch_task_cas_sha256(
        task,
        [
            {
                "id": 101,
                "input_file": None,
                "output_file": original,
                "extra_outputs": {},
            }
        ],
    )
    result = await apply_switch_task_to_production(production, task)
    assert result["histories_updated"] == 1
    assert production.value == target

    result = await apply_switch_task_to_production(production, task)
    assert result["histories_updated"] == 0
    assert production.updates == 1


def test_cloud_worker_connects_only_production_and_cli_separates_trust_domains() -> (
    None
):
    import scripts.history_media_r2_cloud_switch as module

    worker_source = inspect.getsource(module._run_switch_task)
    assert '"PRODUCTION_DATABASE_URL"' in worker_source
    assert "LOCAL_ANALYTICS_DATABASE_URL" not in worker_source

    parser = module._parser()
    planner = parser.parse_args(
        [
            "plan-successor",
            "--predecessor-plan-sha256",
            PREDECESSOR,
            "--artifact-digest",
            ARTIFACT,
            "--worker-id",
            WORKER,
            "--production-route-sha256",
            ROUTE,
            "--output",
            "/secure/plan.json",
        ]
    )
    exporter = parser.parse_args(
        [
            "export-task",
            "--plan-sha256",
            PLAN,
            "--confirm",
            f"SWITCH_HISTORY_MEDIA_{PLAN}",
            "--artifact-digest",
            ARTIFACT,
            "--worker-id",
            WORKER,
            "--production-route-sha256",
            ROUTE,
            "--signing-key-file",
            "/secure/key",
            "--output",
            "/secure/task.json",
        ]
    )
    worker = parser.parse_args(
        [
            "run-task",
            "--task",
            "/secure/task.json",
            "--confirm",
            f"SWITCH_HISTORY_MEDIA_{PLAN}",
            "--artifact-digest",
            ARTIFACT,
            "--worker-id",
            WORKER,
            "--production-route-sha256",
            ROUTE,
            "--signing-key-file",
            "/secure/key",
            "--receipt-output",
            "/secure/receipt.json",
        ]
    )
    importer = parser.parse_args(
        [
            "import-receipt",
            "--task",
            "/secure/task.json",
            "--receipt",
            "/secure/receipt.json",
            "--plan-sha256",
            PLAN,
            "--confirm",
            f"SWITCH_HISTORY_MEDIA_{PLAN}",
            "--artifact-digest",
            ARTIFACT,
            "--worker-id",
            WORKER,
            "--production-route-sha256",
            ROUTE,
            "--signing-key-file",
            "/secure/key",
        ]
    )

    assert planner.command == "plan-successor"
    assert exporter.command == "export-task"
    assert worker.command == "run-task"
    assert importer.command == "import-receipt"


def test_cloud_switch_artifact_and_low_cardinality_task_schema() -> None:
    from scripts.history_media_r2_cloud_switch import (
        CLOUD_SWITCH_TASK_DDL,
        production_route_sha256_from_dsn,
    )

    ddl = CLOUD_SWITCH_TASK_DDL.lower()
    assert "analytics_history_media_r2_cloud_switch_tasks" in ddl
    assert "ledger_ids bigint[]" in ddl
    assert "lease_expires_at" in ddl
    assert "receipt_sha256" in ddl
    assert "unique(plan_sha256,batch_no)" not in ddl

    root = Path(__file__).resolve().parents[2]
    dockerfile = (root / "deploy/docker/Dockerfile.migration").read_text()
    assert "scripts/history_media_r2_cloud_switch.py" in dockerfile

    first = production_route_sha256_from_dsn(
        "postgresql://first:secret@prod-db:5432/allbot?ssl=require"
    )
    same_route = production_route_sha256_from_dsn(
        "postgresql://other:different@prod-db:5432/allbot?ssl=require"
    )
    other_route = production_route_sha256_from_dsn(
        "postgresql://first:secret@other-db:5432/allbot?ssl=require"
    )
    assert first == same_route
    assert first != other_route
    assert "secret" not in first


@pytest.mark.asyncio
async def test_successor_planner_prefetches_multiple_cas_batches_per_round_trip() -> (
    None
):
    from scripts.history_media_r2_cloud_switch import build_successor_switch_batches

    rows = []
    histories = []
    for index in range(1, 13):
        row = _ledger_row(index)
        row.update(
            {
                "source_name": "r2-user-data-prod",
                "source_key": row["original_ref"],
                "source_last_modified": None,
                "source_etag": f"etag-{index}",
                "source_sha256": None,
                "target_sha256": None,
                "byte_size": index,
                "status": "copied_verified",
                "history_manifest_sha256": "8" * 64,
            }
        )
        rows.append(row)
        histories.append(
            {
                "id": 100 + index,
                "input_file": None,
                "output_file": row["original_ref"],
                "extra_outputs": {},
            }
        )

    class Production:
        def __init__(self) -> None:
            self.fetch_calls = 0
            self.queries = []

        async def fetch(self, query, first_history_id, last_history_id):
            self.fetch_calls += 1
            self.queries.append(query)
            return [
                row
                for row in histories
                if first_history_id <= row["id"] <= last_history_id
            ]

    class Ledger:
        async def fetch(self, _query, _run_id, history_ids):
            selected = set(history_ids)
            return [row for row in rows if row["history_id"] in selected]

    production = Production()
    batches = await build_successor_switch_batches(
        production,
        Ledger(),
        run_id="11111111-1111-4111-8111-111111111111",
        successor_rows=rows,
        history_batch_size=2,
        prefetch_history_count=6,
    )

    assert len(batches) == 6
    assert production.fetch_calls == 2
    assert all("h.id between $1 and $2" in query for query in production.queries)
    assert all("unnest" not in query.lower() for query in production.queries)
    assert all(
        "id=any" not in query.replace(" ", "").lower() for query in production.queries
    )
    assert [batch["history_count"] for batch in batches] == [2] * 6
    assert all(len(batch["cas_state_sha256"]) == 64 for batch in batches)
