from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.history_media_r2_migration import (
    AssetIdentity,
    MIGRATION_DDL,
    SourceFactCache,
    build_candidate_keys,
    build_copy_plan,
    build_standard_target,
    classify_target_status,
    classify_reference,
    evaluate_missing_round,
    hash_body,
    history_assets_from_record,
    replace_asset_reference,
    validate_copy_gate,
    validate_switch_gate,
    validate_resume_identity,
)


def test_migration_ledger_is_independent_and_bound_to_history_watermark():
    assert "analytics_history_media_migration_runs" in MIGRATION_DDL
    assert "analytics_history_media_r2_migrations" in MIGRATION_DDL
    assert "history_watermark" in MIGRATION_DDL
    assert "unique (run_id, history_id, role, ordinal)" in MIGRATION_DDL
    assert "copy_plan_sha256" in MIGRATION_DDL
    assert "switch_plan_sha256" in MIGRATION_DDL


def test_standard_targets_require_explicit_dual_ids():
    input_asset = AssetIdentity(1, "input", 2, "7/input_images/a.JPEG")
    output_asset = AssetIdentity(1, "output", 0, "7/output_images/result.png")
    extra_asset = AssetIdentity(1, "extra:mask preview", 3, "mask.webp")

    assert build_standard_target(
        input_asset, registry_task_id="registry-1", backend_task_id=None
    ) == "task-inputs/registry-1/2.jpeg"
    assert build_standard_target(
        output_asset, registry_task_id="registry-1", backend_task_id="backend-1"
    ) == "task-results/backend-1/primary.png"
    assert build_standard_target(
        extra_asset, registry_task_id="registry-1", backend_task_id="backend-1"
    ) == "task-results/backend-1/extras/extra-mask-preview-3.webp"
    assert build_standard_target(
        output_asset, registry_task_id="registry-1", backend_task_id=None
    ) is None
    assert build_standard_target(
        input_asset, registry_task_id=None, backend_task_id="backend-1"
    ) is None


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
    assert classify_target_status(
        source_sha256="a" * 64, target_sha256="a" * 64
    ) == ("target_verified", None)
    assert classify_target_status(
        source_sha256="a" * 64, target_sha256="b" * 64
    ) == ("target_conflict", "TARGET_SHA256_CONFLICT")


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
    assert cache.lookup(
        source="r2-user-data-prod",
        key="a.png",
        byte_size=3,
        last_modified=last_modified,
    ) == "a" * 64
    assert cache.lookup(
        source="r2-user-data-prod",
        key="a.png",
        byte_size=4,
        last_modified=last_modified,
    ) is None
    assert cache.lookup(
        source="r2-user-data-prod",
        key="a.png",
        byte_size=3,
        last_modified=last_modified + timedelta(seconds=1),
    ) is None


def test_missing_confirmation_requires_all_not_found_twice_and_24_hours():
    now = datetime(2026, 8, 9, tzinfo=timezone.utc)
    assert evaluate_missing_round(
        statuses=("not_found", "not_found"),
        previous_rounds=0,
        first_missing_at=None,
        now=now,
    ) == ("provisional_missing", 1, now)
    assert evaluate_missing_round(
        statuses=("not_found", "not_found"),
        previous_rounds=1,
        first_missing_at=now - timedelta(hours=24),
        now=now,
    )[0] == "confirmed_lost"
    assert evaluate_missing_round(
        statuses=("not_found", "source_offline"),
        previous_rounds=1,
        first_missing_at=now - timedelta(days=2),
        now=now,
    )[0] == "source_offline"


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
    script = Path(__file__).resolve().parents[2] / "scripts/history_media_r2_migration.py"
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    for command in (
        "seed",
        "probe",
        "plan-copy",
        "execute-copy",
        "plan-switch",
        "execute-switch",
        "report",
    ):
        assert command in result.stdout
