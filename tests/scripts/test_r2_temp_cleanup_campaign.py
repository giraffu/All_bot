import asyncio
import json
import sqlite3
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from scripts.r2_temp_cleanup import Candidate
from scripts.r2_temp_cleanup_campaign import (
    CampaignState,
    build_campaign_plan,
    execute_campaign,
    load_campaign_plan,
    select_full_staging_candidates,
    validate_campaign_execute_gate,
    verify_campaign_candidates,
)


def _inventory():
    db = sqlite3.connect(":memory:")
    db.execute(
        "create table objects(key text primary key,size integer,etag text,last_modified text)"
    )
    db.executemany(
        "insert into objects values(?,?,?,?)",
        [
            ("staging/user-uploads/u/file.png", 10, "input", "2026-08-01T00:00:00Z"),
            ("task-inputs/task/0.png", 10, "input", "2026-08-01T00:01:00Z"),
            ("staging/worker-results/w/file.png", 20, "output", "2026-08-01T00:00:00Z"),
            ("task-results/task/primary.png", 20, "output", "2026-08-01T00:01:00Z"),
            ("staging/unknown/file.png", 10, "input", "2026-08-01T00:00:00Z"),
            ("staging/user-uploads//malformed.png", 10, "input", "2026-08-01T00:00:00Z"),
            ("web_uploads/file.png", 10, "input", "2026-08-01T00:00:00Z"),
            ("temps/template.png", 10, "input", "2026-08-01T00:00:00Z"),
            ("template-submissions/template.png", 10, "input", "2026-08-01T00:00:00Z"),
            ("root.png", 10, "input", "2026-08-01T00:00:00Z"),
            ("staging/user-uploads/u/young.png", 30, "young", "2026-08-07T23:00:00Z"),
            ("task-inputs/task/1.png", 30, "young", "2026-08-01T00:01:00Z"),
            ("staging/user-uploads/u/single.png", 40, "single", "2026-08-01T00:00:00Z"),
        ],
    )
    db.commit()
    return db


def test_full_campaign_selects_only_known_old_staging_with_typed_durable_twins():
    rows = select_full_staging_candidates(
        _inventory(), cutoff="2026-08-07T00:00:00Z"
    )

    assert [(row.key, row.durable_key) for row in rows] == [
        ("staging/user-uploads/u/file.png", "task-inputs/task/0.png"),
        ("staging/worker-results/w/file.png", "task-results/task/primary.png"),
    ]


def test_campaign_plan_contains_every_verified_object_and_is_sha_sealed(tmp_path):
    inventory = tmp_path / "inventory.sqlite3"
    source = _inventory()
    target = sqlite3.connect(inventory)
    source.backup(target)
    target.close()
    candidates = select_full_staging_candidates(
        source, cutoff="2026-08-07T00:00:00Z"
    )
    verified = [
        {**candidate.__dict__, "sha256": "a" * 64}
        for candidate in candidates
    ]

    plan = build_campaign_plan(
        inventory_path=inventory,
        cutoff="2026-08-07T00:00:00Z",
        candidates=candidates,
        verified=verified,
        blocked={},
        probe_failures=[],
        inventory_integrity="ok",
        inventory_object_count=13,
        inventory_bytes=210,
    )
    path = tmp_path / "campaign.json"
    path.write_text(json.dumps(plan), encoding="utf-8")

    loaded = load_campaign_plan(path, plan["plan_sha256"])
    assert loaded["campaign_object_count"] == 2
    assert loaded["campaign_bytes"] == 30
    assert [item["key"] for item in loaded["objects"]] == [
        "staging/user-uploads/u/file.png",
        "staging/worker-results/w/file.png",
    ]
    assert loaded["blocked_count"] == 0
    assert loaded["blocked_bytes"] == 0
    loaded["objects"][0]["key"] = "staging/user-uploads/tampered"
    path.write_text(json.dumps(loaded), encoding="utf-8")
    with pytest.raises(SystemExit, match="modified"):
        load_campaign_plan(path, plan["plan_sha256"])


def test_campaign_state_resumes_and_batches_by_count_and_bytes(tmp_path):
    objects = [
        {"key": "staging/user-uploads/a/1", "byte_size": 30},
        {"key": "staging/user-uploads/a/2", "byte_size": 25},
        {"key": "staging/user-uploads/a/3", "byte_size": 10},
    ]
    state = CampaignState.open(
        tmp_path / "state.sqlite3",
        campaign_id="campaign",
        plan_sha256="b" * 64,
        inventory_sha256="c" * 64,
        objects=objects,
    )

    assert [row["key"] for row in state.next_batch(max_objects=10, max_bytes=50)] == [
        "staging/user-uploads/a/1"
    ]
    state.mark("staging/user-uploads/a/1", "deleted", reason="verified")
    state.close()
    resumed = CampaignState.open(
        tmp_path / "state.sqlite3",
        campaign_id="campaign",
        plan_sha256="b" * 64,
        inventory_sha256="c" * 64,
        objects=objects,
    )
    assert [row["key"] for row in resumed.next_batch(max_objects=2, max_bytes=50)] == [
        "staging/user-uploads/a/2",
        "staging/user-uploads/a/3",
    ]
    assert resumed.summary()["deleted_count"] == 1
    resumed.close()


