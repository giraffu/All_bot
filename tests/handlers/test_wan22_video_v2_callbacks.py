from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.constants import MODE_IMAGE_TO_VIDEO, MODE_WAN22_VIDEO_V2
from src.handlers.callbacks import wan22_video_v2_callbacks


def _build_update(query):
    return SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=12345, username="tester"),
        effective_chat=SimpleNamespace(id=10001),
    )


@pytest.mark.asyncio
async def test_regenerate_wan22_video_v2_callback_reuses_previous_segment_context(
    monkeypatch,
):
    safe_answer = AsyncMock()
    send_message = AsyncMock(return_value=SimpleNamespace(message_id=88))
    create_background_task = MagicMock()
    process_task = MagicMock(return_value=("bg-task",))

    monkeypatch.setattr(wan22_video_v2_callbacks, "safe_answer_query", safe_answer)
    monkeypatch.setattr(wan22_video_v2_callbacks, "robust_send_message", send_message)
    monkeypatch.setattr(
        wan22_video_v2_callbacks, "create_background_task", create_background_task
    )
    monkeypatch.setattr(
        wan22_video_v2_callbacks, "process_wan22_video_v2_task", process_task
    )
    monkeypatch.setattr(
        wan22_video_v2_callbacks,
        "load_owned_wan22_history",
        AsyncMock(
            side_effect=[
                SimpleNamespace(prompt="current prompt", type=MODE_WAN22_VIDEO_V2),
                SimpleNamespace(),
            ]
        ),
    )
    monkeypatch.setattr(
        wan22_video_v2_callbacks,
        "download_last_frame_to_fsm_temp",
        AsyncMock(return_value="/tmp/start.png"),
    )
    monkeypatch.setattr(
        wan22_video_v2_callbacks,
        "download_history_input_file_to_fsm_temp",
        AsyncMock(return_value="/tmp/end.png"),
    )

    message = SimpleNamespace(message_id=77)
    query = SimpleNamespace(data="wan22v2_regenerate", message=message)
    update = _build_update(query)
    context = SimpleNamespace(
        bot=MagicMock(),
        bot_data={
            "msg_meta_77": {
                "task_id": "task-3",
                "wan22_prev_task_id": "task-2",
                "wan22_chain_task_ids": ["task-1", "task-2"],
                "wan22_negative_prompt": "neg",
                "wan22_resolution_preset": "standard",
                "wan22_use_end_frame": True,
            }
        },
    )

    await wan22_video_v2_callbacks.regenerate_wan22_video_v2_callback(update, context)

    safe_answer.assert_awaited_once()
    process_task.assert_called_once()
    kwargs = process_task.call_args.kwargs
    assert kwargs["prompt"] == "current prompt"
    assert kwargs["negative_prompt"] == "neg"
    assert kwargs["images"] == ["/tmp/start.png", "/tmp/end.png"]
    assert kwargs["use_end_frame"] is True
    assert kwargs["status_msg_id"] == 88
    assert kwargs["result_meta"] == {
        "wan22_prev_task_id": "task-2",
        "wan22_chain_task_ids": ["task-1", "task-2"],
    }
    create_background_task.assert_called_once_with(context, ("bg-task",))


