import pytest
import json
from io import BytesIO
import threading
import time

from scripts.r2_template_submission_migration import (
    _connect,
    _target_inventory,
    build_retirement_plan,
    destination_key,
    execute_retirement_plan,
    load_retirement_plan,
    validate_retirement_gate,
    validate_execute_gate,
    validate_switch_gate,
)


def test_template_migration_copy_batch_uses_bounded_workers(monkeypatch):
    import scripts.r2_template_submission_migration as migration

    thread_ids = set()
    lock = threading.Lock()

    def fake_copy(client, bucket, source_key, target_key, size):
        del client, bucket, target_key, size
        with lock:
            thread_ids.add(threading.get_ident())
        time.sleep(0.02)
        return f"source-{source_key}", f"target-{source_key}"

    monkeypatch.setattr(migration, "_copy_and_verify", fake_copy)
    succeeded = []
    failed = []
    rows = [(f"temps/{index}", f"template-submissions/{index}", index) for index in range(8)]

    migration._run_copy_batch(
        object(),
        "user-data-prod",
        rows,
        workers=4,
        on_success=lambda row, digests: succeeded.append((row, digests)),
        on_failure=lambda row, exc: failed.append((row, exc)),
    )

    assert len(succeeded) == len(rows)
    assert failed == []
    assert 2 <= len(thread_ids) <= 4


def test_template_retirement_preflight_uses_bounded_workers(monkeypatch):
    import scripts.r2_template_submission_migration as migration

    thread_ids = set()
    lock = threading.Lock()

    def fake_preflight(client, bucket, source_key, item, state_row, live_size):
        del client, bucket, item, state_row, live_size
        with lock:
            thread_ids.add(threading.get_ident())
        time.sleep(0.02)
        return source_key, {"present": True, "etag": source_key}

    monkeypatch.setattr(migration, "_retirement_preflight_one", fake_preflight)
    inputs = [
        (f"temps/{index}", {}, (None, 0, "verified", "a", "a"), 0)
        for index in range(8)
    ]

    result = migration._run_retirement_preflight_batch(
        object(), "user-data-prod", inputs, workers=4
    )

    assert len(result) == len(inputs)
    assert 2 <= len(thread_ids) <= 4


def test_template_retirement_database_checks_share_one_event_loop(monkeypatch):
    import asyncio
    import scripts.r2_template_submission_migration as migration

    loops = []
    disposed = []

    async def fake_reference_count():
        loops.append(asyncio.get_running_loop())
        return 0

    async def fake_dispose():
        disposed.append(asyncio.get_running_loop())

    monkeypatch.setattr(migration, "_database_reference_count", fake_reference_count)
    monkeypatch.setattr(migration, "_dispose_database_engine", fake_dispose)
    monkeypatch.setattr(
        migration,
        "execute_retirement_plan",
        lambda *args, **kwargs: {"status": "completed"},
    )

    report = migration._execute_retirement_with_reference_guard(
        object(), object(), bucket="user-data-prod", plan={}, workers=4
    )

    assert report["database_references_before"] == 0
    assert report["database_references_after"] == 0
    assert loops[0] is loops[1] is disposed[0]


def test_template_submission_migration_preserves_relative_key():
    assert destination_key("temps/user/final.png") == "template-submissions/user/final.png"
    with pytest.raises(ValueError):
        destination_key("task-results/final.png")


def test_template_submission_migration_gate_is_exactly_scoped():
    validate_execute_gate(
        bucket="user-data-prod",
        enabled=True,
        confirmation="COPY_VERIFIED_TEMPLATE_SUBMISSIONS_user-data-prod",
    )
    with pytest.raises(ValueError):
        validate_execute_gate(
            bucket="user-data-test",
            enabled=True,
            confirmation="COPY_VERIFIED_TEMPLATE_SUBMISSIONS_user-data-test",
        )


def test_template_migration_state_tracks_both_digests_and_database_mapping(tmp_path):
    db = _connect(tmp_path / "state.sqlite3")
    columns = {row[1] for row in db.execute("pragma table_info(objects)")}
    db.close()
    assert {"source_sha256", "target_sha256", "contribution_id"} <= columns


def test_template_database_switch_has_an_independent_gate():
    validate_switch_gate(
        bucket="user-data-prod",
        enabled=True,
        confirmation="SWITCH_VERIFIED_TEMPLATE_SUBMISSIONS_user-data-prod",
    )
    with pytest.raises(ValueError):
        validate_switch_gate(
            bucket="user-data-prod", enabled=True, confirmation="wrong"
        )


def test_template_source_retirement_has_a_plan_bound_gate():
    plan_sha = "a" * 64
    validate_retirement_gate(
        bucket="user-data-prod",
        enabled=True,
        confirmation=(
            "DELETE_VERIFIED_TEMPLATE_SUBMISSION_SOURCES_"
            f"user-data-prod:{plan_sha}"
        ),
        plan_sha256=plan_sha,
    )
    with pytest.raises(ValueError):
        validate_retirement_gate(
            bucket="user-data-prod",
            enabled=True,
            confirmation="DELETE_VERIFIED_TEMPLATE_SUBMISSION_SOURCES_user-data-prod",
            plan_sha256=plan_sha,
        )


