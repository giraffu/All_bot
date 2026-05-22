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
async def test_handle_task_completion_uses_task_service_download_seam(monkeypatch):
    download_output = AsyncMock(
        return_value=(b"image-bytes", "saved-output.png", 768, 1024, None)
    )
    send_result_media = AsyncMock()
    cleanup_status = AsyncMock()
    monkeypatch.setattr(TaskService, "_download_and_log_task_output", download_output)
    monkeypatch.setattr(TaskService, "_send_result_media", send_result_media)
    monkeypatch.setattr(TaskService, "_cleanup_completion_status_message", cleanup_status)

    user_logger = SimpleNamespace(username="tester")
    status_msg = MagicMock()

    media_bytes, output_path = await TaskService._handle_task_completion(
        context=SimpleNamespace(bot=MagicMock(), bot_data={}),
        chat_id=123,
        internal_user_id=456,
        prompt="prompt",
        task_type="image",
        task_id="task-seam",
        saved_input_images=["input.png"],
        user_logger=user_logger,
        is_video=False,
        send_result=True,
        reply_markup=None,
        status_msg=status_msg,
        delete_status=True,
        caption="done",
        allow_contribute=False,
    )

    assert media_bytes == b"image-bytes"
    assert output_path == "saved-output.png"
    download_output.assert_awaited_once()
    send_result_media.assert_awaited_once()
    cleanup_status.assert_awaited_once_with(
        status_msg=status_msg,
        delete_status=True,
        send_result=True,
    )


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
async def test_resolve_custom_video_settings_warns_and_downgrades_invalid_combo(
    monkeypatch,
):
    reply_text = AsyncMock()
    monkeypatch.setattr("src.services.task_service.robust_reply_text", reply_text)

    update = SimpleNamespace(effective_message=SimpleNamespace())
    context = SimpleNamespace(
        user_data={
            "custom_video_resolution": "1024p",
            "custom_video_duration": "10s",
        }
    )

    result = await TaskService._resolve_custom_video_settings(
        context,
        update=update,
        warn_invalid_combo=True,
    )

    assert result == ("720p", "10s", 720, 10)
    assert context.user_data["custom_video_resolution"] == "720p"
    reply_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_custom_video_settings_can_downgrade_silently(monkeypatch):
    reply_text = AsyncMock()
    monkeypatch.setattr("src.services.task_service.robust_reply_text", reply_text)

    context = SimpleNamespace(
        user_data={
            "custom_video_resolution": "1024p",
            "custom_video_duration": "10s",
        }
    )

    result = await TaskService._resolve_custom_video_settings(
        context,
        warn_invalid_combo=False,
    )

    assert result == ("720p", "10s", 720, 10)
    assert context.user_data["custom_video_resolution"] == "720p"
    reply_text.assert_not_awaited()


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
async def test_monitor_submitted_bot_task_uses_task_service_monitor_seam(monkeypatch):
    monitor_progress = AsyncMock(return_value={"status": "done"})
    monkeypatch.setattr(
        "src.core.billing_core.get_user_priority_and_identity",
        AsyncMock(return_value=(5, "外门弟子", "金丹期")),
    )
    monkeypatch.setattr(TaskService, "_monitor_task_progress", monitor_progress)

    result = await TaskService._monitor_submitted_bot_task(
        task_id="task-monitor",
        status_msg="status-msg",
        is_video=True,
        internal_user_id=456,
        monitor_func="monitor-func",
    )

    assert result == {"status": "done"}
    monitor_progress.assert_awaited_once_with(
        "task-monitor",
        "status-msg",
        is_video=True,
        monitor_func="monitor-func",
        identity_str="外门弟子",
        user_group="金丹期",
    )