@pytest.mark.asyncio
async def test_regenerate_legacy_video_lora_callback_reuses_lora_context(
    monkeypatch,
):
    safe_answer = AsyncMock()
    send_message = AsyncMock(return_value=SimpleNamespace(message_id=88))
    create_background_task = MagicMock()
    process_task = MagicMock(return_value=("bg-task",))

    monkeypatch.setattr(wan22_video_v2_callbacks, "safe_answer_query", safe_answer)
    monkeypatch.setattr(wan22_video_v2_callbacks, "robust_send_message", send_message)
    monkeypatch.setattr(
        wan22_video_v2_callbacks, "create_background_task", create_background_task
    )
    monkeypatch.setattr(
        wan22_video_v2_callbacks, "process_image_to_video_task", process_task
    )
    monkeypatch.setattr(
        wan22_video_v2_callbacks,
        "load_owned_wan22_history",
        AsyncMock(
            side_effect=[
                SimpleNamespace(
                    prompt="[standard|5s] [模型: BreastGrow] current prompt",
                    requested_duration=5,
                    type=MODE_IMAGE_TO_VIDEO,
                ),
                SimpleNamespace(),
            ]
        ),
    )
    monkeypatch.setattr(
        wan22_video_v2_callbacks,
        "download_last_frame_to_fsm_temp",
        AsyncMock(return_value="/tmp/start.png"),
    )

    message = SimpleNamespace(message_id=77)
    query = SimpleNamespace(data="wan22v2_regenerate", message=message)
    update = _build_update(query)
    context = SimpleNamespace(
        bot=MagicMock(),
        bot_data={
            "msg_meta_77": {
                "task_id": "task-3",
                "wan22_prev_task_id": "task-2",
                "wan22_chain_task_ids": ["task-1", "task-2"],
                "wan22_negative_prompt": "neg",
                "wan22_resolution_preset": "standard",
                "wan22_use_end_frame": False,
                "lora_name": "BreastGrow",
                "lora_strength": 1.0,
            }
        },
    )

    await wan22_video_v2_callbacks.regenerate_wan22_video_v2_callback(update, context)

    safe_answer.assert_awaited_once()
    process_task.assert_called_once()
    kwargs = process_task.call_args.kwargs
    assert kwargs["prompt"] == "current prompt"
    assert kwargs["negative_prompt"] == "neg"
    assert kwargs["images"] == ["/tmp/start.png"]
    assert kwargs["use_end_frame"] is False
    assert kwargs["resolution_preset"] == "standard"
    assert kwargs["wan22_prev_task_id"] == "task-2"
    assert kwargs["wan22_chain_task_ids"] == ["task-1", "task-2"]
    assert kwargs["task_type"] == MODE_IMAGE_TO_VIDEO
    assert kwargs["lora_name"] == "BreastGrow"
    assert kwargs["lora_strength"] == 1.0
    create_background_task.assert_called_once_with(context, ("bg-task",))


@pytest.mark.asyncio
async def test_regenerate_callback_recovers_context_from_task_bound_callback(
    monkeypatch,
):
    safe_answer = AsyncMock()
    send_message = AsyncMock(return_value=SimpleNamespace(message_id=88))
    create_background_task = MagicMock()
    process_task = MagicMock(return_value=("bg-task",))
    current_history = SimpleNamespace(
        prompt="current prompt",
        type=MODE_WAN22_VIDEO_V2,
        extra_outputs={
            "_wan22_context": {
                "wan22_prev_task_id": "task-2",
                "wan22_chain_task_ids": ["task-1", "task-2"],
                "wan22_negative_prompt": "neg",
                "wan22_resolution_preset": "standard",
                "wan22_use_end_frame": False,
            }
        },
    )

    monkeypatch.setattr(wan22_video_v2_callbacks, "safe_answer_query", safe_answer)
    monkeypatch.setattr(wan22_video_v2_callbacks, "robust_send_message", send_message)
    monkeypatch.setattr(
        wan22_video_v2_callbacks, "create_background_task", create_background_task
    )
    monkeypatch.setattr(
        wan22_video_v2_callbacks, "process_wan22_video_v2_task", process_task
    )
    load_history_mock = AsyncMock(side_effect=[current_history, SimpleNamespace()])
    monkeypatch.setattr(
        wan22_video_v2_callbacks,
        "load_owned_wan22_history",
        load_history_mock,
    )
    monkeypatch.setattr(
        wan22_video_v2_callbacks,
        "download_last_frame_to_fsm_temp",
        AsyncMock(return_value="/tmp/start.png"),
    )

    message = SimpleNamespace(message_id=77)
    query = SimpleNamespace(data="wan22v2_regenerate:task-3", message=message)
    update = _build_update(query)
    context = SimpleNamespace(bot=MagicMock(), bot_data={})

    await wan22_video_v2_callbacks.regenerate_wan22_video_v2_callback(update, context)

    assert [call.kwargs["task_id"] for call in load_history_mock.await_args_list] == [
        "task-3",
        "task-2",
    ]
    process_task.assert_called_once()
    kwargs = process_task.call_args.kwargs
    assert kwargs["prompt"] == "current prompt"
    assert kwargs["negative_prompt"] == "neg"
    assert kwargs["resolution_preset"] == "standard"
    assert kwargs["result_meta"] == {
        "wan22_prev_task_id": "task-2",
        "wan22_chain_task_ids": ["task-1", "task-2"],
    }
    create_background_task.assert_called_once_with(context, ("bg-task",))


