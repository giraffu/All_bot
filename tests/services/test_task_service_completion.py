from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock

import pytest
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.core.task_core import (
    TaskCancellationFinalizationResult,
    TaskFailureFinalizationResult,
    TaskPersistencePostprocessPlan,
    TaskSuccessPersistenceResult,
)
from src.services.task_service_types import (
    BotTaskCancelled,
    BotTaskCompletionContext,
    BotTaskFailureContext,
)
from src.constants import (
    MODE_FACESWAP_STEP1,
    MODE_IMAGE_TO_VIDEO,
    MODE_NAME_MAP,
    MODE_WAN22_VIDEO_V2,
)
from src.services import task_service_completion as completion_helpers
from src.services import task_service_finalize as support
from src.services import task_service_entrypoints_video as video_entrypoints
from src.services import tg_task_progress_presentation as tg_progress_helpers
from src.services import tg_task_runtime as tg_runtime_helpers
from src.services.task_service_entrypoints_specialized import (
    process_face_video_task,
    process_ltx_video_task,
)
from src.services.task_service_generation_image import process_standard_generation_task as process_generation_task
from src.services.task_service_generation_wan22 import (
    process_wan22_video_v2_generation_task as process_wan22_video_v2_task,
)


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
        "src.core.task_core_persistence.persist_successful_task_result",
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

    media_bytes, output_path = await completion_helpers.handle_task_completion(
        context=SimpleNamespace(bot=MagicMock(), bot_data={}),
        chat_id=123,
        internal_user_id=456,
        prompt="prompt",
        task_type="custom_video",
        registry_task_id="registry-1",
        backend_task_id="backend-1",
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
    assert kwargs["postprocess_plan"] == TaskPersistencePostprocessPlan(
        source="bot",
        refresh_user_group_after_log=True,
    )
    assert kwargs["billing_resolution"] is None
    assert kwargs["extra_outputs"] is None
    assert kwargs["backend_task_id"] == "backend-1"
    assert kwargs["registry_task_id"] == "registry-1"


@pytest.mark.asyncio
async def test_handle_task_completion_uses_helper_download_default(monkeypatch):
    download_output = AsyncMock(
        return_value=TaskSuccessPersistenceResult(
            media_bytes=b"image-bytes",
            output_file="saved-output.png",
            width=768,
            height=1024,
            duration=None,
        )
    )
    send_result_media = AsyncMock()
    cleanup_status = AsyncMock()
    monkeypatch.setattr(
        "src.services.task_service_completion.download_and_log_task_output",
        download_output,
    )
    monkeypatch.setattr(
        "src.services.task_service_completion.send_result_media",
        send_result_media,
    )
    monkeypatch.setattr(
        "src.services.task_service_completion.cleanup_completion_status_message",
        cleanup_status,
    )

    user_logger = SimpleNamespace(username="tester")
    status_msg = MagicMock()

    media_bytes, output_path = await completion_helpers.handle_task_completion(
        context=SimpleNamespace(bot=MagicMock(), bot_data={}),
        chat_id=123,
        internal_user_id=456,
        prompt="prompt",
        task_type="image",
        registry_task_id="registry-seam",
        backend_task_id="backend-seam",
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
    assert download_output.await_args.kwargs["registry_task_id"] == "registry-seam"
    assert download_output.await_args.kwargs["backend_task_id"] == "backend-seam"
    assert download_output.await_args.kwargs["extra_outputs"] is None
    send_result_media.assert_awaited_once()
    assert send_result_media.await_args.kwargs["task_id"] == "registry-seam"
    cleanup_status.assert_awaited_once_with(
        status_msg=status_msg,
        delete_status=True,
        send_result=True,
    )


@pytest.mark.asyncio
async def test_handle_task_completion_uses_module_default_completion_helpers(monkeypatch):
    download_output = AsyncMock(
        return_value=TaskSuccessPersistenceResult(
            media_bytes=b"video-bytes",
            output_file="saved-output.mp4",
            width=None,
            height=None,
            duration=5,
        )
    )
    send_result_media = AsyncMock()
    cleanup_status = AsyncMock()
    monkeypatch.setattr(
        "src.services.task_service_completion.download_and_log_task_output",
        download_output,
    )
    monkeypatch.setattr(
        "src.services.task_service_completion.send_result_media",
        send_result_media,
    )
    monkeypatch.setattr(
        "src.services.task_service_completion.cleanup_completion_status_message",
        cleanup_status,
    )

    status_msg = MagicMock()
    user_logger = SimpleNamespace(username="tester")

    media_bytes, output_path = await completion_helpers.handle_task_completion(
        context=SimpleNamespace(bot=MagicMock(), bot_data={}),
        chat_id=123,
        internal_user_id=456,
        prompt="prompt",
        task_type="custom_video",
        registry_task_id="registry-explicit",
        backend_task_id="backend-explicit",
        saved_input_images=["input.png"],
        user_logger=user_logger,
        is_video=True,
        send_result=True,
        reply_markup=None,
        status_msg=status_msg,
        delete_status=True,
        caption="done",
        allow_contribute=True,
    )

    assert media_bytes == b"video-bytes"
    assert output_path == "saved-output.mp4"
    download_output.assert_awaited_once()
    assert download_output.await_args.kwargs["extra_outputs"] is None
    send_result_media.assert_awaited_once()
    cleanup_status.assert_awaited_once_with(
        status_msg=status_msg,
        delete_status=True,
        send_result=True,
    )


@pytest.mark.asyncio
async def test_handle_task_completion_merges_wan22_result_meta_into_extra_outputs(
    monkeypatch,
):
    download_output = AsyncMock(
        return_value=TaskSuccessPersistenceResult(
            media_bytes=b"video-bytes",
            output_file="saved-output.mp4",
            width=None,
            height=None,
            duration=5,
        )
    )
    send_result_media = AsyncMock()
    cleanup_status = AsyncMock()
    monkeypatch.setattr(
        "src.services.task_service_completion.download_and_log_task_output",
        download_output,
    )
    monkeypatch.setattr(
        "src.services.task_service_completion.send_result_media",
        send_result_media,
    )
    monkeypatch.setattr(
        "src.services.task_service_completion.cleanup_completion_status_message",
        cleanup_status,
    )

    user_logger = SimpleNamespace(username="tester")
    status_msg = MagicMock()

    media_bytes, output_path = await completion_helpers.handle_task_completion(
        context=SimpleNamespace(bot=MagicMock(), bot_data={}),
        chat_id=123,
        internal_user_id=456,
        prompt="prompt",
        task_type=MODE_WAN22_VIDEO_V2,
        registry_task_id="registry-wan22",
        backend_task_id="backend-wan22",
        saved_input_images=["start.png", "end.png"],
        user_logger=user_logger,
        is_video=True,
        send_result=True,
        reply_markup=None,
        status_msg=status_msg,
        delete_status=True,
        caption="done",
        allow_contribute=True,
        result_meta={
            "wan22_resolution_preset": "hd",
            "wan22_negative_prompt": "neg",
            "wan22_use_end_frame": True,
        },
        extra_outputs={"last_frame": {"path": "tail.png"}},
    )

    assert media_bytes == b"video-bytes"
    assert output_path == "saved-output.mp4"
    download_output.assert_awaited_once()
    assert download_output.await_args.kwargs["extra_outputs"] == {
        "last_frame": {"path": "tail.png"},
        "_wan22_context": {
            "wan22_resolution_preset": "hd",
            "wan22_negative_prompt": "neg",
            "wan22_use_end_frame": True,
        },
    }
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
        "src.core.task_core_persistence.persist_successful_task_result",
        persist_mock,
    )

    result = await completion_helpers.download_and_log_task_output(
        internal_user_id=456,
        username="tester",
        prompt="prompt",
        task_type="image",
        registry_task_id="registry-2",
        backend_task_id="backend-2",
        saved_input_images=["input.png"],
        is_video=False,
        allow_contribute=True,
        extra_outputs={"last_frame": {"path": "last.png"}},
        billing_resolution="1024",
        requested_duration=None,
    )
    assert result.media_bytes == b"image-bytes"
    assert result.output_file == "saved-output.png"
    assert result.width == 768
    assert result.height == 1024
    assert result.duration is None
    assert result.extra_outputs is None
    persist_mock.assert_awaited_once()
    kwargs = persist_mock.await_args.kwargs
    assert kwargs["username"] == "tester"
    assert kwargs["task_type"] == "image"
    assert kwargs["extra_outputs"] == {"last_frame": {"path": "last.png"}}
    assert kwargs["postprocess_plan"] == TaskPersistencePostprocessPlan(
        source="bot",
        refresh_user_group_after_log=True,
    )


def test_build_result_reply_markup_injects_gallery_button_when_missing():
    custom_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("自定义", callback_data="custom_action")]]
    )

    final_markup = tg_runtime_helpers.build_result_reply_markup(
        task_type="custom_video",
        task_id="task-3",
        allow_contribute=True,
        reply_markup=custom_markup,
    )

    first_row = final_markup.inline_keyboard[0]
    assert first_row[0].callback_data == "submit_gallery_task-3"


