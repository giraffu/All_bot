import pytest

from scripts.r2_template_submission_migration import (
    _connect,
    _target_inventory,
    destination_key,
    validate_execute_gate,
    validate_switch_gate,
)


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