@pytest.mark.asyncio
async def test_stitch_wan22_video_v2_callback_uses_full_chain(monkeypatch):
    safe_answer = AsyncMock()
    send_message = AsyncMock()
    send_video = AsyncMock(return_value=SimpleNamespace(message_id=99))
    edit_reply_markup = AsyncMock()
    histories = [
        SimpleNamespace(user_id=321, task_id="task-1"),
        SimpleNamespace(user_id=321, task_id="task-2"),
        SimpleNamespace(user_id=321, task_id="task-3"),
    ]

    monkeypatch.setattr(wan22_video_v2_callbacks, "safe_answer_query", safe_answer)
    monkeypatch.setattr(wan22_video_v2_callbacks, "robust_send_message", send_message)
    monkeypatch.setattr(wan22_video_v2_callbacks, "robust_send_video", send_video)
    monkeypatch.setattr(
        wan22_video_v2_callbacks, "robust_edit_reply_markup", edit_reply_markup
    )
    monkeypatch.setattr(
        wan22_video_v2_callbacks,
        "load_owned_wan22_history",
        AsyncMock(side_effect=histories),
    )
    stitch_mock = AsyncMock(
        return_value=SimpleNamespace(
            video_bytes=b"stitched-video",
            task_id="stitched-task",
            task_type=MODE_IMAGE_TO_VIDEO,
            prompt="stitched prompt",
            extra_outputs={"wan22_chain_stitch": {"segment_count": 3}},
            allow_contribute=True,
            segment_count=3,
        )
    )
    monkeypatch.setattr(
        wan22_video_v2_callbacks, "stitch_histories_and_create_history", stitch_mock
    )

    message = SimpleNamespace(
        message_id=77,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔗 完成拼接", callback_data="wan22v2_stitch_chain")]]
        ),
    )
    query = SimpleNamespace(data="wan22v2_stitch_chain", message=message)
    update = _build_update(query)
    context = SimpleNamespace(
        bot=MagicMock(),
        bot_data={
            "msg_meta_77": {
                "task_id": "task-3",
                "wan22_chain_task_ids": ["task-1", "task-2"],
            }
        },
    )

    await wan22_video_v2_callbacks.stitch_wan22_video_v2_callback(update, context)

    stitch_mock.assert_awaited_once()
    stitched_histories = stitch_mock.await_args.kwargs["histories"]
    assert len(stitched_histories) == 3
    assert stitch_mock.await_args.kwargs["user_id"] == 321
    assert stitch_mock.await_args.kwargs["source_task_id"] == "task-3"
    assert stitch_mock.await_args.kwargs["source"] == "bot"
    send_video.assert_awaited_once()
    assert send_video.await_args.kwargs["caption"] == "✅ 3 段视频已拼接完成"
    reply_markup = send_video.await_args.kwargs["reply_markup"]
    first_row = reply_markup.inline_keyboard[0]
    assert first_row[0].callback_data == "submit_gallery_stitched-task"
    assert context.bot_data["msg_meta_99"]["task_id"] == "stitched-task"
    assert context.bot_data["msg_meta_99"]["prompt"] == "stitched prompt"
    edit_reply_markup.assert_awaited_once()