def test_build_result_reply_markup_supports_wan22_video_v2_gallery_button():
    final_markup = tg_runtime_helpers.build_result_reply_markup(
        task_type=MODE_WAN22_VIDEO_V2,
        task_id="task-wan22",
        allow_contribute=True,
        reply_markup=None,
        result_meta={"wan22_resolution_preset": "hd"},
    )

    first_row = final_markup.inline_keyboard[0]
    assert first_row[0].callback_data == "submit_gallery_task-wan22"
    assert first_row[1].callback_data == "wan22v2_extend:task-wan22"


@pytest.mark.parametrize(
    "task_type",
    ["scail2_action_transfer", "scail2_video_replacement", "scail2_face_swap_v2"],
)
def test_build_result_reply_markup_supports_scail2_gallery_button(task_type):
    final_markup = tg_runtime_helpers.build_result_reply_markup(
        task_type=task_type,
        task_id="task-scail2",
        allow_contribute=True,
        reply_markup=None,
    )

    first_row = final_markup.inline_keyboard[0]
    assert first_row[0].callback_data == "submit_gallery_task-scail2"


def test_build_result_reply_markup_supports_wan22_video_v2_non_first_segment_buttons():
    final_markup = tg_runtime_helpers.build_result_reply_markup(
        task_type=MODE_WAN22_VIDEO_V2,
        task_id="task-wan22-2",
        allow_contribute=True,
        reply_markup=None,
        result_meta={
            "wan22_resolution_preset": "hd",
            "wan22_prev_task_id": "task-wan22-1",
            "wan22_chain_task_ids": ["task-wan22-1"],
        },
    )

    first_row = final_markup.inline_keyboard[0]
    second_row = final_markup.inline_keyboard[1]
    assert [btn.callback_data for btn in first_row] == [
        "submit_gallery_task-wan22-2",
        "wan22v2_regenerate:task-wan22-2",
        "wan22v2_extend:task-wan22-2",
    ]
    assert second_row[0].callback_data == "wan22v2_stitch_chain:task-wan22-2"


