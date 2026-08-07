import pytest

from scripts.r2_template_submission_migration import (
    _connect,
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
