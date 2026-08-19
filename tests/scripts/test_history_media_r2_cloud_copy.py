from __future__ import annotations

import hashlib
import inspect
import json
import stat
from datetime import datetime, timezone
from pathlib import Path

import pytest
from botocore.exceptions import ClientError


ARTIFACT = "sha256:" + "a" * 64
PLAN = "b" * 64
WORKER = "sgp1-control-history-r2"


def _row(index: int = 1) -> dict[str, object]:
    return {
        "id": index,
        "history_id": 100 + index,
        "role": "output",
        "ordinal": 0,
        "original_ref": f"legacy-{index}.png",
        "target_key": f"task-results/backend-{index}/primary.png",
        "source_name": "r2-user-data-prod",
        "source_key": f"legacy-{index}.png",
        "source_last_modified": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "source_etag": f"etag-{index}",
        "source_sha256": None,
        "target_sha256": None,
        "byte_size": 100 + index,
        "status": "copy_required",
        "history_manifest_sha256": "c" * 64,
        "copy_plan_sha256": PLAN,
    }


def test_signed_task_bundle_rejects_any_payload_change(tmp_path: Path) -> None:
    from scripts.history_media_r2_cloud_copy import (
        build_task_bundle,
        read_signed_document,
        write_signed_document,
    )

    key = b"k" * 32
    bundle = build_task_bundle(
        operation="head_probe",
        rows=[_row()],
        plan_sha256=PLAN,
        artifact_digest=ARTIFACT,
        worker_id=WORKER,
        runtime_identity={"r2_transport": {"mode": "direct"}},
    )
    path = tmp_path / "bundle.json"
    write_signed_document(path, bundle, key=key)

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert read_signed_document(path, key=key)["payload"] == bundle

    changed = json.loads(path.read_text())
    changed["payload"]["rows"][0]["byte_size"] += 1
    path.write_text(json.dumps(changed))
    path.chmod(0o600)
    with pytest.raises(ValueError, match="signature"):
        read_signed_document(path, key=key)


def test_cloud_execution_identity_is_frozen_and_local_copy_rejects_it() -> None:
    from scripts.history_media_r2_migration import (
        _copy_execution,
        _runtime_identity,
        validate_local_copy_execution,
    )

    config = {
        "target": {"endpoint": "https://target.example"},
        "sources": [
            {
                "name": "r2-user-data-prod",
                "endpoint": "https://target.example",
            }
        ],
        "r2_transport": {"mode": "direct"},
        "copy_execution": {
            "mode": "cloud_receipt",
            "worker_id": WORKER,
            "protocol": "history-r2-cloud-copy/v1",
        },
    }

    identity = _runtime_identity(artifact_digest=ARTIFACT, config=config)
    assert identity["copy_execution"] == {
        "mode": "cloud_receipt",
        "protocol": "history-r2-cloud-copy/v1",
        "worker_id": WORKER,
    }
    assert _copy_execution(config) == identity["copy_execution"]
    with pytest.raises(RuntimeError, match="cloud receipt"):
        validate_local_copy_execution(config)


def test_head_probe_worker_performs_only_head_and_returns_sanitized_metrics() -> None:
    from scripts.history_media_r2_cloud_copy import run_head_probe

    calls: list[tuple[str, str]] = []

    class Client:
        def head_object(self, *, Bucket, Key):
            calls.append((Bucket, Key))
            return {
                "ContentLength": 101,
                "ETag": '"etag-1"',
                "LastModified": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "Metadata": {},
            }

        def __getattr__(self, name: str):
            raise AssertionError(f"forbidden operation: {name}")

    result = run_head_probe([_row()], client=Client(), concurrency=2)

    assert len(calls) == 2
    assert result["operation"] == "HeadObject"
    assert result["assets"] == 1
    assert result["requests"] == 2
    assert result["target_existing"] == 1
    serialized = json.dumps(result)
    assert "legacy-1.png" not in serialized
    assert "task-results/" not in serialized


def test_head_probe_accepts_expected_missing_targets() -> None:
    from scripts.history_media_r2_cloud_copy import run_head_probe

    class Client:
        def head_object(self, *, Bucket, Key):
            if Key.startswith("task-results/"):
                raise ClientError(
                    {"Error": {"Code": "NoSuchKey", "Message": "missing"}},
                    "HeadObject",
                )
            return {
                "ContentLength": 101,
                "ETag": '"etag-1"',
                "LastModified": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "Metadata": {},
            }

    result = run_head_probe([_row()], client=Client(), concurrency=1)

    assert result["target_missing"] == 1
    assert result["target_existing"] == 0


