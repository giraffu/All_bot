from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys

from botocore.exceptions import ClientError
import pytest

from scripts.history_media_r2_migration import (
    AssetIdentity,
    MIGRATION_DDL,
    SourceFactCache,
    StreamingJsonArraySha256,
    build_candidate_keys,
    build_copy_plan,
    build_standard_target,
    classify_target_status,
    classify_reference,
    group_copy_candidates,
    evaluate_missing_round,
    hash_body,
    history_assets_from_record,
    normalize_asyncpg_dsn,
    _add_r2_custom_headers,
    _parser,
    _persist_copy_success,
    _process_r2_custom_arguments,
    _probe_r2_rows,
    _probe_target_rows,
    replace_asset_reference,
    server_side_copy_r2_object,
    validate_copy_gate,
    validate_switch_gate,
    validate_resume_identity,
)


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
    assert _parser().parse_args([*base, "--copy-concurrency", "16"]).copy_concurrency == 16
    with pytest.raises(SystemExit):
        _parser().parse_args([*base, "--copy-concurrency", "0"])
    with pytest.raises(SystemExit):
        _parser().parse_args([*base, "--copy-concurrency", "33"])


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
    forbidden = ("_read_s3_sha", "_open_source_body", "NamedTemporaryFile", "upload_fileobj")
    assert not any(name in source for name in forbidden)
    assert "server_side_copy_r2_object" in source


def test_seed_uses_one_bulk_copy_stage_per_history_batch():
    import inspect
    import scripts.history_media_r2_migration as module

    source = inspect.getsource(module._seed)
    assert "copy_records_to_table" in source
    assert "BACKEND_BATCH_SQL" in source
    assert "for asset in assets" in source
    assert "await conn.fetchrow(BACKEND" not in source
    assert "select id from analytics_media_asset_catalog where history_id=$1" not in source


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
    script = Path(__file__).resolve().parents[2] / "scripts/history_media_r2_migration.py"
    result = subprocess.run(
        [sys.executable, str(script), "probe", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--receipt-only" in result.stdout


def test_partial_copy_plan_requires_an_explicit_flag_and_records_scope():
    import inspect
    import scripts.history_media_r2_migration as module

    source = inspect.getsource(module._create_plan)
    assert "args.allow_incomplete" in source
    assert '"pending_at_freeze"' in source
    assert '"run_status_at_freeze"' in source
    assert '"partial_scope"' in source

    script = Path(__file__).resolve().parents[2] / "scripts/history_media_r2_migration.py"
    result = subprocess.run(
        [sys.executable, str(script), "plan-copy", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--allow-incomplete" in result.stdout


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
            conn, rows, target_client=client, concurrency=8  # type: ignore[arg-type]
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
            conn, rows, r2_client=client, concurrency=8  # type: ignore[arg-type]
        )
        == 0
    )
    assert len(client.head_calls) == 4
    assert client.get_calls == []
    assert any("copy_required" in query for _kind, query, _params in conn.calls)
    assert any("source_etag" in query for _kind, query, _params in conn.calls)
    assert any("r2_checked_at" in query for _kind, query, _params in conn.calls)
    assert not any("source_missing" in query for _kind, query, _params in conn.calls)


def test_migration_ledger_is_independent_and_bound_to_history_watermark():
    assert "analytics_history_media_migration_runs" in MIGRATION_DDL
    assert "analytics_history_media_r2_migrations" in MIGRATION_DDL
    assert "history_watermark" in MIGRATION_DDL
    assert "unique (run_id, history_id, role, ordinal)" in MIGRATION_DDL
    assert "copy_plan_sha256" in MIGRATION_DDL
    assert "switch_plan_sha256" in MIGRATION_DDL
    assert "r2_checked_at" in MIGRATION_DDL


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