def test_record_result_message_meta_uses_special_mode_mapping_for_face_swap():
    context = SimpleNamespace(bot_data={})
    sent_msg = SimpleNamespace(message_id=42)

    tg_runtime_helpers.record_result_message_meta(
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


def test_record_result_message_meta_merges_result_meta():
    context = SimpleNamespace(bot_data={})
    sent_msg = SimpleNamespace(message_id=77)

    tg_runtime_helpers.record_result_message_meta(
        context=context,
        sent_msg=sent_msg,
        task_type=MODE_WAN22_VIDEO_V2,
        prompt="prompt",
        task_id="task-77",
        result_meta={
            "wan22_resolution_preset": "standard",
            "wan22_prev_task_id": "task-1",
        },
    )

    assert context.bot_data["msg_meta_77"]["wan22_resolution_preset"] == "standard"
    assert context.bot_data["msg_meta_77"]["wan22_prev_task_id"] == "task-1"


def test_build_pending_status_text_uses_queue_remaining_fallback():
    text = tg_progress_helpers.build_pending_status_text(
        info={"status": "pending", "queue_remaining": 3},
        vip_suffix="",
    )

    assert text == "⏳ 排队中... (第 3 位)"


@pytest.mark.asyncio
async def test_send_result_media_uses_photo_sender_and_records_meta(monkeypatch):
    sent_msg = SimpleNamespace(message_id=99)
    send_photo = AsyncMock(return_value=sent_msg)
    send_video = AsyncMock()
    monkeypatch.setattr("src.services.tg_task_runtime.robust_send_photo", send_photo)
    monkeypatch.setattr("src.services.tg_task_runtime.robust_send_video", send_video)

    context = SimpleNamespace(bot=MagicMock(), bot_data={})

    result = await tg_runtime_helpers.send_result_media(
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
        result_meta={"wan22_resolution_preset": "fast"},
    )

    assert result is sent_msg
    send_photo.assert_awaited_once()
    send_video.assert_not_awaited()
    kwargs = send_photo.await_args.kwargs
    assert kwargs["photo"] == b"image-bytes"
    assert kwargs["caption"] == "✅ 图片生成完成"
    assert context.bot_data["msg_meta_99"]["task_id"] == "task-5"
    assert context.bot_data["msg_meta_99"]["wan22_resolution_preset"] == "fast"


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

    await tg_runtime_helpers.cleanup_completion_status_message(
        status_msg=status_msg,
        delete_status=False,
        send_result=True,
    )
    await tg_runtime_helpers.cleanup_completion_status_message(
        status_msg=status_msg,
        delete_status=True,
        send_result=False,
    )
    delete_message.assert_not_awaited()

    await tg_runtime_helpers.cleanup_completion_status_message(
        status_msg=status_msg,
        delete_status=True,
        send_result=True,
    )
    delete_message.assert_awaited_once_with(status_msg)


@pytest.mark.asyncio
async def test_monitor_submitted_bot_task_uses_helper_monitor_seam(monkeypatch):
    monitor_progress = AsyncMock(return_value={"status": "done"})
    edit_status_text = AsyncMock()
    monkeypatch.setattr(
        "src.core.billing_core.get_user_priority_and_identity",
        AsyncMock(return_value=(5, "外门弟子", "金丹期")),
    )
    monkeypatch.setattr(
        "src.services.task_service_completion.monitor_bot_task_progress",
        monitor_progress,
    )

    result = await completion_helpers.monitor_submitted_bot_task(
        task_id="task-monitor",
        status_msg="status-msg",
        is_video=True,
        internal_user_id=456,
        monitor_func="monitor-func",
        edit_status_text_func=edit_status_text,
    )

    assert result == {"status": "done"}
    monitor_progress.assert_awaited_once_with(
        "task-monitor",
        "status-msg",
        is_video=True,
        monitor_func="monitor-func",
        identity_str="外门弟子",
        user_group="金丹期",
        edit_status_text_func=edit_status_text,
        lang="zh",
    )


@pytest.mark.asyncio
async def test_monitor_bot_task_progress_shows_cancel_button_only_while_pending():
    edit_status_text = AsyncMock()

    async def monitor_func(*_args, **_kwargs):
        yield {"status": "pending", "queue_pos": 0}
        yield {"status": "running", "progress": 42}
        yield {"status": "done", "progress": 100}

    result = await tg_runtime_helpers.monitor_task_progress(
        task_id="task-pending",
        status_msg="status-msg",
        is_video=False,
        monitor_func=monitor_func,
        edit_status_text_func=edit_status_text,
    )

    assert result == {"status": "done", "progress": 100}
    first_call = edit_status_text.await_args_list[0]
    second_call = edit_status_text.await_args_list[1]
    assert first_call.args == ("status-msg", "⏳ 排队中... (第 1 位)")
    assert isinstance(first_call.kwargs["reply_markup"], InlineKeyboardMarkup)
    assert (
        first_call.kwargs["reply_markup"].inline_keyboard[0][0].callback_data
        == "cancel_task_task-pending"
    )
    assert second_call.args == ("status-msg", "⏳ 正在生成，请耐心等待...")
    assert second_call.kwargs["reply_markup"] is None


@pytest.mark.asyncio
async def test_monitor_bot_task_progress_does_not_repeat_running_percent_updates():
    edit_status_text = AsyncMock()

    async def monitor_func(*_args, **_kwargs):
        yield {"status": "running", "progress": 10}
        yield {"status": "running", "progress": 42}
        yield {"status": "done", "progress": 100}

    result = await tg_runtime_helpers.monitor_task_progress(
        task_id="task-running",
        status_msg="status-msg",
        is_video=False,
        monitor_func=monitor_func,
        edit_status_text_func=edit_status_text,
    )

    assert result == {"status": "done", "progress": 100}
    edit_status_text.assert_awaited_once()
    assert edit_status_text.await_args.args == (
        "status-msg",
        "⏳ 正在生成，请耐心等待...",
    )


@pytest.mark.asyncio
async def test_complete_monitored_bot_task_preserves_supplied_user_logger(monkeypatch):
    handle_task_completion = AsyncMock(return_value=(b"video-bytes", "output.mp4"))
    monkeypatch.setattr(
        "src.services.task_service_completion.handle_task_completion",
        handle_task_completion,
    )

    user_logger = SimpleNamespace(username="tester")
    runtime_state = SimpleNamespace(actual_cost=9, registry_task_id="reg-1", task_submitted=True)
    message_spec = SimpleNamespace(
        completion_caption="done",
        missing_output_message="missing",
    )

    result = await completion_helpers.complete_monitored_bot_task(
        completion=BotTaskCompletionContext(
            context=SimpleNamespace(bot=MagicMock(), bot_data={}),
            chat_id=123,
            status_msg=MagicMock(),
            runtime_state=runtime_state,
            internal_user_id=456,
            username="tester",
            prompt="prompt",
            task_type="custom_video",
            registry_task_id="registry-complete",
            backend_task_id="backend-complete",
            saved_input_images=["input.png"],
            final_info={"status": "done", "extra_outputs": {"last_frame": {"path": "x"}}},
            is_video=True,
            message_spec=message_spec,
            user_logger=user_logger,
            send_result=True,
            reply_markup=None,
            delete_status=True,
            allow_contribute=True,
        ),
    )

    assert result == (b"video-bytes", "output.mp4")
    assert handle_task_completion.await_args.kwargs["user_logger"] is user_logger


@pytest.mark.asyncio
async def test_complete_monitored_bot_task_uses_default_handle_completion(monkeypatch):
    handle_task_completion = AsyncMock(return_value=(b"video-bytes", "output.mp4"))
    monkeypatch.setattr(
        "src.services.task_service_completion.handle_task_completion",
        handle_task_completion,
    )

    user_logger = SimpleNamespace(username="tester")
    runtime_state = SimpleNamespace(actual_cost=9, registry_task_id="reg-1", task_submitted=True)
    message_spec = SimpleNamespace(
        completion_caption="done",
        missing_output_message="missing",
    )

    result = await completion_helpers.complete_monitored_bot_task(
        completion=BotTaskCompletionContext(
            context=SimpleNamespace(bot=MagicMock(), bot_data={}),
            chat_id=123,
            status_msg=MagicMock(),
            runtime_state=runtime_state,
            internal_user_id=456,
            username="tester",
            prompt="prompt",
            task_type="custom_video",
            registry_task_id="registry-complete",
            backend_task_id="backend-complete",
            saved_input_images=["input.png"],
            final_info={"status": "done", "extra_outputs": {"last_frame": {"path": "x"}}},
            is_video=True,
            message_spec=message_spec,
            user_logger=user_logger,
            send_result=True,
            reply_markup=None,
            delete_status=True,
            allow_contribute=True,
            result_meta={"wan22_resolution_preset": "hd"},
        ),
    )

    assert result == (b"video-bytes", "output.mp4")
    kwargs = handle_task_completion.await_args.kwargs
    assert kwargs["user_logger"] is user_logger
    assert kwargs["result_meta"] == {"wan22_resolution_preset": "hd"}
    assert kwargs["extra_outputs"] == {"last_frame": {"path": "x"}}


@pytest.mark.asyncio
async def test_complete_monitored_bot_task_uses_default_finalize_failed(monkeypatch):
    finalize_failed = AsyncMock()
    monkeypatch.setattr(
        "src.services.task_service_completion.finalize_failed_task_for_bot",
        finalize_failed,
    )
    runtime_state = SimpleNamespace(actual_cost=9, registry_task_id="reg-1", task_submitted=True)
    message_spec = SimpleNamespace(
        completion_caption="done",
        missing_output_message="missing",
    )

    result = await completion_helpers.complete_monitored_bot_task(
        completion=BotTaskCompletionContext(
            context=SimpleNamespace(bot=MagicMock(), bot_data={}),
            chat_id=123,
            status_msg=MagicMock(),
            runtime_state=runtime_state,
            internal_user_id=456,
            username="tester",
            prompt="prompt",
            task_type="custom_video",
            registry_task_id="registry-complete",
            backend_task_id="backend-complete",
            saved_input_images=["input.png"],
            final_info=None,
            is_video=True,
            message_spec=message_spec,
            user_logger=SimpleNamespace(username="tester"),
            send_result=True,
            reply_markup=None,
            delete_status=True,
            allow_contribute=True,
        ),
    )

    assert result == (None, None)
    finalize_failed.assert_awaited_once_with(
        context=ANY,
        chat_id=123,
        status_msg=None,
        failure=BotTaskFailureContext(
            internal_user_id=456,
            username="tester",
            cost=9,
            should_refund=True,
            registry_task_id="reg-1",
            release_lock=True,
            explicit_user_message="missing",
        ),
    )


@pytest.mark.asyncio
async def test_finalize_cancelled_task_for_bot_uses_task_service_edit_seam(monkeypatch):
    finalize_cancel = AsyncMock(
        return_value=TaskCancellationFinalizationResult(
            refunded=True,
            user_message="任务已撤销",
        )
    )
    edit_text = AsyncMock()
    monkeypatch.setattr(
        "src.core.task_core_finalization.finalize_task_cancellation", finalize_cancel
    )
    monkeypatch.setattr("src.services.task_service_finalize.robust_edit_text", edit_text)

    result = await support.finalize_cancelled_task_for_bot(
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
async def test_deliver_bot_finalization_message_prefers_edit_status(monkeypatch):
    edit_text = AsyncMock()
    send_message = AsyncMock()
    monkeypatch.setattr("src.services.task_service_finalize.robust_edit_text", edit_text)
    monkeypatch.setattr("src.services.task_service_finalize.robust_send_message", send_message)

    await support.deliver_bot_finalization_message(
        context=SimpleNamespace(bot=MagicMock()),
        chat_id=123,
        status_msg="status-msg",
        finalization_result=TaskFailureFinalizationResult(
            refunded=True,
            user_message="失败消息",
        ),
        policy=support.build_bot_failure_presentation_policy(
            prefer_edit_status=True,
            fallback_to_send_message=False,
        ),
    )

    edit_text.assert_awaited_once_with("status-msg", "❌ 失败消息")
    send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_finalize_failed_task_for_bot_uses_task_service_send_message_seam(monkeypatch):
    finalize_failure = AsyncMock(
        return_value=TaskFailureFinalizationResult(
            refunded=True,
            user_message="系统错误：boom，已退还灵石",
        )
    )
    send_message = AsyncMock()
    monkeypatch.setattr(
        "src.core.task_core_finalization.finalize_task_failure", finalize_failure
    )
    monkeypatch.setattr("src.services.task_service_finalize.robust_send_message", send_message)

    context = SimpleNamespace(bot=MagicMock())
    result = await support.finalize_failed_task_for_bot(
        context=context,
        chat_id=123,
        status_msg=None,
        failure=BotTaskFailureContext(
            internal_user_id=456,
            username="tester",
            cost=5,
            should_refund=True,
            registry_task_id="reg-2",
            release_lock=True,
            error=RuntimeError("boom"),
            generic_error_prefix="系统错误",
        ),
    )

    assert "系统错误" in result.user_message
    send_message.assert_awaited_once_with(
        context.bot,
        123,
        f"❌ {result.user_message}",
    )


def test_build_bot_failure_presentation_policy_keeps_display_contract():
    policy = support.build_bot_failure_presentation_policy(
        message_prefix="⚠️",
        prefer_edit_status=True,
        fallback_to_send_message=False,
    )

    assert policy.message_prefix == "⚠️"
    assert policy.prefer_edit_status is True
    assert policy.fallback_to_send_message is False


@pytest.mark.asyncio
async def test_send_bot_warning_uses_task_service_send_message_seam(monkeypatch):
    send_message = AsyncMock()
    monkeypatch.setattr("src.services.task_service_finalize.robust_send_message", send_message)

    context = SimpleNamespace(bot=MagicMock())
    await support.send_bot_warning(context, 123, "warn")

    send_message.assert_awaited_once_with(context.bot, 123, "⚠️ warn")


@pytest.mark.asyncio
async def test_send_bot_domain_error_uses_task_service_send_message_seam(monkeypatch):
    send_message = AsyncMock()
    monkeypatch.setattr("src.services.task_service_finalize.robust_send_message", send_message)

    context = SimpleNamespace(bot=MagicMock())
    await support.send_bot_domain_error(context, 123, "bad")

    send_message.assert_awaited_once_with(context.bot, 123, "❌ bad")


@pytest.mark.asyncio
async def test_cleanup_runtime_state_if_needed_uses_core_cleanup_seam(monkeypatch):
    cleanup_runtime = AsyncMock()
    monkeypatch.setattr(
        "src.core.task_core_runtime.cleanup_task_runtime_state", cleanup_runtime
    )

    await support.cleanup_runtime_state_if_needed(
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
    acceleration_notice = AsyncMock(return_value="")
    finalize_cancel = AsyncMock(
        return_value=TaskCancellationFinalizationResult(
            refunded=True,
            user_message="任务已撤销，预扣的 5 灵石已全额退回。",
        )
    )
    cleanup_runtime = AsyncMock()

    monkeypatch.setattr(
        "src.services.task_service_generation_image.get_acceleration_notice",
        acceleration_notice,
    )
    monkeypatch.setattr(
        "src.services.task_service_flow.get_or_send_status_message",
        AsyncMock(return_value=status_msg),
    )
    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=456), False)),
    )
    monkeypatch.setattr(
        "src.services.task_service_flow.process_and_submit_task",
        AsyncMock(
            return_value={
                "cost": 5,
                "registry_task_id": "task-6",
                "saved_inputs": ["input.png"],
            }
        ),
    )
    monkeypatch.setattr(
        "src.services.task_service_flow.get_user_priority_and_identity",
        AsyncMock(return_value=(0, "user", "外门弟子")),
    )
    monkeypatch.setattr(
        "src.services.task_service_completion.monitor_bot_task_progress",
        AsyncMock(side_effect=BotTaskCancelled()),
    )
    monkeypatch.setattr(
        "src.core.task_core_finalization.finalize_task_cancellation",
        finalize_cancel,
    )
    monkeypatch.setattr(
        "src.core.task_core_runtime.cleanup_task_runtime_state",
        cleanup_runtime,
    )
    monkeypatch.setattr("src.services.task_service_finalize.robust_edit_text", AsyncMock())
    monkeypatch.setattr("src.services.task_service_finalize.robust_send_message", AsyncMock())

    context = SimpleNamespace(user_data={}, bot=MagicMock())
    result = await process_generation_task(
        context=context,
        chat_id=123,
        user_id=789,
        username="tester",
        prompt="prompt",
        images=["input.png"],
        is_video=False,
    )

    assert result == (None, None)
    acceleration_notice.assert_awaited_once_with(456, quota_manager=ANY)
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
        "src.services.task_service_generation_image.get_acceleration_notice",
        AsyncMock(return_value=""),
    )
    monkeypatch.setattr(
        "src.services.task_service_flow.get_or_send_status_message",
        AsyncMock(return_value=status_msg),
    )
    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=456), False)),
    )
    monkeypatch.setattr(
        "src.services.task_service_flow.process_and_submit_task",
        AsyncMock(
            return_value={
                "cost": 5,
                "registry_task_id": "task-7",
                "saved_inputs": ["input.png"],
            }
        ),
    )
    monkeypatch.setattr(
        "src.services.task_service_flow.get_user_priority_and_identity",
        AsyncMock(return_value=(0, "user", "外门弟子")),
    )
    monkeypatch.setattr(
        "src.services.task_service_completion.monitor_bot_task_progress",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    monkeypatch.setattr(
        "src.core.task_core_finalization.finalize_task_failure",
        finalize_failure,
    )
    monkeypatch.setattr(
        "src.core.task_core_runtime.cleanup_task_runtime_state",
        cleanup_runtime,
    )
    monkeypatch.setattr("src.services.task_service_finalize.robust_edit_text", AsyncMock())
    monkeypatch.setattr("src.services.task_service_finalize.robust_send_message", send_message)

    context = SimpleNamespace(user_data={}, bot=MagicMock())
    result = await process_generation_task(
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
    acceleration_notice = AsyncMock(return_value="")
    finalize_cancel = AsyncMock()
    cleanup_runtime = AsyncMock()

    async def fake_submit(*, submission, **_kwargs):
        submission.runtime_state.task_submitted = True
        submission.runtime_state.actual_cost = 12
        submission.runtime_state.registry_task_id = "task-ltx"
        return "task-ltx", ["input.png"]

    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=456), False)),
    )
    monkeypatch.setattr(
        "src.services.task_service_flow.submit_bot_task",
        AsyncMock(side_effect=fake_submit),
    )
    monkeypatch.setattr(
        "src.services.task_service_entrypoints_specialized.get_acceleration_notice",
        acceleration_notice,
    )
    monkeypatch.setattr(
        "src.services.task_service_flow.robust_reply_text",
        AsyncMock(return_value=msg),
    )
    monkeypatch.setattr("src.services.task_service_finalize.robust_edit_text", AsyncMock())
    monkeypatch.setattr(
        "src.services.task_service_completion.monitor_submitted_bot_task",
        AsyncMock(side_effect=BotTaskCancelled()),
    )
    monkeypatch.setattr(
        "src.services.task_service_finalize.finalize_cancelled_task_for_bot",
        finalize_cancel,
    )
    monkeypatch.setattr(
        "src.services.task_service_finalize.cleanup_runtime_state_if_needed",
        cleanup_runtime,
    )
    monkeypatch.setattr("src.services.task_service_finalize.robust_send_message", AsyncMock())

    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=123),
        effective_user=SimpleNamespace(id=789, username="tester"),
        effective_message=SimpleNamespace(),
    )
    context = SimpleNamespace(
        user_data={},
        bot=MagicMock(),
        t=lambda value, **_kwargs: value,
    )

    result = await process_ltx_video_task(
        update=update,
        context=context,
        prompt="prompt",
        image_path="input.png",
        cleanup=False,
    )

    assert result == (None, None)
    acceleration_notice.assert_awaited_once_with(456, quota_manager=ANY)
    finalize_cancel.assert_awaited_once()
    cleanup_runtime.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_ltx_video_task_includes_lora_context_in_inputs(monkeypatch):
    captured_flow = {}

    async def fake_run_bot_task_application(*, flow):
        captured_flow["flow"] = flow
        return (b"video-bytes", "task-ltx")

    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=456), False)),
    )
    monkeypatch.setattr(
        "src.services.task_service_entrypoints_specialized.get_acceleration_notice",
        AsyncMock(return_value=""),
    )
    monkeypatch.setattr(
        "src.services.task_service_entrypoints_specialized.run_bot_task_application",
        fake_run_bot_task_application,
    )

    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=123),
        effective_user=SimpleNamespace(id=789, username="tester"),
        effective_message=SimpleNamespace(),
    )
    context = SimpleNamespace(
        user_data={
            "ltx_video_resolution": "1280x704",
            "ltx_video_duration": "10s",
        },
        bot=MagicMock(),
        t=lambda value, **_kwargs: value,
    )

    result = await process_ltx_video_task(
        update=update,
        context=context,
        prompt="prompt",
        image_path="input.png",
        lora_name="ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors",
        lora_strength=0.8,
        cleanup=False,
    )

    assert result == (b"video-bytes", "task-ltx")
    flow = captured_flow["flow"]
    assert flow.request.inputs["lora_name"] == "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors"
    assert flow.request.inputs["lora_strength"] == 0.8