def test_template_source_retirement_plan_requires_zero_refs_and_full_verification(tmp_path):
    db = _connect(tmp_path / "state.sqlite3")
    digest = "b" * 64
    db.execute(
        """insert into objects(
             source_key,target_key,byte_size,status,sha256,source_sha256,
             target_sha256,updated_at
           ) values(?,?,?,?,?,?,?,?)""",
        (
            "temps/a.png",
            "template-submissions/a.png",
            10,
            "verified",
            digest,
            digest,
            digest,
            "now",
        ),
    )
    db.commit()

    with pytest.raises(ValueError, match="database references"):
        build_retirement_plan(
            db,
            bucket="user-data-prod",
            scanned=1,
            database_references=1,
        )

    plan = build_retirement_plan(
        db,
        bucket="user-data-prod",
        scanned=1,
        database_references=0,
    )
    db.close()

    assert plan["object_count"] == 1
    assert plan["bytes"] == 10
    assert plan["plan_sha256"]


def test_template_source_retirement_plan_rejects_tampering(tmp_path):
    plan = {
        "schema": "allbot-r2-template-submission-retirement/v1",
        "mode": "dry-run",
        "bucket": "user-data-prod",
        "generated_at": "now",
        "database_references": 0,
        "object_count": 1,
        "bytes": 10,
        "objects": [
            {
                "source_key": "temps/a.png",
                "target_key": "template-submissions/a.png",
                "byte_size": 10,
                "sha256": "c" * 64,
            }
        ],
    }
    from scripts.r2_template_submission_migration import seal_retirement_plan

    plan = seal_retirement_plan(plan)
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    assert load_retirement_plan(path, plan["plan_sha256"])["object_count"] == 1

    plan["bytes"] = 11
    path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid or modified"):
        load_retirement_plan(path, plan["plan_sha256"])


def test_template_source_retirement_verifies_target_and_source_before_delete(tmp_path):
    db = _connect(tmp_path / "state.sqlite3")
    payload = b"template"
    digest = __import__("hashlib").sha256(payload).hexdigest()
    db.execute(
        """insert into objects(
             source_key,target_key,byte_size,status,sha256,source_sha256,
             target_sha256,updated_at
           ) values(?,?,?,?,?,?,?,?)""",
        (
            "temps/a.png",
            "template-submissions/a.png",
            len(payload),
            "verified",
            digest,
            digest,
            digest,
            "now",
        ),
    )
    db.commit()
    plan = build_retirement_plan(
        db,
        bucket="user-data-prod",
        scanned=1,
        database_references=0,
    )

    class FakePaginator:
        def paginate(self, **kwargs):
            assert kwargs == {"Bucket": "user-data-prod", "Prefix": "temps/"}
            return [{"Contents": [{"Key": "temps/a.png", "Size": len(payload)}]}]

    class FakeClient:
        def __init__(self):
            self.objects = {
                "temps/a.png": payload,
                "template-submissions/a.png": payload,
            }

        def get_paginator(self, name):
            assert name == "list_objects_v2"
            return FakePaginator()

        def head_object(self, *, Bucket, Key):
            del Bucket
            if Key not in self.objects:
                from botocore.exceptions import ClientError

                raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
            return {"ContentLength": len(self.objects[Key]), "ETag": digest}

        def get_object(self, *, Bucket, Key):
            del Bucket
            return {"Body": BytesIO(self.objects[Key])}

        def delete_object(self, *, Bucket, Key):
            del Bucket
            del self.objects[Key]

    client = FakeClient()
    report = execute_retirement_plan(
        client,
        db,
        bucket="user-data-prod",
        plan=plan,
    )
    status = db.execute(
        "select status from objects where source_key='temps/a.png'"
    ).fetchone()[0]
    db.close()

    assert report["deleted_count"] == 1
    assert report["post_delete_verified_count"] == 1
    assert status == "retired"
    assert "temps/a.png" not in client.objects
    assert client.objects["template-submissions/a.png"] == payload


def test_template_dry_run_reports_target_conflicts_and_missing_sources(tmp_path):
    db = _connect(tmp_path / "state.sqlite3")
    db.executemany(
        "insert into objects(source_key,target_key,byte_size,status,updated_at) values(?,?,?,?,?)",
        (
            ("temps/a.png", "template-submissions/a.png", 10, "pending", "now"),
            ("temps/b.png", "template-submissions/b.png", 20, "pending", "now"),
            ("temps/c.png", "template-submissions/c.png", 30, "pending", "now"),
        ),
    )
    db.commit()

    class FakeClient:
        def head_object(self, *, Bucket, Key):
            del Bucket
            if Key == "temps/c.png":
                from botocore.exceptions import ClientError

                raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
            sizes = {"temps/a.png": 10, "temps/b.png": 20,
                     "template-submissions/a.png": 10,
                     "template-submissions/b.png": 99}
            if Key not in sizes:
                from botocore.exceptions import ClientError

                raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
            return {"ContentLength": sizes[Key]}

    summary = _target_inventory(FakeClient(), db, "user-data-prod")
    db.close()

    assert summary == {
        "source_missing": 1,
        "target_existing": 2,
        "target_missing": 1,
        "target_size_conflicts": 1,
        "target_existing_unverified": 1,
    }
