from unittest.mock import AsyncMock

import pytest

from src.core.task_core_types import TaskSubmissionContext
from src.services import task_web_terminal_finalization


@pytest.mark.asyncio
async def test_web_success_finalizer_retries_when_history_persistence_fails():
    persist_mock = AsyncMock(side_effect=RuntimeError("history schema mismatch"))
    cleanup_mock = AsyncMock()
    submission_context = TaskSubmissionContext(
        task_type="scail2_action_transfer",
        is_video_task=True,
        user_logger=None,
        prompt="dance",
        saved_inputs=["ref.png", "motion.mp4"],
        metadata={},
        allow_contribute=True,
        final_priority=0,
    )

    with pytest.raises(RuntimeError, match="history schema mismatch"):
        await task_web_terminal_finalization.finalize_monitored_web_task_success(
            backend_task_id="backend-1",
            internal_user_id=123,
            username="tester",
            registry_task_id="registry-1",
            submission_context=submission_context,
            result_path="registry-1__result.mp4",
            extra_outputs={},
            persist_successful_web_history_func=persist_mock,
            cleanup_task_runtime_state_func=cleanup_mock,
            logger=task_web_terminal_finalization.logging.getLogger(__name__),
        )

    persist_mock.assert_awaited_once()
    cleanup_mock.assert_not_awaited()