@pytest.mark.asyncio
async def test_process_video_task_template_entrypoint_uses_internal_user_id_for_notice_and_queue_text(
    monkeypatch,
):
    acceleration_notice = AsyncMock(return_value="")
    run_bot_task_application = AsyncMock(
        return_value=(b"video-bytes", "task-video-template")
    )

    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=456), False)),
    )
    monkeypatch.setattr(
        "src.services.task_service_entrypoints_video.resolve_custom_video_settings",
        AsyncMock(return_value=("512p", "5s", 512, 5)),
    )
    monkeypatch.setattr(
        "src.services.task_service_entrypoints_video.get_acceleration_notice",
        acceleration_notice,
    )
    monkeypatch.setattr(
        "src.services.task_service_entrypoints_video.run_bot_task_application",
        run_bot_task_application,
    )
    monkeypatch.setattr(
        "src.services.task_service_entrypoints_video.load_prompts",
        lambda: {},
    )

    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=123),
        effective_user=SimpleNamespace(id=789, username="tester"),
        effective_message=SimpleNamespace(),
    )
    context = SimpleNamespace(
        user_data={},
        bot=MagicMock(),
        t=lambda value, **_kwargs: value,
    )

    result = await video_entrypoints.process_video_task_template(
        update=update,
        context=context,
        image_path="input.png",
        mode="video_mode",
        default_prompt_key="video.prompt",
        default_prompt_text="default prompt",
    )

    assert result == (b"video-bytes", "task-video-template")
    acceleration_notice.assert_awaited_once_with(456, quota_manager=ANY)
    flow = run_bot_task_application.await_args.kwargs["flow"]
    submitted_status_builder = flow.presentation.submitted_status_builder
    assert "任务已提交，正在排队调度" in submitted_status_builder(6)


