from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.task_application import TaskApplication
from src.core.task_core_dependencies import TaskCoreProcessDependencies
from src.core.task_core_types import (
    SubmissionReconciliationPending,
    SubmissionJournal,
    TaskSubmissionCommand,
    TaskSubmissionExecutionResult,
    TaskSubmissionPolicy,
    VideoTaskRequest,
)


def _dependencies() -> TaskCoreProcessDependencies:
    strategy = MagicMock()
    strategy.get_cost.return_value = 3

    async def execute_saga(**kwargs):
        await kwargs["before_dispatch_func"](
            registry_task_id=kwargs["registry_task_id"],
            cost=kwargs["cost"],
            submission_context=kwargs["submission_context"],
        )
        return TaskSubmissionExecutionResult(
            registry_task_id="task-1",
            backend_task_id="backend-1",
            submission_context=SimpleNamespace(saved_inputs=["saved.png"]),
        )

    return TaskCoreProcessDependencies(
        get_strategy_func=MagicMock(return_value=strategy),
        video_task_types=set(),
        build_video_task_request_func=MagicMock(return_value=VideoTaskRequest()),
        check_concurrency_lock_func=AsyncMock(return_value=(True, "")),
        prepare_task_submission_payload_func=AsyncMock(
            return_value=SimpleNamespace(
                final_priority=0,
                saved_inputs=["input.png"],
                user_logger=SimpleNamespace(user_id=7, username="user"),
            )
        ),
        check_and_deduct_credits_func=AsyncMock(return_value=(True, "")),
        execute_task_submission_saga_func=AsyncMock(side_effect=execute_saga),
        attach_submission_side_effects_func=AsyncMock(),
        compensate_failed_submission_func=AsyncMock(),
        release_concurrency_lock_func=AsyncMock(),
        shield_func=AsyncMock(),
        logger=MagicMock(),
    )


class RecordingJournal(SubmissionJournal):
    def __init__(self):
        self.events: list[str] = []

    async def before_debit(self, **_event):
        self.events.append("before_debit")

    async def after_debit(self, **_event):
        self.events.append("after_debit")

    async def before_dispatch(self, **_event):
        self.events.append("before_dispatch")


class ReconcilingJournal(RecordingJournal):
    def should_compensate(self, _error):
        return False


@pytest.mark.asyncio
async def test_application_submits_command_policy_and_journal_with_owned_dependencies():
    dependencies = _dependencies()
    journal = RecordingJournal()
    application = TaskApplication(dependencies=dependencies)

    result = await application.submit(
        TaskSubmissionCommand(
            internal_user_id=7,
            username="user",
            task_type="txt2img",
            inputs={"prompt": "demo"},
            task_id="task-1",
        ),
        TaskSubmissionPolicy(client_type="bot", cost_override=3),
        journal,
    )

    assert result["backend_task_id"] == "backend-1"
    assert journal.events == ["before_debit", "after_debit", "before_dispatch"]
    dependencies.check_and_deduct_credits_func.assert_awaited_once_with(
        7, 3, "txt2img", "user"
    )


@pytest.mark.asyncio
async def test_application_journal_keeps_ambiguous_dispatch_for_reconciliation():
    dependencies = _dependencies()
    journal = ReconcilingJournal()

    async def ambiguous_dispatch(**kwargs):
        await kwargs["before_dispatch_func"](
            registry_task_id=kwargs["registry_task_id"],
            cost=kwargs["cost"],
            submission_context=kwargs["submission_context"],
        )
        raise TimeoutError("response lost")

    dependencies.execute_task_submission_saga_func.side_effect = ambiguous_dispatch

    with pytest.raises(SubmissionReconciliationPending):
        await TaskApplication(dependencies=dependencies).submit(
            TaskSubmissionCommand(
                internal_user_id=7,
                username="user",
                task_type="txt2img",
                inputs={"prompt": "demo"},
                task_id="task-1",
            ),
            TaskSubmissionPolicy(cost_override=3),
            journal,
        )

    assert journal.events == ["before_debit", "after_debit", "before_dispatch"]
    dependencies.compensate_failed_submission_func.assert_not_awaited()
    dependencies.release_concurrency_lock_func.assert_not_awaited()