@pytest.mark.asyncio
async def test_complete_monitored_bot_task_preserves_supplied_user_logger(monkeypatch):
    handle_task_completion = AsyncMock(return_value=(b"video-bytes", "output.mp4"))
    monkeypatch.setattr(TaskService, "_handle_task_completion", handle_task_completion)

    user_logger = SimpleNamespace(username="tester")
    runtime_state = SimpleNamespace(actual_cost=9, registry_task_id="reg-1", task_submitted=True)
    message_spec = SimpleNamespace(
        completion_caption="done",
        missing_output_message="missing",
    )

    result = await TaskService._complete_monitored_bot_task(
        context=SimpleNamespace(bot=MagicMock(), bot_data={}),
        chat_id=123,
        status_msg=MagicMock(),
        runtime_state=runtime_state,
        internal_user_id=456,
        username="tester",
        user_logger=user_logger,
        prompt="prompt",
        task_type="custom_video",
        task_id="task-complete",
        saved_input_images=["input.png"],
        final_info={"status": "done"},
        is_video=True,
        send_result=True,
        reply_markup=None,
        delete_status=True,
        caption=None,
        allow_contribute=True,
        message_spec=message_spec,
    )

    assert result == (b"video-bytes", "output.mp4")
    assert handle_task_completion.await_args.kwargs["user_logger"] is user_logger


@pytest.mark.asyncio
async def test_complete_monitored_bot_task_delegates_to_completion_helper(monkeypatch):
    complete_helper = AsyncMock(return_value=(b"video-bytes", "output.mp4"))
    monkeypatch.setattr("src.services.task_service.complete_monitored_bot_task", complete_helper)

    user_logger = SimpleNamespace(username="tester")
    runtime_state = SimpleNamespace(actual_cost=9, registry_task_id="reg-1", task_submitted=True)
    message_spec = SimpleNamespace(
        completion_caption="done",
        missing_output_message="missing",
    )

    result = await TaskService._complete_monitored_bot_task(
        context=SimpleNamespace(bot=MagicMock(), bot_data={}),
        chat_id=123,
        status_msg=MagicMock(),
        runtime_state=runtime_state,
        internal_user_id=456,
        username="tester",
        user_logger=user_logger,
        prompt="prompt",
        task_type="custom_video",
        task_id="task-complete",
        saved_input_images=["input.png"],
        final_info={"status": "done"},
        is_video=True,
        send_result=True,
        reply_markup=None,
        delete_status=True,
        caption=None,
        allow_contribute=True,
        message_spec=message_spec,
    )

    assert result == (b"video-bytes", "output.mp4")
    kwargs = complete_helper.await_args.kwargs
    assert kwargs["user_logger"] is user_logger
    assert kwargs["handle_task_completion_func"] is TaskService._handle_task_completion
    assert kwargs["finalize_failed_task_for_bot_func"] is TaskService._finalize_failed_task_for_bot


@pytest.mark.asyncio
async def test_complete_monitored_bot_task_preserves_explicit_completion_seams(monkeypatch):
    complete_helper = AsyncMock(return_value=(b"video-bytes", "output.mp4"))
    monkeypatch.setattr("src.services.task_service.complete_monitored_bot_task", complete_helper)

    explicit_send_result_media = AsyncMock()
    explicit_cleanup_status = AsyncMock()
    explicit_handle_completion = AsyncMock()
    explicit_finalize_failed = AsyncMock()
    runtime_state = SimpleNamespace(actual_cost=9, registry_task_id="reg-1", task_submitted=True)
    message_spec = SimpleNamespace(
        completion_caption="done",
        missing_output_message="missing",
    )

    result = await TaskService._complete_monitored_bot_task(
        context=SimpleNamespace(bot=MagicMock(), bot_data={}),
        chat_id=123,
        status_msg=MagicMock(),
        runtime_state=runtime_state,
        internal_user_id=456,
        username="tester",
        user_logger=SimpleNamespace(username="tester"),
        prompt="prompt",
        task_type="custom_video",
        task_id="task-complete",
        saved_input_images=["input.png"],
        final_info={"status": "done"},
        is_video=True,
        send_result=True,
        reply_markup=None,
        delete_status=True,
        caption=None,
        allow_contribute=True,
        message_spec=message_spec,
        send_result_media_func=explicit_send_result_media,
        cleanup_completion_status_message_func=explicit_cleanup_status,
        handle_task_completion_func=explicit_handle_completion,
        finalize_failed_task_for_bot_func=explicit_finalize_failed,
    )

    assert result == (b"video-bytes", "output.mp4")
    kwargs = complete_helper.await_args.kwargs
    assert kwargs["send_result_media_func"] is explicit_send_result_media
    assert kwargs["cleanup_completion_status_message_func"] is explicit_cleanup_status
    assert kwargs["handle_task_completion_func"] is explicit_handle_completion
    assert kwargs["finalize_failed_task_for_bot_func"] is explicit_finalize_failed


