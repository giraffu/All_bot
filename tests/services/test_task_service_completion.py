from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.core.task_core import (
    CoreDomainError,
    TaskCancellationFinalizationResult,
    TaskFailureFinalizationResult,
    TaskSuccessPersistenceResult,
)
from src.constants import MODE_FACESWAP_STEP1, MODE_NAME_MAP
from src.services.task_service import TaskService


@pytest.mark.asyncio
async def test_handle_task_completion_keeps_success_flow_when_metadata_probe_fails(
    monkeypatch,
):
    persist_mock = AsyncMock(
        return_value=TaskSuccessPersistenceResult(
            media_bytes=b"video-bytes",
            output_file="saved-output.mp4",
            width=None,
            height=None,
            duration=None,
        )
    )
    monkeypatch.setattr(
        "src.core.task_core.persist_successful_task_result",
        persist_mock,
    )
    monkeypatch.setattr(
        "src.services.tg_task_runtime.robust_send_video",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "src.services.tg_task_runtime.robust_delete_message",
        AsyncMock(),
    )

    user_logger = SimpleNamespace(username="tester")

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
    persist_mock.assert_awaited_once()
    kwargs = persist_mock.await_args.kwargs
    assert kwargs["source"] == "bot"
    assert kwargs["refresh_user_group_after_log"] is True
    assert kwargs["billing_resolution"] is None
    assert kwargs["backend_task_id"] == "task-1"
    assert kwargs["registry_task_id"] == "task-1"


@pytest.mark.asyncio
async def test_download_and_log_task_output_handles_image_branch(monkeypatch):
    persist_mock = AsyncMock(
        return_value=TaskSuccessPersistenceResult(
            media_bytes=b"image-bytes",
            output_file="saved-output.png",
            width=768,
            height=1024,
            duration=None,
        )
    )
    monkeypatch.setattr(
        "src.core.task_core.persist_successful_task_result",
        persist_mock,
    )

    media_bytes, output_path, width, height, duration = (
        await TaskService._download_and_log_task_output(
            internal_user_id=456,
            username="tester",
            prompt="prompt",
            task_type="image",
            task_id="task-2",
            saved_input_images=["input.png"],
            is_video=False,
            allow_contribute=True,
            billing_resolution="1024",
            requested_duration=None,
        )
    )

    assert media_bytes == b"image-bytes"
    assert output_path == "saved-output.png"
    assert width == 768
    assert height == 1024
    assert duration is None
    persist_mock.assert_awaited_once()
    kwargs = persist_mock.await_args.kwargs
    assert kwargs["username"] == "tester"
    assert kwargs["task_type"] == "image"
    assert kwargs["source"] == "bot"


def test_build_result_reply_markup_injects_gallery_button_when_missing():
    custom_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("自定义", callback_data="custom_action")]]
    )

    final_markup = TaskService._build_result_reply_markup(
        task_type="custom_video",
        task_id="task-3",
        allow_contribute=True,
        reply_markup=custom_markup,
    )

    first_row = final_markup.inline_keyboard[0]
    assert first_row[0].callback_data == "submit_gallery_task-3"


def test_record_result_message_meta_uses_special_mode_mapping_for_face_swap():
    context = SimpleNamespace(bot_data={})
    sent_msg = SimpleNamespace(message_id=42)

    TaskService._record_result_message_meta(
        context=context,
        sent_msg=sent_msg,
        task_type="face_swap",
        prompt="prompt",
        task_id="task-4",
    )

    assert context.bot_data["msg_meta_42"]["mode_name"] == MODE_NAME_MAP.get(
        MODE_FACESWAP_STEP1
    )
    assert context.bot_data["msg_meta_42"]["prompt"] == "prompt"
    assert context.bot_data["msg_meta_42"]["task_id"] == "task-4"


@pytest.mark.asyncio
async def test_send_result_media_uses_photo_sender_and_records_meta(monkeypatch):
    sent_msg = SimpleNamespace(message_id=99)
    send_photo = AsyncMock(return_value=sent_msg)
    send_video = AsyncMock()
    monkeypatch.setattr("src.services.tg_task_runtime.robust_send_photo", send_photo)
    monkeypatch.setattr("src.services.tg_task_runtime.robust_send_video", send_video)

    context = SimpleNamespace(bot=MagicMock(), bot_data={})

    result = await TaskService._send_result_media(
        context=context,
        chat_id=123,
        media_bytes=b"image-bytes",
        is_video=False,
        caption=None,
        task_type="image",
        task_id="task-5",
        allow_contribute=False,
        reply_markup=None,
        prompt="prompt-5",
    )

    assert result is sent_msg
    send_photo.assert_awaited_once()
    send_video.assert_not_awaited()
    kwargs = send_photo.await_args.kwargs
    assert kwargs["photo"] == b"image-bytes"
    assert kwargs["caption"] == "✅ 图片生成完成"
    assert context.bot_data["msg_meta_99"]["task_id"] == "task-5"