def test_copy_worker_uses_marker_bound_server_side_copy_and_checkpoints() -> None:
    from scripts.history_media_r2_cloud_copy import run_copy_task

    persisted: list[dict[str, object]] = []

    def copy_one(_client, **kwargs):
        assert kwargs["copy_plan_sha256"] == PLAN
        return {
            "outcome": {"etag": "target-etag", "multipart": False},
            "error": None,
            "elapsed_ms": 12.0,
            "attempt_count": 1,
            "request_events": [{"kind": "ok"}],
        }

    result = run_copy_task(
        [_row()],
        client=object(),
        plan_sha256=PLAN,
        concurrency=1,
        copy_one=copy_one,
        checkpoint=lambda payload: persisted.append(payload),
    )

    assert result["outcome_counts"] == {"copied_verified": 1}
    assert result["results"] == [
        {
            "ledger_ids": [1],
            "outcome": "copied_verified",
            "target_etag": "target-etag",
        }
    ]
    assert persisted[-1]["results"] == result["results"]


def test_transient_exhaustion_stays_retryable_but_fatal_failure_isolated() -> None:
    from scripts.history_media_r2_cloud_copy import run_copy_task
    from scripts.history_media_r2_migration import R2CopyOperationError

    calls = 0

    def copy_one(_client, **_kwargs):
        nonlocal calls
        calls += 1
        error = (
            R2CopyOperationError("copy_object", TimeoutError("timeout"))
            if calls == 1
            else R2CopyOperationError("copy_object", ValueError("bad request"))
        )
        return {
            "outcome": None,
            "error": error,
            "elapsed_ms": 1.0,
            "attempt_count": 6,
            "request_events": [{"kind": "timeout" if calls == 1 else "fatal"}],
        }

    result = run_copy_task(
        [_row(1), _row(2)],
        client=object(),
        plan_sha256=PLAN,
        concurrency=1,
        copy_one=copy_one,
    )

    assert result["outcome_counts"] == {"fatal": 1, "retryable": 1}
    assert [item["outcome"] for item in result["results"]] == [
        "retryable",
        "fatal",
    ]
    assert "legacy-" not in json.dumps(result)


def test_copy_task_gate_rejects_wrong_plan_confirm_artifact_or_worker() -> None:
    from scripts.history_media_r2_cloud_copy import validate_copy_task_gate

    bundle = build = {
        "operation": "copy_object",
        "plan_sha256": PLAN,
        "artifact_digest": ARTIFACT,
        "worker_id": WORKER,
    }
    validate_copy_task_gate(
        build,
        plan_sha256=PLAN,
        confirm=f"COPY_HISTORY_MEDIA_{PLAN}",
        artifact_digest=ARTIFACT,
        worker_id=WORKER,
    )
    for override in (
        {"plan_sha256": "d" * 64},
        {"confirm": "COPY_HISTORY_MEDIA_" + "e" * 64},
        {"artifact_digest": "sha256:" + "f" * 64},
        {"worker_id": "other-worker"},
    ):
        kwargs = {
            "plan_sha256": PLAN,
            "confirm": f"COPY_HISTORY_MEDIA_{PLAN}",
            "artifact_digest": ARTIFACT,
            "worker_id": WORKER,
            **override,
        }
        with pytest.raises(ValueError):
            validate_copy_task_gate(bundle, **kwargs)


def test_receipt_binding_and_row_coverage_fail_closed() -> None:
    from scripts.history_media_r2_cloud_copy import (
        build_copy_receipt,
        build_task_bundle,
        validate_copy_receipt,
    )

    bundle = build_task_bundle(
        operation="copy_object",
        rows=[_row(1), _row(2)],
        plan_sha256=PLAN,
        artifact_digest=ARTIFACT,
        worker_id=WORKER,
        runtime_identity={"copy_execution": {"mode": "cloud_receipt"}},
        task_id="11111111-1111-4111-8111-111111111111",
    )
    receipt = build_copy_receipt(
        bundle,
        {
            "results": [
                {
                    "ledger_ids": [1],
                    "outcome": "copied_verified",
                    "target_etag": "one",
                },
                {"ledger_ids": [2], "outcome": "retryable", "error_kind": "timeout"},
            ],
            "outcome_counts": {"copied_verified": 1, "retryable": 1},
            "request_kinds": {"ok": 1, "timeout": 1},
            "latency_ms": {"count": 2, "p50": 1, "p95": 2, "max": 2},
        },
    )
    validate_copy_receipt(bundle, receipt)

    changed = json.loads(json.dumps(receipt))
    changed["results"].pop()
    with pytest.raises(ValueError, match="coverage"):
        validate_copy_receipt(bundle, changed)
    changed = json.loads(json.dumps(receipt))
    changed["artifact_digest"] = "sha256:" + "d" * 64
    with pytest.raises(ValueError, match="identity"):
        validate_copy_receipt(bundle, changed)


