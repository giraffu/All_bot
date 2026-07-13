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


def _build_wan22_seed(fsm_data: dict):
    return SimpleNamespace(fsm_data=fsm_data)


def _build_stitch_plan(histories):
    return SimpleNamespace(
        histories=histories,
        internal_user_id=321,
        source_task_id="task-3",
        full_task_ids=[history.task_id for history in histories],
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
    prepare_seed = AsyncMock(
        return_value=_build_wan22_seed(
            {
                "start_image_path": "/tmp/start.png",
                "end_image_path": "/tmp/end.png",
                "use_end_frame": True,
                "resolution_preset": "standard",
                "duration": 5,
                "prompt": "current prompt",
                "negative_prompt": "neg",
                "extension_prev_task_id": "task-2",
                "extension_task_type": MODE_WAN22_VIDEO_V2,
                "chain_task_ids": ["task-1", "task-2"],
            }
        )
    )
    monkeypatch.setattr(
        wan22_video_v2_callbacks,
        "prepare_wan22_regeneration_fsm_data",
        prepare_seed,
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
    prepare_seed.assert_awaited_once_with(
        current_task_id="task-3",
        telegram_user_id=12345,
        username="tester",
        message_meta={
            "task_id": "task-3",
            "wan22_prev_task_id": "task-2",
            "wan22_chain_task_ids": ["task-1", "task-2"],
            "wan22_negative_prompt": "neg",
            "wan22_resolution_preset": "standard",
            "wan22_use_end_frame": True,
        },
    )
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
    prepare_seed = AsyncMock(
        return_value=_build_wan22_seed(
            {
                "start_image_path": "/tmp/start.png",
                "end_image_path": None,
                "use_end_frame": False,
                "resolution_preset": "standard",
                "duration": 5,
                "prompt": "current prompt",
                "negative_prompt": "neg",
                "extension_prev_task_id": "task-2",
                "extension_task_type": MODE_IMAGE_TO_VIDEO,
                "chain_task_ids": ["task-1", "task-2"],
                "lora_name": "BreastGrow",
                "lora_strength": 1.0,
            }
        )
    )
    monkeypatch.setattr(
        wan22_video_v2_callbacks,
        "prepare_wan22_regeneration_fsm_data",
        prepare_seed,
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
    prepare_seed.assert_awaited_once_with(
        current_task_id="task-3",
        telegram_user_id=12345,
        username="tester",
        message_meta={
            "task_id": "task-3",
            "wan22_prev_task_id": "task-2",
            "wan22_chain_task_ids": ["task-1", "task-2"],
            "wan22_negative_prompt": "neg",
            "wan22_resolution_preset": "standard",
            "wan22_use_end_frame": False,
            "lora_name": "BreastGrow",
            "lora_strength": 1.0,
        },
    )
    create_background_task.assert_called_once_with(context, ("bg-task",))


@pytest.mark.asyncio
async def test_regenerate_callback_recovers_context_from_task_bound_callback(
    monkeypatch,
):
    safe_answer = AsyncMock()
    send_message = AsyncMock(return_value=SimpleNamespace(message_id=88))
    create_background_task = MagicMock()
    process_task = MagicMock(return_value=("bg-task",))
    prepare_seed = AsyncMock(
        return_value=_build_wan22_seed(
            {
                "start_image_path": "/tmp/start.png",
                "end_image_path": None,
                "use_end_frame": False,
                "resolution_preset": "standard",
                "duration": 5,
                "prompt": "current prompt",
                "negative_prompt": "neg",
                "extension_prev_task_id": "task-2",
                "extension_task_type": MODE_WAN22_VIDEO_V2,
                "chain_task_ids": ["task-1", "task-2"],
            }
        )
    )

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
        "prepare_wan22_regeneration_fsm_data",
        prepare_seed,
    )

    message = SimpleNamespace(message_id=77)
    query = SimpleNamespace(data="wan22v2_regenerate:task-3", message=message)
    update = _build_update(query)
    context = SimpleNamespace(bot=MagicMock(), bot_data={})

    await wan22_video_v2_callbacks.regenerate_wan22_video_v2_callback(update, context)

    prepare_seed.assert_awaited_once_with(
        current_task_id="task-3",
        telegram_user_id=12345,
        username="tester",
        message_meta={},
    )
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
    current_history = SimpleNamespace(user_id=321, task_id="task-3")
    previous_histories = [
        SimpleNamespace(user_id=321, task_id="task-1"),
        SimpleNamespace(user_id=321, task_id="task-2"),
    ]
    histories = [*previous_histories, current_history]

    monkeypatch.setattr(wan22_video_v2_callbacks, "safe_answer_query", safe_answer)
    monkeypatch.setattr(wan22_video_v2_callbacks, "robust_send_message", send_message)
    monkeypatch.setattr(wan22_video_v2_callbacks, "robust_send_video", send_video)
    monkeypatch.setattr(
        wan22_video_v2_callbacks, "robust_edit_reply_markup", edit_reply_markup
    )
    monkeypatch.setattr(
        wan22_video_v2_callbacks, "build_wan22_stitch_plan", AsyncMock(
            return_value=_build_stitch_plan(histories)
        )
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
            [[
                InlineKeyboardButton(
                    "🔗 完成拼接",
                    callback_data="wan22v2_stitch_chain:task-3",
                )
            ]]
        ),
    )
    query = SimpleNamespace(data="wan22v2_stitch_chain:task-3", message=message)
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
    assert [history.task_id for history in stitched_histories] == [
        "task-1",
        "task-2",
        "task-3",
    ]
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


@pytest.mark.asyncio
async def test_stitch_callback_recovers_chain_from_task_bound_callback(monkeypatch):
    safe_answer = AsyncMock()
    send_message = AsyncMock()
    send_video = AsyncMock(return_value=SimpleNamespace(message_id=99))
    edit_reply_markup = AsyncMock()
    current_history = SimpleNamespace(
        user_id=321,
        task_id="task-3",
    )
    previous_histories = [
        SimpleNamespace(user_id=321, task_id="task-1"),
        SimpleNamespace(user_id=321, task_id="task-2"),
    ]
    histories = [*previous_histories, current_history]

    monkeypatch.setattr(wan22_video_v2_callbacks, "safe_answer_query", safe_answer)
    monkeypatch.setattr(wan22_video_v2_callbacks, "robust_send_message", send_message)
    monkeypatch.setattr(wan22_video_v2_callbacks, "robust_send_video", send_video)
    monkeypatch.setattr(
        wan22_video_v2_callbacks, "robust_edit_reply_markup", edit_reply_markup
    )
    build_plan_mock = AsyncMock(return_value=_build_stitch_plan(histories))
    monkeypatch.setattr(
        wan22_video_v2_callbacks,
        "build_wan22_stitch_plan",
        build_plan_mock,
    )
    stitch_mock = AsyncMock(
        return_value=SimpleNamespace(
            video_bytes=b"stitched-video",
            task_id="stitched-task",
            task_type=MODE_WAN22_VIDEO_V2,
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
            [[
                InlineKeyboardButton(
                    "🔗 完成拼接",
                    callback_data="wan22v2_stitch_chain:task-3",
                )
            ]]
        ),
    )
    query = SimpleNamespace(data="wan22v2_stitch_chain:task-3", message=message)
    update = _build_update(query)
    context = SimpleNamespace(bot=MagicMock(), bot_data={})

    await wan22_video_v2_callbacks.stitch_wan22_video_v2_callback(update, context)

    build_plan_mock.assert_awaited_once_with(
        current_task_id="task-3",
        telegram_user_id=12345,
        username="tester",
        message_meta={},
    )
    stitched_histories = stitch_mock.await_args.kwargs["histories"]
    assert [history.task_id for history in stitched_histories] == [
        "task-1",
        "task-2",
        "task-3",
    ]
    assert stitch_mock.await_args.kwargs["source_task_id"] == "task-3"
    send_video.assert_awaited_once()
