from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
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
    assert len(handler.entry_points) == 3


@pytest.mark.asyncio
async def test_start_wan22_video_v2_initializes_defaults(monkeypatch):
    reply_mock = AsyncMock()
    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr(wan22_video_v2_fsm, "robust_reply_text", reply_mock)

    update = _build_update_with_message(text="🎬 图生视频v2")
    context = SimpleNamespace(user_data={}, lang="zh", t=lambda key, **kwargs: f"T:{key}")

    result = await wan22_video_v2_fsm.start_wan22_video_v2(update, context)

    assert result == wan22_video_v2_fsm.Wan22VideoV2State.WAIT_START_IMAGE
    assert context.user_data["in_conversation"] == wan22_video_v2_fsm.WAN22_VIDEO_V2_CONVERSATION_TAG
    assert context.user_data["wan22_video_v2_data"]["use_end_frame"] is False
    assert (
        context.user_data["wan22_video_v2_data"]["resolution_preset"]
        == wan22_video_v2_fsm.WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET
    )
    reply_mock.assert_awaited_once()
    assert "T:fsm.wan22_video_v2.start" in reply_mock.await_args.args[1]


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
        cleanup=True,
    )
    create_background_task_mock.assert_called_once_with(context, ("bg-task",))
    assert "wan22_video_v2_data" not in context.user_data
    assert "in_conversation" not in context.user_data
    cleanup_mock.assert_not_called()
    assert edit_mock.await_args_list[-1].args[1] == "T:fsm.wan22_video_v2.submitting:30"
    assert edit_mock.await_args_list[-1].kwargs == {"parse_mode": "Markdown"}


@pytest.mark.asyncio
async def test_build_settings_message_uses_selected_resolution_cost():
    context = SimpleNamespace(
        lang="zh",
        t=lambda key, **kwargs: (
            f"{key}:{kwargs['cost']}"
            if key == "fsm.wan22_video_v2.settings_text"
            else f"T:{key}"
        ),
    )
    data = {
        "use_end_frame": False,
        "end_image_path": None,
        "prompt": "positive",
        "negative_prompt": "",
        "resolution_preset": "fast",
    }

    message = wan22_video_v2_fsm._build_settings_message(context, data)

    assert message == "fsm.wan22_video_v2.settings_text:10"


@pytest.mark.asyncio
async def test_handle_settings_action_updates_resolution_preset(monkeypatch):
    edit_mock = AsyncMock()
    monkeypatch.setattr(wan22_video_v2_fsm, "robust_edit_text", edit_mock)

    query = SimpleNamespace(
        data="wan22v2_res_hd",
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
    assert context.user_data["wan22_video_v2_data"]["resolution_preset"] == "hd"
    query.answer.assert_awaited_once()
    edit_mock.assert_awaited_once()