@pytest.mark.asyncio
async def test_finalize_cancelled_task_for_bot_uses_task_service_edit_seam(monkeypatch):
    finalize_cancel = AsyncMock(
        return_value=TaskCancellationFinalizationResult(
            refunded=True,
            user_message="任务已撤销",
        )
    )
    edit_text = AsyncMock()
    monkeypatch.setattr("src.core.task_core.finalize_task_cancellation", finalize_cancel)
    monkeypatch.setattr("src.services.task_service.robust_edit_text", edit_text)

    result = await TaskService._finalize_cancelled_task_for_bot(
        status_msg="status-msg",
        internal_user_id=456,
        username="tester",
        cost=5,
        task_submitted=True,
        registry_task_id="reg-1",
        explicit_user_message="任务已撤销",
    )

    assert result.user_message == "任务已撤销"
    edit_text.assert_awaited_once_with("status-msg", "✅ 任务已撤销")


@pytest.mark.asyncio
async def test_finalize_failed_task_for_bot_uses_task_service_send_message_seam(monkeypatch):
    finalize_failure = AsyncMock(
        return_value=TaskFailureFinalizationResult(
            refunded=True,
            user_message="系统错误：boom，已退还灵石",
        )
    )
    send_message = AsyncMock()
    monkeypatch.setattr("src.core.task_core.finalize_task_failure", finalize_failure)
    monkeypatch.setattr("src.services.task_service.robust_send_message", send_message)

    context = SimpleNamespace(bot=MagicMock())
    result = await TaskService._finalize_failed_task_for_bot(
        context=context,
        chat_id=123,
        status_msg=None,
        internal_user_id=456,
        username="tester",
        cost=5,
        should_refund=True,
        registry_task_id="reg-2",
        release_lock=True,
        error=RuntimeError("boom"),
        generic_error_prefix="系统错误",
    )

    assert "系统错误" in result.user_message
    send_message.assert_awaited_once_with(
        context.bot,
        123,
        f"❌ {result.user_message}",
    )


@pytest.mark.asyncio
async def test_send_bot_warning_uses_task_service_send_message_seam(monkeypatch):
    send_message = AsyncMock()
    monkeypatch.setattr("src.services.task_service.robust_send_message", send_message)

    context = SimpleNamespace(bot=MagicMock())
    await TaskService._send_bot_warning(context, 123, "warn")

    send_message.assert_awaited_once_with(context.bot, 123, "⚠️ warn")


@pytest.mark.asyncio
async def test_send_bot_domain_error_uses_task_service_send_message_seam(monkeypatch):
    send_message = AsyncMock()
    monkeypatch.setattr("src.services.task_service.robust_send_message", send_message)

    context = SimpleNamespace(bot=MagicMock())
    await TaskService._send_bot_domain_error(context, 123, "bad")

    send_message.assert_awaited_once_with(context.bot, 123, "❌ bad")


@pytest.mark.asyncio
async def test_cleanup_runtime_state_if_needed_uses_core_cleanup_seam(monkeypatch):
    cleanup_runtime = AsyncMock()
    monkeypatch.setattr("src.core.task_core.cleanup_task_runtime_state", cleanup_runtime)

    await TaskService._cleanup_runtime_state_if_needed(
        internal_user_id=456,
        registry_task_id="reg-cleanup",
        release_lock=True,
        terminal_state_finalized=False,
    )

    cleanup_runtime.assert_awaited_once_with(
        internal_user_id=456,
        registry_task_id="reg-cleanup",
        release_lock=True,
    )


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