@pytest.mark.asyncio
async def test_process_generation_task_delegates_video_modes_to_image_to_video_entrypoint(
    monkeypatch,
):
    image_to_video_entry = AsyncMock(return_value=(b"video-bytes", "task-image-to-video"))
    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=456), False)),
    )
    monkeypatch.setattr(
        "src.services.task_service_generation_image.process_image_to_video_generation_task",
        image_to_video_entry,
    )

    context = SimpleNamespace(user_data={}, bot=MagicMock())
    result = await process_generation_task(
        context=context,
        chat_id=123,
        user_id=789,
        username="tester",
        prompt="prompt",
        images=["input.png"],
        is_video=True,
        task_type=MODE_IMAGE_TO_VIDEO,
        resolution="720p",
        duration="8s",
        lora_name="BreastGrow",
    )

    assert result == (b"video-bytes", "task-image-to-video")
    image_to_video_entry.assert_awaited_once_with(
        context=context,
        chat_id=123,
        user_id=789,
        username="tester",
        prompt="prompt",
        images=["input.png"],
        resolution="720p",
        duration="8s",
        status_msg_id=None,
        delete_status=True,
        task_type=MODE_IMAGE_TO_VIDEO,
        cleanup=True,
        send_result=True,
        deduct_quota=True,
        reply_markup=None,
        lora_name="BreastGrow",
        lora_strength=1.0,
        allow_contribute=True,
        source_post_id=None,
    )


