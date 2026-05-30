from src.core.task_core_types import TaskSubmissionSideEffectPlan
from src.core.task_lifecycle_contract import (
    BACKEND_STATUS_CANCELLED,
    BACKEND_STATUS_DONE,
    BACKEND_STATUS_ERROR,
    STREAM_STATUS_FAILED,
    STREAM_STATUS_SUCCESS,
    build_task_terminal_snapshot,
    is_backend_cancelled_status,
    is_backend_failed_status,
    is_backend_success_status,
    is_backend_terminal_status,
    normalize_task_submission_side_effect_plan,
)


def test_normalize_task_submission_side_effect_plan_defaults_web_monitor_for_web():
    plan = normalize_task_submission_side_effect_plan(
        submission_side_effect_plan=None,
        client_type="web",
        source_post_id=9,
    )

    assert plan == TaskSubmissionSideEffectPlan(
        attach_web_monitor=True,
        source_post_id=9,
    )


def test_normalize_task_submission_side_effect_plan_preserves_explicit_plan():
    explicit_plan = TaskSubmissionSideEffectPlan(
        attach_web_monitor=False,
        source_post_id=12,
    )

    assert (
        normalize_task_submission_side_effect_plan(
            submission_side_effect_plan=explicit_plan,
            client_type="web",
            source_post_id=3,
        )
        is explicit_plan
    )


def test_task_terminal_snapshot_normalizes_stream_statuses():
    success_snapshot = build_task_terminal_snapshot(
        status=STREAM_STATUS_SUCCESS,
        result_path="result.png",
    )
    failed_snapshot = build_task_terminal_snapshot(status=STREAM_STATUS_FAILED)

    assert success_snapshot.status == BACKEND_STATUS_DONE
    assert success_snapshot.result_path == "result.png"
    assert failed_snapshot.status == BACKEND_STATUS_ERROR


def test_backend_terminal_status_helpers_cover_success_failure_and_cancelled():
    assert is_backend_success_status(BACKEND_STATUS_DONE) is True
    assert is_backend_failed_status(BACKEND_STATUS_ERROR) is True
    assert is_backend_cancelled_status(BACKEND_STATUS_CANCELLED) is True
    assert is_backend_terminal_status(BACKEND_STATUS_DONE) is True
    assert is_backend_terminal_status(BACKEND_STATUS_CANCELLED) is True
    assert is_backend_terminal_status("running") is False
