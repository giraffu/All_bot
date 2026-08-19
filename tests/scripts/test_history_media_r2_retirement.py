from __future__ import annotations

import inspect
import json
from datetime import datetime, timezone

import pytest

from scripts.history_media_r2_retirement import (
    DURABILITY_NAS_ARCHIVE,
    DURABILITY_R2_PERSISTENT_TARGET,
    RETIREMENT_DDL,
    _durability_archive_config,
    _head_candidates,
    _parser,
    _retirement_runtime_identity,
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
    assert "nas_bucket" not in identity
    assert "nas_endpoint_sha256" not in identity


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
    assert "delete_object" in source
    assert "validate_delete_gate" in source
    assert "copy_required" in source
    assert "switch_completed_at" in source
    assert "target_key" in source


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

    assert report.command == "report"
    assert not hasattr(report, "confirm")
    assert plan.history_id_file == "/secure/archive-canary.ids"
    assert plan.archive_config is None
    assert plan.durability_basis == DURABILITY_R2_PERSISTENT_TARGET
    assert execute.archive_config is None
    assert execute.durability_basis == DURABILITY_R2_PERSISTENT_TARGET
    assert execute.delete_concurrency <= 8
    assert "analytics_history_media_r2_retirement_plans" in RETIREMENT_DDL
    assert "analytics_history_media_r2_retirement_objects" in RETIREMENT_DDL
    assert "analytics_history_media_r2_retirement_batches" in RETIREMENT_DDL
