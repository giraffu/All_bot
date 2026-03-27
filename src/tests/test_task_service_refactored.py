import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.task_service import TaskService
from src.constants import MODE_BLOWJOB, TASK_COSTS

@pytest.mark.asyncio
async def test_process_video_task_template():
    update = AsyncMock()
    context = AsyncMock()
    update.effective_chat.id = 123
    update.effective_user.id = 456
    update.effective_user.username = "testuser"
    update.effective_user.full_name = "Test User"
    
    with patch("src.services.task_service.permission_service") as mock_perm, \
         patch("src.services.task_service.redis_client") as mock_redis, \
         patch("src.services.task_service.UserLogger"), \
         patch("src.services.task_service.robust_reply_text", new_callable=AsyncMock), \
         patch("src.services.task_service.robust_edit_text", new_callable=AsyncMock), \
         patch("src.services.task_service.TaskRegistry") as mock_registry, \
         patch("src.services.task_service.image_service") as mock_image_service, \
         patch("src.services.task_service.TaskService._monitor_task_progress", new_callable=AsyncMock) as mock_monitor, \
         patch("src.services.task_service.TaskService._handle_task_completion", new_callable=AsyncMock) as mock_handle:
         
        mock_redis.increment_user_concurrency = AsyncMock(return_value=1)
        mock_redis.decrement_user_concurrency = AsyncMock()
        mock_perm.get_user_group = AsyncMock(return_value="金丹期")
        mock_perm.get_user_identity = AsyncMock(return_value="外门弟子")
        mock_perm.check_quota = AsyncMock(return_value=True)
        mock_perm.calculate_user_priority = AsyncMock(return_value=5)
        mock_perm.increment_quota = AsyncMock()
        mock_perm.quota_manager.get_user_stats = AsyncMock(return_value={"generation_count": 5})
        
        mock_registry.add_task = AsyncMock(return_value="reg_id")
        mock_registry.update_backend_task_id = AsyncMock()
        mock_registry.remove_task = AsyncMock()
        
        mock_image_service.submit_perfect_video_edit = AsyncMock(return_value="task_id_1")
        mock_monitor.return_value = {"status": "done"}
        mock_handle.return_value = (b"video_bytes", "video_path")
        
        media, path = await TaskService._process_video_task_template(
            update, context, "dummy.jpg", MODE_BLOWJOB, "blowjob", "prompt", cleanup=False
        )
        
        assert media == b"video_bytes"
        assert path == "video_path"
        
        # Check if the right cost and resolution were used
        # For 金丹期, it should be 720p (720, 720)
        # Cost should be 6
        mock_perm.increment_quota.assert_any_call(456, cost=6, username="testuser", task_type=MODE_BLOWJOB)
        mock_image_service.submit_perfect_video_edit.assert_awaited_once()
        kwargs = mock_image_service.submit_perfect_video_edit.await_args.kwargs
        assert kwargs["width"] == 720
        assert kwargs["height"] == 720

