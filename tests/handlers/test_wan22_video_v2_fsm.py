import re
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock
import warnings

import pytest
from telegram.ext import ConversationHandler
from telegram.warnings import PTBUserWarning

from src.handlers.fsm import wan22_video_v2_fsm


def _build_user():
    return SimpleNamespace(
        id=12345,
        username="tester",
        full_name="Test User",
    )


def _build_message(text: str = "test prompt"):
    return SimpleNamespace(
        text=text,
        chat_id=10001,
    )


def _build_update_with_message(*, text: str = "test prompt"):
    user = _build_user()
    return SimpleNamespace(
        effective_user=user,
        effective_chat=SimpleNamespace(id=10001),
        message=_build_message(text=text),
        callback_query=None,
    )


def test_get_wan22_video_v2_fsm_handler_exposes_expected_entry_points():
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=PTBUserWarning)
        handler = wan22_video_v2_fsm.get_wan22_video_v2_fsm_handler()

    assert handler.name == "wan22_video_v2_fsm"
    assert len(handler.entry_points) == 5


def test_settings_callback_pattern_accepts_all_resolution_presets():
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=PTBUserWarning)
        handler = wan22_video_v2_fsm.get_wan22_video_v2_fsm_handler()

    setup_callback = handler.states[wan22_video_v2_fsm.Wan22VideoV2State.WAIT_SETUP][0]
    assert setup_callback.pattern.pattern == (
        wan22_video_v2_fsm.WAN22_VIDEO_V2_SETUP_ACTION_PATTERN
    )
    setup_pattern = re.compile(wan22_video_v2_fsm.WAN22_VIDEO_V2_SETUP_ACTION_PATTERN)
    assert setup_pattern.match("wan22v2_setup_mode_single")
    assert setup_pattern.match("wan22v2_setup_mode_end")
    assert setup_pattern.match("wan22v2_setup_confirm")
    for preset_key in wan22_video_v2_fsm.WAN22_VIDEO_V2_RESOLUTION_PRESETS:
        assert setup_pattern.match(f"wan22v2_setup_res_{preset_key}")
    assert not setup_pattern.match("wan22v2_setup_res_fast")

    settings_callback = handler.states[wan22_video_v2_fsm.Wan22VideoV2State.WAIT_SETTINGS][0]
    assert settings_callback.pattern.pattern == (
        wan22_video_v2_fsm.WAN22_VIDEO_V2_SETTINGS_ACTION_PATTERN
    )

    pattern = re.compile(wan22_video_v2_fsm.WAN22_VIDEO_V2_SETTINGS_ACTION_PATTERN)
    assert pattern.match("wan22v2_submit")
    for preset_key in wan22_video_v2_fsm.WAN22_VIDEO_V2_RESOLUTION_PRESETS:
        assert pattern.match(f"wan22v2_res_{preset_key}")
    assert not pattern.match("wan22v2_res_fast")

    entry_patterns = [
        getattr(entry, "pattern", None).pattern
        for entry in handler.entry_points
        if getattr(entry, "pattern", None)
    ]
    assert any(
        re.compile(pattern).match("wan22v2_extend:task-1")
        for pattern in entry_patterns
    )
    assert any(
        re.compile(pattern).match("wan22v2_regenerate:task-2")
        for pattern in entry_patterns
    )


def test_settings_keyboard_renders_resolution_presets_in_one_row():
    context = SimpleNamespace(lang="zh", t=lambda key, **kwargs: f"T:{key}")
    data = {"resolution_preset": "preview"}

    keyboard = wan22_video_v2_fsm._build_settings_keyboard(context, data)

    assert [
        button.callback_data
        for button in keyboard.inline_keyboard[0]
    ] == [
        "wan22v2_res_preview",
        "wan22v2_res_small",
        "wan22v2_res_standard",
        "wan22v2_res_hd",
    ]
    assert [button.text for button in keyboard.inline_keyboard[1]] == [
        "• 5 秒 (*1)",
        "8 秒 (*2)",
        "10 秒 (*3)",
    ]
    assert keyboard.inline_keyboard[2][0].callback_data == "wan22v2_submit"