@pytest.mark.asyncio
async def test_process_wan22_video_v2_task_builds_expected_inputs(monkeypatch):
    captured_flow = {}

    async def fake_run_bot_task_application(*, flow):
        captured_flow["flow"] = flow
        return (b"video-bytes", "task-wan22")

    monkeypatch.setattr(
        "src.services.wan22_aio_video_generation.resolve_internal_user_id",
        AsyncMock(return_value=456),
    )
    monkeypatch.setattr(
        "src.services.wan22_aio_video_generation.get_acceleration_notice",
        AsyncMock(return_value=""),
    )
    monkeypatch.setattr(
        "src.services.wan22_aio_video_generation.run_bot_task_application",
        fake_run_bot_task_application,
    )

    context = SimpleNamespace(user_data={}, bot=MagicMock(), t=lambda key, **kwargs: key)
    result = await process_wan22_video_v2_task(
        context=context,
        chat_id=123,
        user_id=789,
        username="tester",
        prompt="positive",
        negative_prompt="negative",
        images=["start.png", "end.png"],
        use_end_frame=True,
        cleanup=False,
    )

    assert result == (b"video-bytes", "task-wan22")
    flow = captured_flow["flow"]
    assert flow.request.task_type == MODE_WAN22_VIDEO_V2
    assert flow.request.inputs["images"] == ["start.png", "end.png"]
    assert flow.request.inputs["negative_prompt"] == "negative"
    assert flow.request.inputs["use_end_frame"] is True
    assert flow.request.inputs["upscale"] is False
    assert flow.request.inputs["extract_last_frame"] is True
    assert flow.billing.requested_duration == 5

