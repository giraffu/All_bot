from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.task_service import TaskService


@pytest.mark.asyncio
async def test_handle_task_completion_keeps_success_flow_when_metadata_probe_fails(
    monkeypatch,
):
    monkeypatch.setattr(
        "src.services.task_service.image_service.download_video_result",
        AsyncMock(return_value=b"video-bytes"),
    )
    monkeypatch.setattr(
        "src.services.task_service.extract_media_metadata_from_bytes_best_effort",
        MagicMock(return_value=(None, None, None)),
    )
    monkeypatch.setattr(
        "src.services.task_service.permission_service.refresh_user_group",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "src.services.task_service.robust_send_video",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "src.services.task_service.robust_delete_message",
        AsyncMock(),
    )

    user_logger = MagicMock()
    user_logger.save_output_image.return_value = "saved-output.mp4"
    user_logger.log_task = AsyncMock()

    media_bytes, output_path = await TaskService._handle_task_completion(
        context=SimpleNamespace(bot=MagicMock(), bot_data={}),
        chat_id=123,
        internal_user_id=456,
        prompt="prompt",
        task_type="custom_video",
        task_id="task-1",
        saved_input_images=["input.png"],
        user_logger=user_logger,
        is_video=True,
        send_result=True,
        reply_markup=None,
        status_msg=MagicMock(),
        delete_status=True,
        caption="done",
        allow_contribute=True,
    )

    assert media_bytes == b"video-bytes"
    assert output_path == "saved-output.mp4"
    user_logger.log_task.assert_awaited_once()
    kwargs = user_logger.log_task.await_args.kwargs
    assert kwargs["width"] is None
    assert kwargs["height"] is None
    assert kwargs["duration"] is None