@pytest.mark.asyncio
async def test_cleanup_completion_status_message_only_deletes_when_enabled(
    monkeypatch,
):
    delete_message = AsyncMock()
    monkeypatch.setattr(
        "src.services.tg_task_runtime.robust_delete_message",
        delete_message,
    )
    status_msg = MagicMock()

    await TaskService._cleanup_completion_status_message(
        status_msg=status_msg,
        delete_status=False,
        send_result=True,
    )
    await TaskService._cleanup_completion_status_message(
        status_msg=status_msg,
        delete_status=True,
        send_result=False,
    )
    delete_message.assert_not_awaited()

    await TaskService._cleanup_completion_status_message(
        status_msg=status_msg,
        delete_status=True,
        send_result=True,
    )
    delete_message.assert_awaited_once_with(status_msg)


@pytest.mark.asyncio
async def test_process_generation_task_uses_finalize_task_cancellation(monkeypatch):
    status_msg = MagicMock()
    finalize_cancel = AsyncMock(
        return_value=TaskCancellationFinalizationResult(
            refunded=True,
            user_message="任务已撤销，预扣的 5 灵石已全额退回。",
        )
    )
    cleanup_runtime = AsyncMock()

    monkeypatch.setattr(
        "src.services.task_service.TaskService._get_acceleration_notice",
        AsyncMock(return_value=""),
    )
    monkeypatch.setattr(
        "src.services.task_service.TaskService._get_or_send_status_msg",
        AsyncMock(return_value=status_msg),
    )
    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=456), False)),
    )
    monkeypatch.setattr(
        "src.core.task_core.process_and_submit_task",
        AsyncMock(
            return_value={
                "cost": 5,
                "registry_task_id": "task-6",
                "saved_inputs": ["input.png"],
            }
        ),
    )
    monkeypatch.setattr(
        "src.core.billing_core.get_user_priority_and_identity",
        AsyncMock(return_value=(0, "user", "外门弟子")),
    )
    monkeypatch.setattr(
        "src.services.task_service.TaskService._monitor_task_progress",
        AsyncMock(side_effect=CoreDomainError("cancelled")),
    )
    monkeypatch.setattr(
        "src.core.task_core.finalize_task_cancellation",
        finalize_cancel,
    )
    monkeypatch.setattr(
        "src.core.task_core.cleanup_task_runtime_state",
        cleanup_runtime,
    )
    monkeypatch.setattr("src.services.task_service.robust_edit_text", AsyncMock())
    monkeypatch.setattr("src.services.task_service.robust_send_message", AsyncMock())

    context = SimpleNamespace(user_data={}, bot=MagicMock())
    result = await TaskService.process_generation_task(
        context=context,
        chat_id=123,
        user_id=789,
        username="tester",
        prompt="prompt",
        images=["input.png"],
        is_video=False,
    )

    assert result == (None, None)
    finalize_cancel.assert_awaited_once()
    cleanup_runtime.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_generation_task_uses_finalize_task_failure(monkeypatch):
    status_msg = MagicMock()
    finalize_failure = AsyncMock(
        return_value=TaskFailureFinalizationResult(
            refunded=True,
            user_message="出错了：boom，已退还灵石",
        )
    )
    cleanup_runtime = AsyncMock()
    send_message = AsyncMock()

    monkeypatch.setattr(
        "src.services.task_service.TaskService._get_acceleration_notice",
        AsyncMock(return_value=""),
    )
    monkeypatch.setattr(
        "src.services.task_service.TaskService._get_or_send_status_msg",
        AsyncMock(return_value=status_msg),
    )
    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=456), False)),
    )
    monkeypatch.setattr(
        "src.core.task_core.process_and_submit_task",
        AsyncMock(
            return_value={
                "cost": 5,
                "registry_task_id": "task-7",
                "saved_inputs": ["input.png"],
            }
        ),
    )
    monkeypatch.setattr(
        "src.core.billing_core.get_user_priority_and_identity",
        AsyncMock(return_value=(0, "user", "外门弟子")),
    )
    monkeypatch.setattr(
        "src.services.task_service.TaskService._monitor_task_progress",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    monkeypatch.setattr(
        "src.core.task_core.finalize_task_failure",
        finalize_failure,
    )
    monkeypatch.setattr(
        "src.core.task_core.cleanup_task_runtime_state",
        cleanup_runtime,
    )
    monkeypatch.setattr("src.services.task_service.robust_edit_text", AsyncMock())
    monkeypatch.setattr("src.services.task_service.robust_send_message", send_message)

    context = SimpleNamespace(user_data={}, bot=MagicMock())
    result = await TaskService.process_generation_task(
        context=context,
        chat_id=123,
        user_id=789,
        username="tester",
        prompt="prompt",
        images=["input.png"],
        is_video=False,
    )

    assert result == (None, None)
    finalize_failure.assert_awaited_once()
    cleanup_runtime.assert_not_awaited()
    send_message.assert_awaited()