def test_campaign_state_rejects_payload_drift_from_frozen_plan(tmp_path):
    objects = [{"key": "staging/user-uploads/a/1", "byte_size": 10}]
    path = tmp_path / "state.sqlite3"
    state = CampaignState.open(
        path,
        campaign_id="campaign",
        plan_sha256="b" * 64,
        inventory_sha256="c" * 64,
        objects=objects,
    )
    state.close()
    db = sqlite3.connect(path)
    db.execute(
        "update objects set payload=?",
        (json.dumps({"key": "staging/user-uploads/a/changed", "byte_size": 10}),),
    )
    db.commit()
    db.close()

    with pytest.raises(SystemExit, match="frozen plan"):
        CampaignState.open(
            path,
            campaign_id="campaign",
            plan_sha256="b" * 64,
            inventory_sha256="c" * 64,
            objects=objects,
        )


def test_campaign_execute_confirmation_is_bound_to_exact_plan_sha():
    validate_campaign_execute_gate(
        bucket="user-data-prod",
        enabled=True,
        confirmation="EXECUTE_R2_TEMP_CAMPAIGN_user-data-prod:" + "d" * 64,
        plan_sha256="d" * 64,
    )
    with pytest.raises(ValueError):
        validate_campaign_execute_gate(
            bucket="user-data-prod",
            enabled=True,
            confirmation="EXECUTE_R2_TEMP_CAMPAIGN_user-data-prod:" + "e" * 64,
            plan_sha256="d" * 64,
        )


def _campaign_file(tmp_path, objects):
    inventory = tmp_path / "inventory.sqlite3"
    inventory.write_bytes(b"immutable-inventory")
    candidates = [
        Candidate(
            key=item["key"],
            durable_key=item["durable_key"],
            byte_size=item["byte_size"],
            etag="etag",
            last_modified="2026-08-01T00:00:00Z",
        )
        for item in objects
    ]
    plan = build_campaign_plan(
        inventory_path=inventory,
        cutoff="2026-08-07T00:00:00Z",
        candidates=candidates,
        verified=objects,
        blocked={},
        probe_failures=[],
        inventory_integrity="ok",
        inventory_object_count=10,
        inventory_bytes=100,
    )
    path = tmp_path / "campaign.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    return path, plan


def test_campaign_execute_blocks_changed_objects_and_continues_without_reauthorization(
    tmp_path, monkeypatch
):
    objects = [
        {
            "key": f"staging/user-uploads/u/{name}.png",
            "durable_key": f"task-inputs/t/{name}.png",
            "byte_size": 10,
            "etag": "etag",
            "last_modified": "2026-08-01T00:00:00Z",
            "sha256": "a" * 64,
        }
        for name in ("referenced", "changed", "safe")
    ]
    path, plan = _campaign_file(tmp_path, objects)

    async def references(keys, **_kwargs):
        return {"history": {keys[0]}} if keys else {}

    async def revalidate(_client, _bucket, item):
        if item["key"].endswith("changed.png"):
            return False, "sha_changed"
        return True, "verified"

    class Client:
        def __init__(self):
            self.deleted = []

        def delete_object(self, *, Bucket, Key):
            self.deleted.append((Bucket, Key))

    client = Client()
    monkeypatch.setenv("R2_TEMP_CLEANUP_CAMPAIGN_ENABLED", "true")
    monkeypatch.setattr(
        "scripts.r2_temp_cleanup_campaign.campaign_reference_categories", references
    )
    monkeypatch.setattr(
        "scripts.r2_temp_cleanup_campaign._revalidate_planned_object", revalidate
    )
    monkeypatch.setattr("scripts.r2_temp_cleanup_campaign._r2_client", lambda: client)
    monkeypatch.setattr(
        "scripts.r2_temp_cleanup_campaign._deleted_object_is_absent", lambda *_: True
    )
    monkeypatch.setattr(
        "scripts.r2_temp_cleanup_campaign._sha256_object", lambda *_: "a" * 64
    )
    args = SimpleNamespace(
        approved_campaign=path,
        plan_sha256=plan["plan_sha256"],
        state=tmp_path / "state.sqlite3",
        output=tmp_path / "receipt.json",
        bucket="user-data-prod",
        confirm="EXECUTE_R2_TEMP_CAMPAIGN_user-data-prod:" + plan["plan_sha256"],
        max_batch_objects=10_000,
        max_batch_bytes=50 * 1024**3,
    )

    receipt = asyncio.run(execute_campaign(args))

    assert receipt["status"] == "completed"
    assert receipt["blocked_count"] == 2
    assert receipt["deleted_count"] == 1
    assert client.deleted == [("user-data-prod", objects[2]["key"])]


