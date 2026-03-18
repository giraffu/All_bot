import pytest
from unittest.mock import AsyncMock, patch
from src.services.task_service import TaskService
from src.constants import MODE_TEXT_TO_IMAGE, TASK_COSTS

@pytest.mark.asyncio
async def test_process_text_to_image_task_success():
    # Setup
    update = AsyncMock()
    context = AsyncMock()
    update.effective_chat.id = 123
    update.effective_user.id = 456
    update.effective_user.username = "testuser"
    update.effective_user.full_name = "Test User"
    
    prompt = "A beautiful landscape"
    task_id = "task-123"
    
    # Mock dependencies
    with patch("src.services.task_service.permission_service") as mock_perm_service, \
         patch("src.services.task_service.image_service") as mock_image_service, \
         patch("src.services.task_service.UserLogger") as mock_logger_cls, \
         patch("src.services.task_service.robust_reply_text") as mock_reply, \
         patch("src.services.task_service.robust_edit_text") as mock_edit, \
         patch("src.services.task_service.TaskService._monitor_task_progress") as mock_monitor, \
         patch("src.services.task_service.TaskService._handle_task_completion") as mock_handle:
        
        # Configure mocks
        mock_perm_service.check_quota = AsyncMock(return_value=True)
        mock_perm_service.increment_quota = AsyncMock()
        mock_image_service.submit_text_to_image_task = AsyncMock(return_value=task_id)
        mock_monitor.return_value = {"status": "done", "result": "path/to/image.png"}
        mock_handle.return_value = (b"image_bytes", "full_path")
        
        # Execute
        media_bytes, full_path = await TaskService.process_text_to_image_task(update, context, prompt)
        
        # Assertions
        cost = TASK_COSTS[MODE_TEXT_TO_IMAGE]
        mock_perm_service.check_quota.assert_awaited_once_with(update, context, cost=cost)
        mock_perm_service.increment_quota.assert_awaited_once_with(456, cost=cost, username="testuser", task_type=MODE_TEXT_TO_IMAGE)
        mock_image_service.submit_text_to_image_task.assert_awaited_once_with(prompt)
        mock_monitor.assert_awaited_once()
        mock_handle.assert_awaited_once()
        
        assert media_bytes == b"image_bytes"
        assert full_path == "full_path"

@pytest.mark.asyncio
async def test_process_text_to_image_task_insufficient_quota():
    # Setup
    update = AsyncMock()
    context = AsyncMock()
    update.effective_chat.id = 123
    update.effective_user.id = 456
    
    prompt = "A beautiful landscape"
    
    # Mock dependencies
    with patch("src.services.task_service.permission_service") as mock_perm_service, \
         patch("src.services.task_service.UserLogger"), \
         patch("src.services.task_service.robust_reply_text") as mock_reply, \
         patch("src.services.task_service.robust_delete_message") as mock_delete:
        
        # Configure mocks
        mock_perm_service.check_quota = AsyncMock(return_value=False)
        
        # Execute
        media_bytes, full_path = await TaskService.process_text_to_image_task(update, context, prompt)
        
        # Assertions
        cost = TASK_COSTS[MODE_TEXT_TO_IMAGE]
        mock_perm_service.check_quota.assert_awaited_once_with(update, context, cost=cost)
        mock_delete.assert_awaited_once()
        
        assert media_bytes is None
        assert full_path is None