@pytest.mark.asyncio
async def test_start_wan22_video_v2_initializes_defaults(monkeypatch):
    reply_mock = AsyncMock()
    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr(wan22_video_v2_fsm, "robust_reply_text", reply_mock)

    update = _build_update_with_message(text="🎬 图生视频v2")
    def translate(key, **kwargs):
        if key == "fsm.wan22_video_v2.setup_text":
            return "设置面板：请直接发送起始帧图片。"
        return f"T:{key}"

    context = SimpleNamespace(user_data={}, lang="zh", t=translate)

    result = await wan22_video_v2_fsm.start_wan22_video_v2(update, context)

    assert result == wan22_video_v2_fsm.Wan22VideoV2State.WAIT_SETUP
    assert context.user_data["in_conversation"] == wan22_video_v2_fsm.WAN22_VIDEO_V2_CONVERSATION_TAG
    assert context.user_data["wan22_video_v2_data"]["use_end_frame"] is False
    assert (
        context.user_data["wan22_video_v2_data"]["resolution_preset"]
        == wan22_video_v2_fsm.WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET
    )
    reply_mock.assert_awaited_once()
    assert "请直接发送起始帧图片" in reply_mock.await_args.args[1]
    keyboard = reply_mock.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].callback_data == "wan22v2_setup_mode_single"
    assert keyboard.inline_keyboard[0][0].text.startswith("✅ ")
    assert keyboard.inline_keyboard[0][1].callback_data == "wan22v2_setup_mode_end"
    assert [
        button.callback_data
        for button in keyboard.inline_keyboard[1]
    ] == [
        "wan22v2_setup_res_preview",
        "wan22v2_setup_res_small",
        "wan22v2_setup_res_standard",
        "wan22v2_setup_res_hd",
    ]
    assert [button.text for button in keyboard.inline_keyboard[2]] == [
        "✅ 5 秒 (*1)",
        "8 秒 (*2)",
        "10 秒 (*3)",
    ]
    callback_data = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
    ]
    assert "wan22v2_setup_confirm" not in callback_data
    assert "发送起始帧图片" in reply_mock.await_args.args[1]


@pytest.mark.asyncio
async def test_handle_initial_setup_action_updates_frame_mode_and_resolution(monkeypatch):
    edit_mock = AsyncMock()
    monkeypatch.setattr(wan22_video_v2_fsm, "robust_edit_text", edit_mock)

    context = SimpleNamespace(
        user_data={
            "wan22_video_v2_data": {
                "start_image_path": None,
                "end_image_path": "/tmp/old-end.png",
                "use_end_frame": False,
                "resolution_preset": "preview",
            }
        },
        lang="zh",
        t=lambda key, **kwargs: f"T:{key}",
    )

    mode_query = SimpleNamespace(
        data="wan22v2_setup_mode_end",
        answer=AsyncMock(),
        message=SimpleNamespace(),
    )
    mode_result = await wan22_video_v2_fsm.handle_initial_setup_action(
        SimpleNamespace(callback_query=mode_query),
        context,
    )

    assert mode_result == wan22_video_v2_fsm.Wan22VideoV2State.WAIT_SETUP
    assert context.user_data["wan22_video_v2_data"]["use_end_frame"] is True
    assert context.user_data["wan22_video_v2_data"]["end_image_path"] is None
    mode_query.answer.assert_awaited_once()

    res_query = SimpleNamespace(
        data="wan22v2_setup_res_hd",
        answer=AsyncMock(),
        message=SimpleNamespace(),
    )
    res_result = await wan22_video_v2_fsm.handle_initial_setup_action(
        SimpleNamespace(callback_query=res_query),
        context,
    )

    assert res_result == wan22_video_v2_fsm.Wan22VideoV2State.WAIT_SETUP
    assert context.user_data["wan22_video_v2_data"]["resolution_preset"] == "hd"
    assert edit_mock.await_count == 2