@pytest.mark.asyncio
async def test_process_face_video_task_uses_finalize_task_failure(monkeypatch):
    status_msg = MagicMock()
    acceleration_notice = AsyncMock(return_value="")
    finalize_failure = AsyncMock(
        return_value=TaskFailureFinalizationResult(
            refunded=True,
            user_message="系统错误：boom，已退还灵石",
        )
    )
    cleanup_runtime = AsyncMock()

    async def fake_submit(*, submission, **_kwargs):
        submission.runtime_state.task_submitted = True
        submission.runtime_state.actual_cost = 9
        submission.runtime_state.registry_task_id = "task-face-video"
        return "task-face-video", ["face.png", "video.mp4"]

    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=456), False)),
    )
    monkeypatch.setattr(
        "src.services.task_service_flow.submit_bot_task",
        AsyncMock(side_effect=fake_submit),
    )
    monkeypatch.setattr(
        "src.services.task_service_entrypoints_specialized.get_acceleration_notice",
        acceleration_notice,
    )
    monkeypatch.setattr(
        "src.services.task_service_flow.get_or_send_status_message",
        AsyncMock(return_value=status_msg),
    )
    monkeypatch.setattr(
        "src.services.task_service_completion.monitor_submitted_bot_task",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    monkeypatch.setattr(
        "src.services.task_service_finalize.finalize_failed_task_for_bot",
        finalize_failure,
    )
    monkeypatch.setattr(
        "src.services.task_service_finalize.cleanup_runtime_state_if_needed",
        cleanup_runtime,
    )
    monkeypatch.setattr("src.services.task_service_finalize.robust_send_message", AsyncMock())

    context = SimpleNamespace(user_data={}, bot=MagicMock())
    result = await process_face_video_task(
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
    acceleration_notice.assert_awaited_once_with(456, quota_manager=ANY)
    finalize_failure.assert_awaited_once()
    cleanup_runtime.assert_awaited_once()
