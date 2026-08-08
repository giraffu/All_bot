import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from scripts.r2_media_governance import (
    MediaReference,
    build_governance_index,
    freeze_flat_root_campaign,
    freeze_numeric_migration_plan,
    select_flat_root_size_candidates,
    validate_inventory,
    validate_flat_root_delete_gate,
)


def _inventory(path: Path) -> None:
    db = sqlite3.connect(path)
    db.execute(
        "create table objects(key text primary key,size integer not null,"
        "etag text not null,last_modified text not null) without rowid"
    )
    db.executemany(
        "insert into objects values(?,?,?,?)",
        [
            ("7/input_images/a.png", 3, "legacy", "2026-08-01T00:00:00Z"),
            ("7/output_images/b.png", 4, "legacy", "2026-08-01T00:00:00Z"),
            ("flat.png", 5, "flat", "2026-08-01T00:00:00Z"),
            ("task-results/backend/primary.png", 5, "durable", "2026-08-01T00:00:00Z"),
            ("web_uploads/7/x.png", 6, "excluded", "2026-08-01T00:00:00Z"),
        ],
    )
    db.commit()
    db.close()


def test_inventory_is_validated_and_reused_into_governance_index(tmp_path):
    inventory = tmp_path / "inventory.sqlite3"
    index = tmp_path / "governance.sqlite3"
    _inventory(inventory)

    evidence = validate_inventory(inventory)
    built = build_governance_index(inventory, index)

    assert evidence["integrity"] == "ok"
    assert evidence["object_count"] == 5
    assert built["inventory_sha256"] == evidence["sha256"]
    db = sqlite3.connect(index)
    columns = {row[1] for row in db.execute("pragma table_info(media_objects)")}
    assert {
        "object_key", "size", "sha256", "object_class", "registry_task_id",
        "backend_task_id", "role", "ordinal", "referenced_by", "durable_target",
        "migration_status", "cleanup_status", "error",
    } <= columns
    assert db.execute("select count(*) from media_objects").fetchone()[0] == 5
    assert db.execute("select value from governance_metadata where key='inventory_sha256'").fetchone()[0] == evidence["sha256"]
    db.close()


def test_numeric_migration_plan_only_maps_unambiguous_references(tmp_path):
    inventory = tmp_path / "inventory.sqlite3"
    index = tmp_path / "governance.sqlite3"
    output = tmp_path / "migration.json"
    _inventory(inventory)
    build_governance_index(inventory, index)
    references = [
        MediaReference("7/input_images/a.png", "registry", "backend", "input", 0, "history:1"),
        MediaReference("7/output_images/b.png", "registry", None, "primary", 0, "history:1"),
    ]

    plan = freeze_numeric_migration_plan(index, references, output)

    assert plan["migratable_count"] == 1
    assert plan["migratable_bytes"] == 3
    assert plan["unresolved_count"] == 1
    assert plan["objects"][0]["durable_target"] == "task-inputs/registry/0.png"
    assert len(plan["plan_sha256"]) == 64
    stored = json.loads(output.read_text())
    assert stored["plan_sha256"] == plan["plan_sha256"]


def test_numeric_plan_bounds_unresolved_details_in_frozen_json(tmp_path):
    inventory = tmp_path / "inventory.sqlite3"
    db = sqlite3.connect(inventory)
    db.execute(
        "create table objects(key text primary key,size integer not null,"
        "etag text not null,last_modified text not null) without rowid"
    )
    db.executemany(
        "insert into objects values(?,?,?,?)",
        [(f"7/input_images/{i}.png", 1, "etag", "2026-08-01") for i in range(150)],
    )
    db.commit()
    db.close()
    index = tmp_path / "governance.sqlite3"
    build_governance_index(inventory, index)

    plan = freeze_numeric_migration_plan(index, [], tmp_path / "plan.json")

    assert plan["unresolved_count"] == 150
    assert plan["unresolved_bytes"] == 150
    assert len(plan["unresolved_samples"]) == 100


def test_flat_root_prefilter_is_size_only_and_excludes_non_flat_keys(tmp_path):
    inventory = tmp_path / "inventory.sqlite3"
    index = tmp_path / "governance.sqlite3"
    _inventory(inventory)
    build_governance_index(inventory, index)

    assert select_flat_root_size_candidates(index) == [
        ("flat.png", "task-results/backend/primary.png", 5)
    ]


def test_flat_root_campaign_records_dual_full_sha_and_reference_audit(tmp_path):
    inventory = tmp_path / "inventory.sqlite3"
    index = tmp_path / "governance.sqlite3"
    output = tmp_path / "cleanup.json"
    _inventory(inventory)
    build_governance_index(inventory, index)

    plan = freeze_flat_root_campaign(
        index,
        verified=[{
            "object_key": "flat.png",
            "durable_twin": "task-results/backend/primary.png",
            "size": 5,
            "source_sha256": "a" * 64,
            "durable_sha256": "a" * 64,
            "reference_audit": {
                "history": "clear", "gallery": "clear", "favorite": "clear",
                "public": "clear", "template": "clear", "archive": "clear",
                "active_task": "clear", "redis": "clear", "head": "verified",
            },
        }],
        blocked=[{"object_key": "other.png", "reason": "referenced:history"}],
        output=output,
        batch_id="flat-root-1",
    )

    assert plan["campaign_object_count"] == 1
    assert plan["campaign_bytes"] == 5
    assert plan["blocked_count"] == 1
    assert len(plan["campaign_sha256"]) == 64
    assert plan["objects"][0]["source_sha256"] == plan["objects"][0]["durable_sha256"]


def test_flat_root_delete_gate_binds_bucket_and_exact_campaign_sha():
    digest = "d" * 64
    validate_flat_root_delete_gate(
        bucket="user-data-prod", enabled=True,
        confirmation=f"DELETE_FLAT_ROOT_user-data-prod:{digest}",
        campaign_sha256=digest,
    )
    import pytest
    with pytest.raises(ValueError):
        validate_flat_root_delete_gate(
            bucket="user-data-prod", enabled=False,
            confirmation=f"DELETE_FLAT_ROOT_user-data-prod:{digest}",
            campaign_sha256=digest,
        )


def test_user_logger_writes_only_new_asset_contract_keys(tmp_path, monkeypatch):
    from src.logger import UserLogger
    uploaded = []
    monkeypatch.setattr(
        "src.logger.storage",
        SimpleNamespace(
            upload_file=lambda path, key: uploaded.append(key) or key,
            upload_bytes=lambda data, key, **kwargs: uploaded.append(key) or key,
        ),
    )
    source = tmp_path / "input.png"
    source.write_bytes(b"png")
    logger = UserLogger(7)

    input_key = logger.save_input_image(str(source))
    output_key = logger.save_output_image(b"png", "backend-1")

    assert input_key.startswith("staging/user-uploads/7/")
    assert output_key == "task-results/backend-1/primary.png"
    assert all("/input_images/" not in key and "/output_images/" not in key for key in uploaded)
    freeze_flat_root_campaign,