def test_cli_separates_local_coordinator_from_cloud_worker_commands() -> None:
    from scripts.history_media_r2_cloud_copy import _parser

    parser = _parser()
    export = parser.parse_args(
        [
            "export-copy-task",
            "--plan-sha256",
            PLAN,
            "--confirm",
            f"COPY_HISTORY_MEDIA_{PLAN}",
            "--config",
            "/secure/config.json",
            "--artifact-digest",
            ARTIFACT,
            "--worker-id",
            WORKER,
            "--signing-key-file",
            "/secure/key",
            "--output",
            "/secure/task.json",
        ]
    )
    worker = parser.parse_args(
        [
            "run-copy-task",
            "--task",
            "/secure/task.json",
            "--confirm",
            f"COPY_HISTORY_MEDIA_{PLAN}",
            "--config",
            "/secure/config.json",
            "--artifact-digest",
            ARTIFACT,
            "--worker-id",
            WORKER,
            "--signing-key-file",
            "/secure/key",
            "--receipt-output",
            "/secure/receipt.json",
        ]
    )
    importer = parser.parse_args(
        [
            "import-copy-receipt",
            "--task",
            "/secure/task.json",
            "--receipt",
            "/secure/receipt.json",
            "--plan-sha256",
            PLAN,
            "--confirm",
            f"COPY_HISTORY_MEDIA_{PLAN}",
            "--artifact-digest",
            ARTIFACT,
            "--worker-id",
            WORKER,
            "--signing-key-file",
            "/secure/key",
        ]
    )

    assert export.command == "export-copy-task"
    assert worker.command == "run-copy-task"
    assert importer.command == "import-copy-receipt"


def test_cloud_task_schema_is_low_cardinality_and_lease_bound() -> None:
    from scripts.history_media_r2_cloud_copy import CLOUD_TASK_DDL

    ddl = CLOUD_TASK_DDL.lower()
    assert "analytics_history_media_r2_cloud_copy_tasks" in ddl
    assert "lease_expires_at" in ddl
    assert "bundle_sha256" in ddl
    assert "receipt_sha256" in ddl
    assert "ledger_ids bigint[]" in ddl
    assert "analytics_history_media_r2_cloud_copy_plan_sessions" in ddl
    assert "preflight_rowset_sha256" in ddl


def test_cloud_export_runs_global_preflight_once_per_frozen_session() -> None:
    import scripts.history_media_r2_cloud_copy as module

    source = inspect.getsource(module._export_copy_task)
    assert "analytics_history_media_r2_cloud_copy_plan_sessions" in source
    assert "_validate_copy_plan_preflight" in source
    assert "preflight_rowset_sha256" in source


def test_signed_partial_checkpoint_can_commit_completed_subset() -> None:
    from scripts.history_media_r2_cloud_copy import (
        _checkpoint_receipt,
        build_task_bundle,
        validate_copy_receipt,
    )

    bundle = build_task_bundle(
        operation="copy_object",
        rows=[_row(1), _row(2)],
        plan_sha256=PLAN,
        artifact_digest=ARTIFACT,
        worker_id=WORKER,
        runtime_identity={"copy_execution": {"mode": "cloud_receipt"}},
    )
    checkpoint = _checkpoint_receipt(
        bundle,
        {
            "results": [
                {
                    "ledger_ids": [1],
                    "outcome": "copied_verified",
                    "target_etag": "one",
                }
            ]
        },
    )

    validate_copy_receipt(bundle, checkpoint)
    assert checkpoint["complete"] is False


def test_cloud_copy_worker_disables_hidden_sdk_retries() -> None:
    import scripts.history_media_r2_cloud_copy as module

    source = inspect.getsource(module._run_copy_task)
    assert "external_retry_lane=True" in source


def test_cloud_copy_script_has_no_get_list_delete_or_history_database() -> None:
    import scripts.history_media_r2_cloud_copy as module

    source = inspect.getsource(module)
    for forbidden in (
        ".get_object(",
        ".list_objects",
        ".delete_object(",
        "PRODUCTION_DATABASE_URL",
        "update history",
    ):
        assert forbidden not in source.lower()


def test_database_migration_artifact_contains_cloud_copy_worker() -> None:
    root = Path(__file__).resolve().parents[2]
    dockerfile = (root / "deploy/docker/Dockerfile.migration").read_text()

    assert "scripts/history_media_r2_cloud_copy.py" in dockerfile
