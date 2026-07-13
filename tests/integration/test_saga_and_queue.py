from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core import task_core
from src.core.task_core import process_and_submit_task
from src.core.task_core_dependencies import TaskCoreProcessDependencies
from src.core.task_core_types import CoreDomainError, TaskSubmissionContext, VideoTaskRequest


# Dummy test for Saga Compensation to verify asyncio.shield logic
@pytest.mark.asyncio
async def test_saga_compensation_refunds_credits_and_releases_lock():
    user_id = 123
    username = "test_user"
    task_type = "face_swap"
    inputs = {"face_image": "face.png", "target_image": "body.png"}
    mock_lock = AsyncMock(return_value=(True, ""))
    mock_deduct = AsyncMock(return_value=(True, ""))
    mock_refund = AsyncMock()
    mock_release = AsyncMock()

    async def prepare_payload(**kwargs):
        return TaskSubmissionContext(
            task_type=kwargs["task_type"],
            is_video_task=False,
            user_logger=SimpleNamespace(user_id=user_id, username=username),
            prompt="prompt",
            saved_inputs=["processed.png"],
            metadata={},
            allow_contribute=True,
            final_priority=0,
            video_request=VideoTaskRequest(),
        )

    async def execute_saga(**_kwargs):
        raise Exception("API refused connection")

    async def compensate_failed_submission(**kwargs):
        await mock_refund(
            kwargs["user_id"],
            kwargs["cost"],
            task_type="refund_saga_failed",
            username=kwargs["username"],
        )

    dependencies = TaskCoreProcessDependencies(
        get_strategy_func=lambda _task_type: SimpleNamespace(
            get_cost=lambda _inputs: 1
        ),
        video_task_types={"custom_video", "ltx_video"},
        build_video_task_request_func=task_core.build_video_task_request,
        check_concurrency_lock_func=mock_lock,
        prepare_task_submission_payload_func=prepare_payload,
        check_and_deduct_credits_func=mock_deduct,
        execute_task_submission_saga_func=execute_saga,
        attach_submission_side_effects_func=lambda **_kwargs: None,
        compensate_failed_submission_func=compensate_failed_submission,
        release_concurrency_lock_func=mock_release,
        shield_func=lambda coro: coro,
        logger=task_core.logger,
    )

    with pytest.raises(CoreDomainError, match="系统派发失败，灵石已全额退还"):
        await process_and_submit_task(
            user_id,
            username,
            task_type,
            inputs,
            "test_task_id",
            dependencies=dependencies,
        )

    mock_deduct.assert_awaited_once()
    mock_refund.assert_awaited_once_with(
        user_id,
        1,
        task_type="refund_saga_failed",
        username=username,
    )
    mock_release.assert_awaited_once_with(
        user_id,
        idempotency_key="task_concurrency:test_task_id",
    )


@pytest.mark.asyncio
async def test_queue_manager_requires_task_id():
    from backend.app.queue_manager import QueueManager
    from backend.app.models import TaskType

    mock_redis = AsyncMock()
    qm = QueueManager(mock_redis)

    # In Python 3.10+, TypeError is raised when a required argument is missing
    with pytest.raises(TypeError):
        # Missing task_id argument should raise TypeError
        await qm.enqueue_task(TaskType.IMG2IMG, {"prompt": "test"}, 0)

    # Calling with task_id should work
    task_id = "test-uuid"
    result = await qm.enqueue_task(
        TaskType.IMG2IMG, {"prompt": "test"}, 0, task_id=task_id
    )
    assert result == task_id