@pytest.mark.asyncio
async def test_handle_initial_setup_confirm_requests_start_image(monkeypatch):
    edit_mock = AsyncMock()
    monkeypatch.setattr(wan22_video_v2_fsm, "robust_edit_text", edit_mock)

    query = SimpleNamespace(
        data="wan22v2_setup_confirm",
        answer=AsyncMock(),
        message=SimpleNamespace(),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(
        user_data={
            "wan22_video_v2_data": {
                "start_image_path": None,
                "end_image_path": None,
                "use_end_frame": True,
                "resolution_preset": "standard",
            }
        },
        lang="zh",
        t=lambda key, **kwargs: f"T:{key}",
    )

    result = await wan22_video_v2_fsm.handle_initial_setup_action(update, context)

    assert result == wan22_video_v2_fsm.Wan22VideoV2State.WAIT_START_IMAGE
    query.answer.assert_awaited_once()
    edit_mock.assert_awaited_once_with(
        query.message,
        "T:fsm.wan22_video_v2.send_start_after_setup",
        parse_mode="Markdown",
    )


@pytest.mark.asyncio
async def test_setup_panel_accepts_start_image_without_confirm(monkeypatch):
    reply_mock = AsyncMock()
    download_mock = AsyncMock(return_value="/tmp/start.png")
    monkeypatch.setattr(wan22_video_v2_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        wan22_video_v2_fsm,
        "_download_image_to_temp",
        download_mock,
    )

    message = SimpleNamespace(
        document=None,
        photo=[SimpleNamespace(file_id="photo-file-id")],
        chat_id=10001,
    )
    update = SimpleNamespace(
        effective_user=_build_user(),
        message=message,
        callback_query=None,
    )
    context = SimpleNamespace(
        user_data={
            "wan22_video_v2_data": {
                "start_image_path": None,
                "end_image_path": None,
                "use_end_frame": False,
                "resolution_preset": "standard",
            }
        },
        lang="zh",
        t=lambda key, **kwargs: f"T:{key}",
    )

    result = await wan22_video_v2_fsm.receive_initial_setup_start_image(
        update,
        context,
    )

    assert result == wan22_video_v2_fsm.Wan22VideoV2State.WAIT_PROMPT
    assert context.user_data["wan22_video_v2_data"]["start_image_path"] == "/tmp/start.png"
    assert download_mock.await_args.kwargs["file_id"] == "photo-file-id"
    assert reply_mock.await_args_list[0].args[1] == (
        "T:fsm.wan22_video_v2.start_image_received"
    )
    assert reply_mock.await_args_list[1].args[1] == "T:fsm.wan22_video_v2.send_prompt"


@pytest.mark.asyncio
async def test_receive_start_image_single_frame_moves_to_prompt(monkeypatch):
    reply_mock = AsyncMock()
    download_mock = AsyncMock(return_value="/tmp/start.png")
    monkeypatch.setattr(wan22_video_v2_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(wan22_video_v2_fsm, "_download_image_to_temp", download_mock)

    message = SimpleNamespace(
        document=None,
        photo=[SimpleNamespace(file_id="start-file")],
    )
    update = SimpleNamespace(message=message, callback_query=None)
    context = SimpleNamespace(
        user_data={
            "wan22_video_v2_data": {
                "start_image_path": None,
                "end_image_path": None,
                "use_end_frame": False,
                "resolution_preset": "preview",
            }
        },
        t=lambda key, **kwargs: f"T:{key}",
    )

    result = await wan22_video_v2_fsm.receive_start_image(update, context)

    assert result == wan22_video_v2_fsm.Wan22VideoV2State.WAIT_PROMPT
    assert context.user_data["wan22_video_v2_data"]["start_image_path"] == "/tmp/start.png"
    download_mock.assert_awaited_once()
    assert reply_mock.await_args_list[0].args[1] == "T:fsm.wan22_video_v2.start_image_received"
    assert reply_mock.await_args_list[1].args[1] == "T:fsm.wan22_video_v2.send_prompt"


@pytest.mark.asyncio
async def test_receive_start_image_end_frame_mode_waits_for_end_image(monkeypatch):
    reply_mock = AsyncMock()
    download_mock = AsyncMock(return_value="/tmp/start.png")
    monkeypatch.setattr(wan22_video_v2_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(wan22_video_v2_fsm, "_download_image_to_temp", download_mock)

    message = SimpleNamespace(
        document=None,
        photo=[SimpleNamespace(file_id="start-file")],
    )
    update = SimpleNamespace(message=message, callback_query=None)
    context = SimpleNamespace(
        user_data={
            "wan22_video_v2_data": {
                "start_image_path": None,
                "end_image_path": None,
                "use_end_frame": True,
                "resolution_preset": "preview",
            }
        },
        t=lambda key, **kwargs: f"T:{key}",
    )

    result = await wan22_video_v2_fsm.receive_start_image(update, context)

    assert result == wan22_video_v2_fsm.Wan22VideoV2State.WAIT_END_IMAGE
    assert context.user_data["wan22_video_v2_data"]["start_image_path"] == "/tmp/start.png"
    reply_mock.assert_awaited_once_with(
        message,
        "T:fsm.wan22_video_v2.send_end_image",
        parse_mode="Markdown",
    )


@pytest.mark.asyncio
async def test_choose_end_frame_mode_sets_wait_end_image(monkeypatch):
    edit_mock = AsyncMock()
    monkeypatch.setattr(wan22_video_v2_fsm, "robust_edit_text", edit_mock)

    query = SimpleNamespace(
        data="wan22v2_end_frame_yes",
        answer=AsyncMock(),
        message=SimpleNamespace(),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(
        user_data={
            "wan22_video_v2_data": {
                "start_image_path": "/tmp/start.png",
                "end_image_path": None,
                "use_end_frame": False,
            }
        },
        t=lambda key, **kwargs: f"T:{key}",
    )

    result = await wan22_video_v2_fsm.choose_end_frame_mode(update, context)

    assert result == wan22_video_v2_fsm.Wan22VideoV2State.WAIT_END_IMAGE
    assert context.user_data["wan22_video_v2_data"]["use_end_frame"] is True
    query.answer.assert_awaited_once()
    edit_mock.assert_awaited_once_with(
        query.message,
        "T:fsm.wan22_video_v2.send_end_image",
        parse_mode="Markdown",
    )


@pytest.mark.asyncio
async def test_submit_generation_forwards_wan22_payload(monkeypatch):
    edit_mock = AsyncMock()
    quota_mock = AsyncMock()
    create_background_task_mock = MagicMock()
    process_task_mock = MagicMock(return_value=("bg-task",))
    cleanup_mock = MagicMock()

    monkeypatch.setattr(wan22_video_v2_fsm, "robust_edit_text", edit_mock)
    monkeypatch.setattr(
        wan22_video_v2_fsm.permission_service, "check_quota", quota_mock
    )
    monkeypatch.setattr(
        wan22_video_v2_fsm, "create_background_task", create_background_task_mock
    )
    monkeypatch.setattr(
        wan22_video_v2_fsm, "process_wan22_video_v2_task", process_task_mock
    )
    monkeypatch.setattr(
        wan22_video_v2_fsm, "cleanup_fsm_temp_files", cleanup_mock
    )

    query = SimpleNamespace(
        data="wan22v2_submit",
        answer=AsyncMock(),
        message=SimpleNamespace(),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(),
        user_data={
            "in_conversation": wan22_video_v2_fsm.WAN22_VIDEO_V2_CONVERSATION_TAG,
            "wan22_video_v2_data": {
                "start_image_path": "/tmp/start.png",
                "end_image_path": "/tmp/end.png",
                "use_end_frame": True,
                "resolution_preset": "hd",
                "prompt": "positive",
                "negative_prompt": "negative",
            },
        },
        t=lambda key, **kwargs: f"T:{key}:{kwargs.get('cost', '')}",
    )

    result = await wan22_video_v2_fsm.submit_generation(update, context)

    assert result == ConversationHandler.END
    quota_mock.assert_awaited_once_with(12345, "tester", "Test User", cost=30)
    process_task_mock.assert_called_once_with(
        context=context,
        chat_id=10001,
        user_id=12345,
        username="tester",
        prompt="positive",
        negative_prompt="negative",
        images=["/tmp/start.png", "/tmp/end.png"],
        use_end_frame=True,
        resolution_preset="hd",
        duration=5,
        result_meta=None,
        cleanup=True,
    )
    create_background_task_mock.assert_called_once_with(context, ("bg-task",))
    assert "wan22_video_v2_data" not in context.user_data
    assert "in_conversation" not in context.user_data
    cleanup_mock.assert_not_called()
    assert edit_mock.await_args_list[-1].args[1] == "T:fsm.wan22_video_v2.submitting:30"
    assert edit_mock.await_args_list[-1].kwargs == {"parse_mode": "Markdown"}


@pytest.mark.asyncio
async def test_skip_negative_prompt_submits_without_settings_confirmation(monkeypatch):
    edit_mock = AsyncMock()
    quota_mock = AsyncMock()
    create_background_task_mock = MagicMock()
    process_task_mock = MagicMock(return_value=("bg-task",))

    monkeypatch.setattr(wan22_video_v2_fsm, "robust_edit_text", edit_mock)
    monkeypatch.setattr(
        wan22_video_v2_fsm.permission_service, "check_quota", quota_mock
    )
    monkeypatch.setattr(
        wan22_video_v2_fsm, "create_background_task", create_background_task_mock
    )
    monkeypatch.setattr(
        wan22_video_v2_fsm, "process_wan22_video_v2_task", process_task_mock
    )

    query = SimpleNamespace(
        data="wan22v2_skip_negative_prompt",
        answer=AsyncMock(),
        message=SimpleNamespace(),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(),
        user_data={
            "in_conversation": wan22_video_v2_fsm.WAN22_VIDEO_V2_CONVERSATION_TAG,
            "wan22_video_v2_data": {
                "start_image_path": "/tmp/start.png",
                "end_image_path": None,
                "use_end_frame": False,
                "resolution_preset": "small",
                "duration": 8,
                "prompt": "positive",
            },
        },
        t=lambda key, **kwargs: f"T:{key}:{kwargs.get('cost', '')}",
    )

    result = await wan22_video_v2_fsm.skip_negative_prompt(update, context)

    assert result == ConversationHandler.END
    query.answer.assert_awaited_once()
    quota_mock.assert_awaited_once_with(12345, "tester", "Test User", cost=24)
    process_task_mock.assert_called_once()
    assert process_task_mock.call_args.kwargs["negative_prompt"] == ""
    create_background_task_mock.assert_called_once_with(context, ("bg-task",))
    assert edit_mock.await_args_list[-1].args[1] == "T:fsm.wan22_video_v2.submitting:24"
    assert "wan22_video_v2_data" not in context.user_data


@pytest.mark.asyncio
async def test_receive_negative_prompt_submits_without_settings_confirmation(monkeypatch):
    reply_mock = AsyncMock()
    quota_mock = AsyncMock()
    create_background_task_mock = MagicMock()
    process_task_mock = MagicMock(return_value=("bg-task",))

    monkeypatch.setattr(wan22_video_v2_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        wan22_video_v2_fsm.permission_service, "check_quota", quota_mock
    )
    monkeypatch.setattr(
        wan22_video_v2_fsm, "create_background_task", create_background_task_mock
    )
    monkeypatch.setattr(
        wan22_video_v2_fsm, "process_wan22_video_v2_task", process_task_mock
    )

    update = _build_update_with_message(text="custom negative")
    context = SimpleNamespace(
        bot=SimpleNamespace(),
        user_data={
            "in_conversation": wan22_video_v2_fsm.WAN22_VIDEO_V2_CONVERSATION_TAG,
            "wan22_video_v2_data": {
                "start_image_path": "/tmp/start.png",
                "end_image_path": None,
                "use_end_frame": False,
                "resolution_preset": "preview",
                "duration": 5,
                "prompt": "positive",
            },
        },
        t=lambda key, **kwargs: f"T:{key}:{kwargs.get('cost', '')}",
    )

    result = await wan22_video_v2_fsm.receive_negative_prompt(update, context)

    assert result == ConversationHandler.END
    quota_mock.assert_awaited_once_with(12345, "tester", "Test User", cost=6)
    process_task_mock.assert_called_once()
    assert process_task_mock.call_args.kwargs["negative_prompt"] == "custom negative"
    create_background_task_mock.assert_called_once_with(context, ("bg-task",))
    reply_mock.assert_awaited_once_with(
        update.message,
        "T:fsm.wan22_video_v2.submitting:6",
        parse_mode="Markdown",
    )
    assert "wan22_video_v2_data" not in context.user_data


@pytest.mark.asyncio
async def test_start_wan22_video_v2_extension_prefills_tail_frame(monkeypatch):
    edit_mock = AsyncMock()
    load_history_mock = AsyncMock(return_value=SimpleNamespace(type="wan22_video_v2"))
    download_last_frame_mock = AsyncMock(return_value="/tmp/tail.png")

    monkeypatch.setattr(wan22_video_v2_fsm, "robust_edit_text", edit_mock)
    monkeypatch.setattr(
        wan22_video_v2_fsm,
        "load_owned_wan22_history",
        load_history_mock,
    )
    monkeypatch.setattr(
        wan22_video_v2_fsm,
        "download_last_frame_to_fsm_temp",
        download_last_frame_mock,
    )

    query = SimpleNamespace(
        data="wan22v2_extend",
        answer=AsyncMock(),
        message=SimpleNamespace(text="existing", message_id=123),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
    )
    context = SimpleNamespace(
        bot_data={
            "msg_meta_123": {
                "task_id": "task-1",
                "wan22_resolution_preset": "hd",
                "wan22_chain_task_ids": [],
            }
        },
        user_data={},
        lang="zh",
        t=lambda key, **kwargs: (
            f"{key}:{kwargs['resolution_preset']}"
            if key == "fsm.wan22_video_v2.extension_start"
            else f"T:{key}"
        ),
    )

    result = await wan22_video_v2_fsm.start_wan22_video_v2_extension(update, context)

    assert result == wan22_video_v2_fsm.Wan22VideoV2State.WAIT_END_FRAME_CHOICE
    assert context.user_data["in_conversation"] == wan22_video_v2_fsm.WAN22_VIDEO_V2_CONVERSATION_TAG
    assert context.user_data["wan22_video_v2_data"]["start_image_path"] == "/tmp/tail.png"
    assert context.user_data["wan22_video_v2_data"]["resolution_preset"] == "hd"
    assert context.user_data["wan22_video_v2_data"]["extension_prev_task_id"] == "task-1"
    assert context.user_data["wan22_video_v2_data"]["chain_task_ids"] == ["task-1"]
    load_history_mock.assert_awaited_once_with(
        task_id="task-1",
        telegram_user_id=12345,
        username="tester",
    )
    download_last_frame_mock.assert_awaited_once()
    edit_mock.assert_awaited_once_with(
        query.message,
        "fsm.wan22_video_v2.extension_start:高清",
        reply_markup=ANY,
        parse_mode="Markdown",
    )


@pytest.mark.asyncio
async def test_start_wan22_video_v2_extension_recovers_context_without_bot_data(
    monkeypatch,
):
    edit_mock = AsyncMock()
    history = SimpleNamespace(
        type="wan22_video_v2",
        extra_outputs={
            "_wan22_context": {
                "wan22_resolution_preset": "hd",
                "wan22_chain_task_ids": ["task-0"],
            }
        },
    )

    monkeypatch.setattr(wan22_video_v2_fsm, "robust_edit_text", edit_mock)
    monkeypatch.setattr(
        wan22_video_v2_fsm,
        "load_owned_wan22_history",
        AsyncMock(return_value=history),
    )
    monkeypatch.setattr(
        wan22_video_v2_fsm,
        "download_last_frame_to_fsm_temp",
        AsyncMock(return_value="/tmp/tail.png"),
    )

    query = SimpleNamespace(
        data="wan22v2_extend:task-1",
        answer=AsyncMock(),
        message=SimpleNamespace(text="existing", message_id=123),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
    )
    context = SimpleNamespace(
        bot_data={},
        user_data={},
        lang="zh",
        t=lambda key, **kwargs: (
            f"{key}:{kwargs['resolution_preset']}"
            if key == "fsm.wan22_video_v2.extension_start"
            else f"T:{key}"
        ),
    )

    result = await wan22_video_v2_fsm.start_wan22_video_v2_extension(update, context)

    assert result == wan22_video_v2_fsm.Wan22VideoV2State.WAIT_END_FRAME_CHOICE
    data = context.user_data["wan22_video_v2_data"]
    assert data["extension_prev_task_id"] == "task-1"
    assert data["resolution_preset"] == "hd"
    assert data["chain_task_ids"] == ["task-0", "task-1"]
    edit_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_wan22_video_v2_extension_recovers_task_id_from_gallery_button(
    monkeypatch,
):
    edit_mock = AsyncMock()
    history = SimpleNamespace(type="wan22_video_v2", extra_outputs={})

    monkeypatch.setattr(wan22_video_v2_fsm, "robust_edit_text", edit_mock)
    monkeypatch.setattr(
        wan22_video_v2_fsm,
        "load_owned_wan22_history",
        AsyncMock(return_value=history),
    )
    monkeypatch.setattr(
        wan22_video_v2_fsm,
        "download_last_frame_to_fsm_temp",
        AsyncMock(return_value="/tmp/tail.png"),
    )

    query = SimpleNamespace(
        data="wan22v2_extend",
        answer=AsyncMock(),
        message=SimpleNamespace(
            text="existing",
            message_id=123,
            reply_markup=SimpleNamespace(
                inline_keyboard=[
                    [SimpleNamespace(callback_data="submit_gallery_task-1")]
                ]
            ),
        ),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
    )
    context = SimpleNamespace(
        bot_data={},
        user_data={},
        lang="zh",
        t=lambda key, **kwargs: (
            f"{key}:{kwargs['resolution_preset']}"
            if key == "fsm.wan22_video_v2.extension_start"
            else f"T:{key}"
        ),
    )

    result = await wan22_video_v2_fsm.start_wan22_video_v2_extension(update, context)

    assert result == wan22_video_v2_fsm.Wan22VideoV2State.WAIT_END_FRAME_CHOICE
    assert context.user_data["wan22_video_v2_data"]["extension_prev_task_id"] == "task-1"


@pytest.mark.asyncio
async def test_start_wan22_video_v2_extension_replies_when_task_id_missing(
    monkeypatch,
):
    reply_mock = AsyncMock()
    monkeypatch.setattr(wan22_video_v2_fsm, "robust_reply_text", reply_mock)

    message = SimpleNamespace(message_id=123, reply_markup=None)
    query = SimpleNamespace(
        data="wan22v2_extend",
        answer=AsyncMock(),
        message=message,
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(
        bot_data={},
        user_data={},
        t=lambda key, **kwargs: f"T:{key}",
    )

    result = await wan22_video_v2_fsm.start_wan22_video_v2_extension(update, context)

    assert result == ConversationHandler.END
    reply_mock.assert_awaited_once_with(
        message,
        "T:fsm.wan22_video_v2.expired_alert",
        parse_mode="Markdown",
    )


@pytest.mark.asyncio
async def test_start_wan22_video_v2_extension_replies_for_media_message(monkeypatch):
    edit_mock = AsyncMock()
    reply_mock = AsyncMock()
    monkeypatch.setattr(wan22_video_v2_fsm, "robust_edit_text", edit_mock)
    monkeypatch.setattr(wan22_video_v2_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        wan22_video_v2_fsm,
        "load_owned_wan22_history",
        AsyncMock(return_value=SimpleNamespace(type="wan22_video_v2")),
    )
    monkeypatch.setattr(
        wan22_video_v2_fsm,
        "download_last_frame_to_fsm_temp",
        AsyncMock(return_value="/tmp/tail.png"),
    )

    media_message = SimpleNamespace(text=None, caption="done")
    query = SimpleNamespace(
        data="wan22v2_extend",
        answer=AsyncMock(),
        message=media_message,
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
    )
    context = SimpleNamespace(
        bot_data={
            "msg_meta_123": {
                "task_id": "task-1",
                "wan22_resolution_preset": "hd",
                "wan22_chain_task_ids": [],
            }
        },
        user_data={},
        lang="zh",
        t=lambda key, **kwargs: (
            f"{key}:{kwargs['resolution_preset']}"
            if key == "fsm.wan22_video_v2.extension_start"
            else f"T:{key}"
        ),
    )
    media_message.message_id = 123

    result = await wan22_video_v2_fsm.start_wan22_video_v2_extension(update, context)

    assert result == wan22_video_v2_fsm.Wan22VideoV2State.WAIT_END_FRAME_CHOICE
    edit_mock.assert_not_awaited()
    reply_mock.assert_awaited_once_with(
        media_message,
        "fsm.wan22_video_v2.extension_start:高清",
        reply_markup=ANY,
        parse_mode="Markdown",
    )


@pytest.mark.asyncio
async def test_start_wan22_video_v2_extension_surfaces_missing_tail_frame_error(
    monkeypatch,
):
    reply_mock = AsyncMock()
    monkeypatch.setattr(wan22_video_v2_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        wan22_video_v2_fsm,
        "load_owned_wan22_history",
        AsyncMock(
            side_effect=wan22_video_v2_fsm.Wan22VideoV2ExtensionError(
                "这条记录没有可用的尾帧图片"
            )
        ),
    )

    message = SimpleNamespace()
    query = SimpleNamespace(
        data="wan22v2_extend",
        answer=AsyncMock(),
        message=message,
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
        effective_message=message,
    )
    context = SimpleNamespace(
        bot_data={"msg_meta_123": {"task_id": "task-1"}},
        user_data={},
        lang="zh",
        t=lambda key, **kwargs: f"T:{key}",
    )
    message.message_id = 123

    result = await wan22_video_v2_fsm.start_wan22_video_v2_extension(update, context)

    assert result == ConversationHandler.END
    reply_mock.assert_awaited_once_with(message, "❌ 这条记录没有可用的尾帧图片")


@pytest.mark.asyncio
async def test_start_wan22_video_v2_regeneration_waits_for_editable_prompt(
    monkeypatch,
):
    edit_mock = AsyncMock()
    load_history_mock = AsyncMock(
        side_effect=[
            SimpleNamespace(
                prompt="[standard|5s] [模型: BreastGrow] current prompt",
                requested_duration=5,
                type=wan22_video_v2_fsm.MODE_IMAGE_TO_VIDEO,
            ),
            SimpleNamespace(type="wan22_video_v2"),
        ]
    )

    monkeypatch.setattr(wan22_video_v2_fsm, "robust_edit_text", edit_mock)
    monkeypatch.setattr(
        wan22_video_v2_fsm,
        "load_owned_wan22_history",
        load_history_mock,
    )
    monkeypatch.setattr(
        wan22_video_v2_fsm,
        "download_last_frame_to_fsm_temp",
        AsyncMock(return_value="/tmp/start.png"),
    )

    query = SimpleNamespace(
        data="wan22v2_regenerate",
        answer=AsyncMock(),
        message=SimpleNamespace(text="existing", message_id=123),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
    )
    context = SimpleNamespace(
        bot_data={
            "msg_meta_123": {
                "task_id": "task-3",
                "wan22_prev_task_id": "task-2",
                "wan22_chain_task_ids": ["task-1", "task-2"],
                "wan22_negative_prompt": "negative",
                "wan22_resolution_preset": "standard",
                "wan22_use_end_frame": False,
                "lora_name": "BreastGrow",
                "lora_strength": 1.0,
            }
        },
        user_data={},
        lang="zh",
        t=lambda key, **kwargs: (
            f"regen:{kwargs['prompt']}"
            if key == "fsm.wan22_video_v2.regenerate_prompt"
            else f"T:{key}"
        ),
    )

    result = await wan22_video_v2_fsm.start_wan22_video_v2_regeneration(
        update,
        context,
    )

    assert result == wan22_video_v2_fsm.Wan22VideoV2State.WAIT_PROMPT
    data = context.user_data["wan22_video_v2_data"]
    assert data["start_image_path"] == "/tmp/start.png"
    assert data["prompt"] == "current prompt"
    assert data["prefill_prompt"] == "current prompt"
    assert data["negative_prompt"] == "negative"
    assert data["extension_prev_task_id"] == "task-2"
    assert data["extension_task_type"] == wan22_video_v2_fsm.MODE_IMAGE_TO_VIDEO
    assert data["lora_name"] == "BreastGrow"
    assert data["lora_strength"] == 1.0
    assert data["chain_task_ids"] == ["task-1", "task-2"]
    edit_mock.assert_awaited_once_with(
        query.message,
        "regen:current prompt",
        reply_markup=ANY,
        parse_mode="Markdown",
    )


@pytest.mark.asyncio
async def test_use_original_prompt_moves_to_negative_prompt(monkeypatch):
    edit_mock = AsyncMock()
    monkeypatch.setattr(wan22_video_v2_fsm, "robust_edit_text", edit_mock)

    query = SimpleNamespace(
        data="wan22v2_use_original_prompt",
        answer=AsyncMock(),
        message=SimpleNamespace(text="existing"),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(
        user_data={
            "wan22_video_v2_data": {
                "prompt": "current prompt",
                "prefill_prompt": "current prompt",
            }
        },
        t=lambda key, **kwargs: f"T:{key}",
    )

    result = await wan22_video_v2_fsm.use_original_prompt(update, context)

    assert result == wan22_video_v2_fsm.Wan22VideoV2State.WAIT_NEGATIVE_PROMPT
    assert context.user_data["wan22_video_v2_data"]["prompt"] == "current prompt"
    edit_mock.assert_awaited_once_with(
        query.message,
        "T:fsm.wan22_video_v2.send_negative_prompt",
        reply_markup=ANY,
        parse_mode="Markdown",
    )


@pytest.mark.asyncio
async def test_submit_generation_for_extension_adds_stitch_context(monkeypatch):
    edit_mock = AsyncMock()
    quota_mock = AsyncMock()
    create_background_task_mock = MagicMock()
    process_task_mock = MagicMock(return_value=("bg-task",))

    monkeypatch.setattr(wan22_video_v2_fsm, "robust_edit_text", edit_mock)
    monkeypatch.setattr(
        wan22_video_v2_fsm.permission_service, "check_quota", quota_mock
    )
    monkeypatch.setattr(
        wan22_video_v2_fsm, "create_background_task", create_background_task_mock
    )
    monkeypatch.setattr(
        wan22_video_v2_fsm, "process_wan22_video_v2_task", process_task_mock
    )

    query = SimpleNamespace(
        data="wan22v2_submit",
        answer=AsyncMock(),
        message=SimpleNamespace(),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(),
        user_data={
            "in_conversation": wan22_video_v2_fsm.WAN22_VIDEO_V2_CONVERSATION_TAG,
            "wan22_video_v2_data": {
                "start_image_path": "/tmp/start.png",
                "end_image_path": None,
                "use_end_frame": False,
                "resolution_preset": "standard",
                "prompt": "positive",
                "negative_prompt": "negative",
                "extension_prev_task_id": "task-1",
                "chain_task_ids": ["task-1"],
            },
        },
        t=lambda key, **kwargs: f"T:{key}:{kwargs.get('cost', '')}",
    )

    result = await wan22_video_v2_fsm.submit_generation(update, context)

    assert result == ConversationHandler.END
    process_task_mock.assert_called_once()
    kwargs = process_task_mock.call_args.kwargs
    assert kwargs["result_meta"] == {
        "wan22_prev_task_id": "task-1",
        "wan22_chain_task_ids": ["task-1"],
    }


@pytest.mark.asyncio
async def test_submit_generation_for_legacy_extension_uses_legacy_submitting_text(
    monkeypatch,
):
    edit_mock = AsyncMock()
    quota_mock = AsyncMock()
    create_background_task_mock = MagicMock()
    process_task_mock = MagicMock(return_value=("bg-task",))

    monkeypatch.setattr(wan22_video_v2_fsm, "robust_edit_text", edit_mock)
    monkeypatch.setattr(
        wan22_video_v2_fsm.permission_service, "check_quota", quota_mock
    )
    monkeypatch.setattr(
        wan22_video_v2_fsm, "create_background_task", create_background_task_mock
    )
    monkeypatch.setattr(
        wan22_video_v2_fsm, "process_image_to_video_task", process_task_mock
    )

    query = SimpleNamespace(
        data="wan22v2_submit",
        answer=AsyncMock(),
        message=SimpleNamespace(),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(),
        user_data={
            "in_conversation": wan22_video_v2_fsm.WAN22_VIDEO_V2_CONVERSATION_TAG,
            "wan22_video_v2_data": {
                "start_image_path": "/tmp/start.png",
                "end_image_path": None,
                "use_end_frame": False,
                "resolution_preset": "standard",
                "prompt": "positive",
                "negative_prompt": "negative",
                "extension_prev_task_id": "task-1",
                "extension_task_type": wan22_video_v2_fsm.MODE_IMAGE_TO_VIDEO,
                "chain_task_ids": ["task-1"],
                "lora_name": "BreastGrow",
                "lora_strength": 1.0,
            },
        },
        t=lambda key, **kwargs: f"T:{key}:{kwargs.get('cost', '')}",
    )

    result = await wan22_video_v2_fsm.submit_generation(update, context)

    assert result == ConversationHandler.END
    process_task_mock.assert_called_once()
    assert edit_mock.await_args_list[-1].args[1] == (
        "T:fsm.wan22_video_v2.submitting_legacy:20"
    )


@pytest.mark.asyncio
async def test_build_settings_message_uses_selected_resolution_cost():
    context = SimpleNamespace(
        lang="zh",
        t=lambda key, **kwargs: (
            f"{key}:{kwargs['resolution_preset']}:{kwargs['cost']}"
            if key == "fsm.wan22_video_v2.settings_text"
            else f"T:{key}"
        ),
    )
    data = {
        "use_end_frame": False,
        "end_image_path": None,
        "prompt": "positive",
        "negative_prompt": "",
        "resolution_preset": "preview",
    }

    message = wan22_video_v2_fsm._build_settings_message(context, data)

    assert message == "fsm.wan22_video_v2.settings_text:极速（约 512p）:6"


@pytest.mark.asyncio
async def test_build_settings_message_uses_legacy_title_for_legacy_context():
    context = SimpleNamespace(
        lang="zh",
        t=lambda key, **kwargs: (
            f"{key}:{kwargs['resolution_preset']}:{kwargs['cost']}"
            if key == "fsm.wan22_video_v2.legacy_settings_text"
            else f"T:{key}"
        ),
    )
    data = {
        "use_end_frame": False,
        "end_image_path": None,
        "prompt": "positive",
        "negative_prompt": "",
        "resolution_preset": "preview",
        "extension_task_type": wan22_video_v2_fsm.MODE_IMAGE_TO_VIDEO,
    }

    message = wan22_video_v2_fsm._build_settings_message(context, data)

    assert message == "fsm.wan22_video_v2.legacy_settings_text:极速（约 512p）:6"


@pytest.mark.asyncio
async def test_handle_settings_action_updates_resolution_preset(monkeypatch):
    edit_mock = AsyncMock()
    monkeypatch.setattr(wan22_video_v2_fsm, "robust_edit_text", edit_mock)

    query = SimpleNamespace(
        data="wan22v2_res_preview",
        answer=AsyncMock(),
        message=SimpleNamespace(),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(
        user_data={
            "wan22_video_v2_data": {
                "start_image_path": "/tmp/start.png",
                "end_image_path": None,
                "use_end_frame": False,
                "resolution_preset": "standard",
                "prompt": "positive",
                "negative_prompt": "negative",
            }
        },
        lang="zh",
        t=lambda key, **kwargs: f"T:{key}",
    )

    result = await wan22_video_v2_fsm.handle_settings_action(update, context)

    assert result == wan22_video_v2_fsm.Wan22VideoV2State.WAIT_SETTINGS
    assert context.user_data["wan22_video_v2_data"]["resolution_preset"] == "preview"
    query.answer.assert_awaited_once()
    edit_mock.assert_awaited_once()