def test_campaign_system_error_pauses_and_preserves_resume_state(tmp_path, monkeypatch):
    objects = [
        {
            "key": "staging/worker-results/w/safe.png",
            "durable_key": "task-results/t/safe.png",
            "byte_size": 10,
            "etag": "etag",
            "last_modified": "2026-08-01T00:00:00Z",
            "sha256": "a" * 64,
        }
    ]
    path, plan = _campaign_file(tmp_path, objects)

    async def unavailable(*_args, **_kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setenv("R2_TEMP_CLEANUP_CAMPAIGN_ENABLED", "true")
    monkeypatch.setattr(
        "scripts.r2_temp_cleanup_campaign.campaign_reference_categories", unavailable
    )
    monkeypatch.setattr("scripts.r2_temp_cleanup_campaign._r2_client", object)
    args = SimpleNamespace(
        approved_campaign=path,
        plan_sha256=plan["plan_sha256"],
        state=tmp_path / "state.sqlite3",
        output=tmp_path / "receipt.json",
        bucket="user-data-prod",
        confirm="EXECUTE_R2_TEMP_CAMPAIGN_user-data-prod:" + plan["plan_sha256"],
        max_batch_objects=10_000,
        max_batch_bytes=50 * 1024**3,
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        asyncio.run(execute_campaign(args))

    receipt = json.loads((tmp_path / "receipt.json").read_text())
    assert receipt["status"] == "paused"
    assert receipt["pending_count"] == 1


def test_campaign_plan_marks_object_state_changes_blocked(monkeypatch):
    candidate = Candidate(
        key="staging/user-uploads/u/file.png",
        durable_key="task-inputs/t/file.png",
        byte_size=10,
        etag="etag",
        last_modified="2026-08-01T00:00:00Z",
    )

    class Client:
        def head_object(self, *, Bucket, Key):
            return {"ContentLength": 9 if Key == candidate.key else 10}

    verified, failures = asyncio.run(
        verify_campaign_candidates(
            Client(), "user-data-prod", [candidate], concurrency=2
        )
    )

    assert verified == []
    assert failures == [
        {"key": candidate.key, "byte_size": 10, "error": "HEAD_SIZE_MISMATCH"}
    ]


def test_campaign_report_unifies_reference_and_probe_blocks(tmp_path):
    inventory = tmp_path / "inventory.sqlite3"
    inventory.write_bytes(b"snapshot")
    referenced = Candidate(
        "staging/user-uploads/u/ref.png",
        "task-inputs/t/ref.png",
        10,
        "one",
        "2026-08-01T00:00:00Z",
    )
    changed = Candidate(
        "staging/worker-results/w/changed.png",
        "task-results/t/changed.png",
        20,
        "two",
        "2026-08-01T00:00:00Z",
    )
    plan = build_campaign_plan(
        inventory_path=inventory,
        cutoff="2026-08-07T00:00:00Z",
        candidates=[referenced, changed],
        verified=[],
        blocked={"history": {referenced.key}, "favorite": {referenced.key}},
        probe_failures=[
            {"key": changed.key, "byte_size": 20, "error": "SHA256_MISMATCH"}
        ],
        inventory_integrity="ok",
        inventory_object_count=2,
        inventory_bytes=30,
    )

    assert plan["blocked_count"] == 2
    assert plan["blocked_bytes"] == 30
    assert plan["campaign_object_count"] == 0
    assert plan["probe_failure_count"] == 1
    assert plan["blocked_objects"][0]["reasons"] == [
        "reference:favorite",
        "reference:history",
    ]


def test_campaign_plan_fails_closed_on_systemic_r2_error():
    candidate = Candidate(
        key="staging/worker-results/w/file.png",
        durable_key="task-results/t/file.png",
        byte_size=10,
        etag="etag",
        last_modified="2026-08-01T00:00:00Z",
    )

    class Client:
        def head_object(self, *, Bucket, Key):
            raise EndpointConnectionError(endpoint_url="https://r2.invalid")

    with pytest.raises(EndpointConnectionError):
        asyncio.run(
            verify_campaign_candidates(
                Client(), "user-data-prod", [candidate], concurrency=2
            )
        )


def test_campaign_plan_treats_object_404_as_blocked_not_systemic():
    candidate = Candidate(
        key="staging/user-uploads/u/missing.png",
        durable_key="task-inputs/t/missing.png",
        byte_size=10,
        etag="etag",
        last_modified="2026-08-01T00:00:00Z",
    )

    class Client:
        def head_object(self, *, Bucket, Key):
            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "missing"}},
                "HeadObject",
            )

    verified, failures = asyncio.run(
        verify_campaign_candidates(
            Client(), "user-data-prod", [candidate], concurrency=2
        )
    )
    assert verified == []
    assert failures[0]["error"] == "OBJECT_MISSING"
