import pytest

from scripts.r2_template_submission_migration import (
    destination_key,
    validate_execute_gate,
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
