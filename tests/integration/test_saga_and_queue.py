import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from src.core.task_core import process_and_submit_task, CoreDomainError

# Dummy test for Saga Compensation to verify asyncio.shield logic
@pytest.mark.asyncio
async def test_saga_compensation_refunds_credits_and_releases_lock():
    user_id = 123
    username = "test_user"
    task_type = "face_swap"
    inputs = {"face_image": "face.png", "target_image": "body.png"}

    with patch('src.core.task_core.check_concurrency_lock', new_callable=AsyncMock) as mock_lock, \
         patch('src.core.task_core.check_and_deduct_credits', new_callable=AsyncMock) as mock_deduct, \
         patch('src.core.task_core.dispatch_to_worker', new_callable=AsyncMock) as mock_submit, \
         patch('src.core.task_core.refund_credits', new_callable=AsyncMock) as mock_refund, \
         patch('src.core.task_core.release_concurrency_lock', new_callable=AsyncMock) as mock_release, \
         patch('src.core.task_core.get_user_priority_and_identity', new_callable=AsyncMock) as mock_identity, \
         patch('src.core.task_core._process_input_path', new_callable=AsyncMock) as mock_process:

        # Setup mocks
        mock_lock.return_value = (True, "")
        mock_deduct.return_value = (True, "")
        mock_identity.return_value = (0, "user", "title")
        mock_process.return_value = "processed.png"
        
        # Simulate external service failure
        mock_submit.side_effect = Exception("API refused connection")

        with pytest.raises(CoreDomainError, match="系统派发失败，灵石已全额退还"):
            await process_and_submit_task(user_id, username, task_type, inputs, "test_task_id")

        # Assert Saga compensation occurred
        mock_refund.assert_called_once()
        mock_release.assert_called_once_with(user_id)

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
    result = await qm.enqueue_task(TaskType.IMG2IMG, {"prompt": "test"}, 0, task_id=task_id)
    assert result == task_id
