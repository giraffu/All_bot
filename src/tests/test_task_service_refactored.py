from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.constants import MODE_BLOWJOB
from src.services.task_service import TaskService


@pytest.mark.asyncio
async def test_process_video_task_template():
    status_message = SimpleNamespace(message_id=999)
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=123),
        effective_user=SimpleNamespace(
            id=456,
            username="testuser",
            full_name="Test User",
        ),
        effective_message=SimpleNamespace(chat_id=123),
    )
    context = SimpleNamespace(
        user_data={"custom_video_resolution": "720p"},
        bot=SimpleNamespace(send_message=AsyncMock()),
    )

    with (
        patch("src.services.task_service.permission_service") as mock_perm,
        patch("src.services.task_service.UserLogger"),
        patch(
            "src.services.task_service.robust_reply_text",
            new_callable=AsyncMock,
            return_value=status_message,
        ),
        patch("src.services.task_service.robust_edit_text", new_callable=AsyncMock),
        patch("src.services.task_service.TaskRegistry") as mock_registry,
        patch("src.services.task_service.image_service") as mock_image_service,
        patch("src.core.task_dispatcher.image_service") as mock_dispatcher_image_service,
        patch(
            "src.services.task_service.TaskService._monitor_task_progress",
            new_callable=AsyncMock,
        ) as mock_monitor,
        patch(
            "src.services.task_service.TaskService._handle_task_completion",
            new_callable=AsyncMock,
        ) as mock_handle,
        patch(
            "src.core.task_core.check_and_deduct_credits", new_callable=AsyncMock
        ) as mock_deduct,
        patch(
            "src.core.task_core.check_concurrency_lock", new_callable=AsyncMock
        ) as mock_lock,
        patch(
            "src.core.task_core.get_user_priority_and_identity",
            new_callable=AsyncMock,
        ) as mock_core_priority,
        patch(
            "src.core.billing_core.get_user_priority_and_identity",
            new_callable=AsyncMock,
        ) as mock_billing_priority,
        patch(
            "src.core.user_core.get_or_create_user_by_telegram", new_callable=AsyncMock
        ) as mock_get_user,
        patch("src.services.task_service.robust_send_message", new_callable=AsyncMock),
    ):
        mock_lock.return_value = (True, "")
        mock_deduct.return_value = (True, "")
        mock_core_priority.return_value = (5, "外门弟子", "金丹期")
        mock_billing_priority.return_value = (5, "外门弟子", "金丹期")
        mock_get_user.return_value = (SimpleNamespace(id=456), False)
        mock_perm.get_user_group = AsyncMock(return_value="金丹期")
        mock_perm.get_user_identity = AsyncMock(return_value="外门弟子")
        mock_perm.check_quota = AsyncMock(return_value=True)
        mock_perm.calculate_user_priority = AsyncMock(return_value=5)
        mock_perm.increment_quota = AsyncMock()
        mock_perm.quota_manager.get_user_stats = AsyncMock(
            return_value={"generation_count": 5}
        )

        mock_registry.add_task = AsyncMock(return_value="reg_id")
        mock_registry.update_backend_task_id = AsyncMock()
        mock_registry.remove_task = AsyncMock()

        mock_image_service.submit_perfect_video_edit = AsyncMock(
            return_value="task_id_1"
        )
        mock_dispatcher_image_service.submit_perfect_video_edit = AsyncMock(
            return_value="task_id_1"
        )
        mock_monitor.return_value = {"status": "done"}
        mock_handle.return_value = (b"video_bytes", "video_path")

        media, path = await TaskService._process_video_task_template(
            update,
            context,
            "dummy.jpg",
            MODE_BLOWJOB,
            "blowjob",
            "prompt",
            cleanup=False,
        )

        assert media == b"video_bytes"
        assert path == "video_path"

        # Check if the right cost and resolution were used
        # For 金丹期, it should be 720p (720, 720)
        # Cost should be 18
        # The internal_user_id is dynamic so we can't hardcode 456, just check the call
        assert mock_deduct.called
        mock_dispatcher_image_service.submit_perfect_video_edit.assert_awaited_once()
        kwargs = mock_dispatcher_image_service.submit_perfect_video_edit.await_args.kwargs
        assert kwargs["width"] == 720
        assert kwargs["height"] == 720
