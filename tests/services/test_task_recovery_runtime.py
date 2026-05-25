from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.task_core import (
    TaskPersistencePostprocessPlan,
    TaskSuccessPersistenceResult,
)
from src.services import task_recovery_runtime


@pytest.mark.asyncio
async def test_handle_recovered_task_completion_uses_core_helper_and_records_meta(
    monkeypatch,
):
    persist_mock = AsyncMock(
        return_value=TaskSuccessPersistenceResult(
            media_bytes=b"image-bytes",
            output_file="saved-output.png",
            width=768,
            height=1024,
            duration=None,
        )
    )
    send_photo = AsyncMock(return_value=SimpleNamespace(message_id=88))
    delete_message = AsyncMock()

    monkeypatch.setattr(
        "src.services.task_recovery_runtime.persist_successful_task_result",
        persist_mock,
    )
    monkeypatch.setattr(
        "src.services.tg_task_runtime.robust_send_photo",
        send_photo,
    )
    monkeypatch.setattr(
        "src.services.tg_task_runtime.robust_delete_message",
        delete_message,
    )

    context = SimpleNamespace(bot=MagicMock(), bot_data={})
    status_msg = MagicMock()

    result = await task_recovery_runtime._handle_recovered_task_completion(
        context=context,
        chat_id=123,
        internal_user_id=456,
        username="tester",
        prompt="prompt",
        task_type="image",
        task_id="task-1",
        saved_input_images=["input.png"],
        is_video=False,
        send_result=True,
        reply_markup=None,
        status_msg=status_msg,
        delete_status=True,
        allow_contribute=False,
        billing_resolution="1024",
        requested_duration=None,
    )

    assert result.output_file == "saved-output.png"
    persist_mock.assert_awaited_once()
    assert persist_mock.await_args.kwargs["postprocess_plan"] == (
        TaskPersistencePostprocessPlan(
            source="bot",
            refresh_user_group_after_log=True,
        )
    )
    send_photo.assert_awaited_once()
    delete_message.assert_awaited_once_with(status_msg)
    assert context.bot_data["msg_meta_88"]["task_id"] == "task-1"


@pytest.mark.asyncio
async def test_run_recovered_task_uses_local_monitor_and_completion(monkeypatch):
    monitor_mock = AsyncMock(return_value={"status": "done"})
    completion_mock = AsyncMock()

    monkeypatch.setattr(
        "src.services.task_recovery_runtime.permission_service.get_user_identity",
        AsyncMock(return_value="外门弟子"),
    )
    monkeypatch.setattr(
        "src.services.task_recovery_runtime.permission_service.get_user_group",
        AsyncMock(return_value="外门弟子"),
    )
    monkeypatch.setattr(
        "src.services.task_recovery_runtime._monitor_recovered_task_progress",
        monitor_mock,
    )
    monkeypatch.setattr(
        "src.services.task_recovery_runtime._handle_recovered_task_completion",
        completion_mock,
    )

    application = SimpleNamespace(bot=MagicMock(), bot_data={})
    recovered = await task_recovery_runtime.run_recovered_task(
        {
            "user_id": 1,
            "username": "tester",
            "backend_task_id": "backend-1",
            "chat_id": 100,
            "message_id": 200,
            "task_type": "image",
            "prompt": "hello",
            "saved_input_images": ["input.png"],
            "is_video": False,
            "allow_contribute": True,
        },
        application,
    )

    assert recovered is True
    monitor_mock.assert_awaited_once()
    completion_mock.assert_awaited_once()
    kwargs = completion_mock.await_args.kwargs
    assert kwargs["allow_contribute"] is True
    assert kwargs["task_id"] == "backend-1"