@pytest.mark.asyncio
async def test_process_ltx_video_task_uses_finalize_task_cancellation(monkeypatch):
    msg = MagicMock()
    finalize_cancel = AsyncMock()
    cleanup_runtime = AsyncMock()

    async def fake_submit(*, runtime_state, **_kwargs):
        runtime_state.task_submitted = True
        runtime_state.actual_cost = 12
        runtime_state.registry_task_id = "task-ltx"
        return "task-ltx", ["input.png"]

    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=456), False)),
    )
    monkeypatch.setattr(
        "src.services.task_service.TaskService._submit_bot_task",
        AsyncMock(side_effect=fake_submit),
    )
    monkeypatch.setattr(
        "src.services.task_service.TaskService._get_acceleration_notice",
        AsyncMock(return_value=""),
    )
    monkeypatch.setattr("src.services.task_service.robust_reply_text", AsyncMock(return_value=msg))
    monkeypatch.setattr("src.services.task_service.robust_edit_text", AsyncMock())
    monkeypatch.setattr(
        "src.services.task_service.TaskService._monitor_submitted_bot_task",
        AsyncMock(side_effect=CoreDomainError("cancelled")),
    )
    monkeypatch.setattr(
        "src.services.task_service.TaskService._finalize_cancelled_task_for_bot",
        finalize_cancel,
    )
    monkeypatch.setattr(
        "src.services.task_service.TaskService._cleanup_runtime_state_if_needed",
        cleanup_runtime,
    )
    monkeypatch.setattr("src.services.task_service.robust_send_message", AsyncMock())

    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=123),
        effective_user=SimpleNamespace(id=789, username="tester"),
        effective_message=SimpleNamespace(),
    )
    context = SimpleNamespace(user_data={}, bot=MagicMock(), t=lambda value: value)

    result = await TaskService.process_ltx_video_task(
        update=update,
        context=context,
        prompt="prompt",
        image_path="input.png",
        cleanup=False,
    )

    assert result == (None, None)
    finalize_cancel.assert_awaited_once()
    cleanup_runtime.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_face_video_task_uses_finalize_task_failure(monkeypatch):
    status_msg = MagicMock()
    finalize_failure = AsyncMock(
        return_value=TaskFailureFinalizationResult(
            refunded=True,
            user_message="系统错误：boom，已退还灵石",
        )
    )
    cleanup_runtime = AsyncMock()

    async def fake_submit(*, runtime_state, **_kwargs):
        runtime_state.task_submitted = True
        runtime_state.actual_cost = 9
        runtime_state.registry_task_id = "task-face-video"
        return "task-face-video", ["face.png", "video.mp4"]

    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=456), False)),
    )
    monkeypatch.setattr(
        "src.services.task_service.TaskService._submit_bot_task",
        AsyncMock(side_effect=fake_submit),
    )
    monkeypatch.setattr(
        "src.services.task_service.TaskService._get_acceleration_notice",
        AsyncMock(return_value=""),
    )
    monkeypatch.setattr(
        "src.services.task_service.TaskService._get_or_send_status_msg",
        AsyncMock(return_value=status_msg),
    )
    monkeypatch.setattr(
        "src.services.task_service.TaskService._monitor_submitted_bot_task",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    monkeypatch.setattr(
        "src.services.task_service.TaskService._finalize_failed_task_for_bot",
        finalize_failure,
    )
    monkeypatch.setattr(
        "src.services.task_service.TaskService._cleanup_runtime_state_if_needed",
        cleanup_runtime,
    )
    monkeypatch.setattr("src.services.task_service.robust_send_message", AsyncMock())

    context = SimpleNamespace(user_data={}, bot=MagicMock())
    result = await TaskService.process_face_video_task(
        context=context,
        chat_id=123,
        user_id=789,
        username="tester",
        face_image_path="face.png",
        video_path="video.mp4",
        resolution=720,
        duration=5,
        cost=9,
        cleanup=False,
    )

    assert result == (None, None)
    finalize_failure.assert_awaited_once()
    cleanup_runtime.assert_awaited_once()
