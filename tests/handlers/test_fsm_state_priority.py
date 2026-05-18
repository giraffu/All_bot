from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.ext import ConversationHandler

from src.handlers.fsm import (
    custom_video_fsm,
    edit_image_fsm,
    faceswap_fsm,
    ltx_video_fsm,
    quick_video_fsm,
    video_lora_fsm,
)


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


@pytest.mark.asyncio
async def test_custom_video_state_expired_before_quota_check(monkeypatch):
    reply_mock = AsyncMock()
    quota_mock = AsyncMock()

    monkeypatch.setattr(custom_video_fsm, "is_global_menu_command", lambda _text: False)
    monkeypatch.setattr(custom_video_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(custom_video_fsm.permission_service, "check_quota", quota_mock)

    update = SimpleNamespace(
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
        message=_build_message(),
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(),
        user_data={
            "in_conversation": "CUSTOM_VIDEO",
            "custom_video_data": {
                "resolution": "512p",
                "duration": "5s",
                "image_path": None,
            }
        },
    )

    result = await custom_video_fsm.receive_prompt(update, context)

    assert result == ConversationHandler.END
    quota_mock.assert_not_awaited()
    reply_mock.assert_awaited_once()
    assert "任务状态已过期" in reply_mock.await_args.args[1]
    assert "in_conversation" not in context.user_data
    assert "custom_video_data" not in context.user_data


@pytest.mark.asyncio
async def test_edit_image_empty_images_before_quota_check(monkeypatch):
    reply_mock = AsyncMock()
    quota_mock = AsyncMock()

    monkeypatch.setattr(edit_image_fsm, "is_global_menu_command", lambda _text: False)
    monkeypatch.setattr(edit_image_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(edit_image_fsm.permission_service, "check_quota", quota_mock)

    update = SimpleNamespace(
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
        message=_build_message(),
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(),
        user_data={
            "in_conversation": "EDIT_IMAGE",
            "edit_image_data": {
                "mode": "edit",
                "cost": 2,
                "images": [],
                "lora_name": "",
            }
        },
    )

    result = await edit_image_fsm.receive_prompt(update, context)

    assert result == ConversationHandler.END
    quota_mock.assert_not_awaited()
    reply_mock.assert_awaited_once()
    assert "任务已提交或状态已失效" in reply_mock.await_args.args[1]
    assert "in_conversation" not in context.user_data
    assert "edit_image_data" not in context.user_data


@pytest.mark.asyncio
async def test_ltx_video_state_expired_before_quota_check(monkeypatch):
    quota_mock = AsyncMock()
    safe_answer_mock = AsyncMock()
    query = SimpleNamespace(
        from_user=SimpleNamespace(id=12345),
        message=SimpleNamespace(chat_id=10001),
        answer=AsyncMock(),
    )

    monkeypatch.setattr(ltx_video_fsm.permission_service, "check_quota", quota_mock)
    monkeypatch.setattr("src.utils.safe_answer_query", safe_answer_mock)

    update = SimpleNamespace(
        callback_query=query,
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(),
        user_data={
            "in_conversation": "LTX_VIDEO",
            "ltx_video_data": {
                "resolution": "1280x704",
                "duration": "5s",
                "prompt": "make video",
                "image_path": None,
            }
        },
    )

    result = await ltx_video_fsm.confirm_generation(update, context)

    assert result == ConversationHandler.END
    quota_mock.assert_not_awaited()
    safe_answer_mock.assert_awaited_once()
    query.answer.assert_awaited_once()
    assert query.answer.await_args.kwargs["show_alert"] is True
    assert "任务状态已过期" in query.answer.await_args.args[0]
    assert "in_conversation" not in context.user_data
    assert "ltx_video_data" not in context.user_data


@pytest.mark.asyncio
async def test_video_lora_state_expired_before_quota_check(monkeypatch):
    reply_mock = AsyncMock()
    quota_mock = AsyncMock()

    monkeypatch.setattr(video_lora_fsm, "is_global_menu_command", lambda _text: False)
    monkeypatch.setattr(video_lora_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(video_lora_fsm.permission_service, "check_quota", quota_mock)

    update = SimpleNamespace(
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
        message=_build_message(),
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(),
        user_data={
            "in_conversation": "VIDEO_LORA",
            "video_lora_data": {
                "resolution": "512p",
                "duration": "5s",
                "lora_name": "test-lora",
                "image_path": None,
            }
        },
    )

    result = await video_lora_fsm.receive_prompt(update, context)

    assert result == ConversationHandler.END
    quota_mock.assert_not_awaited()
    reply_mock.assert_awaited_once()
    assert "任务状态已过期" in reply_mock.await_args.args[1]
    assert "in_conversation" not in context.user_data
    assert "video_lora_data" not in context.user_data


@pytest.mark.asyncio
async def test_faceswap_face_missing_before_quota_check(monkeypatch):
    reply_mock = AsyncMock()
    quota_mock = AsyncMock()

    monkeypatch.setattr(faceswap_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(faceswap_fsm.permission_service, "check_quota", quota_mock)

    message = SimpleNamespace(
        document=None,
        photo=[SimpleNamespace(file_id="face-file-id")],
        chat_id=10001,
    )
    update = SimpleNamespace(
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
        message=message,
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(),
        user_data={"in_conversation": "FACESWAP", "faceswap_data": {}},
    )

    result = await faceswap_fsm.receive_body_image(update, context)

    assert result == ConversationHandler.END
    quota_mock.assert_not_awaited()
    reply_mock.assert_awaited_once()
    assert "任务状态已过期" in reply_mock.await_args.args[1]
    assert "in_conversation" not in context.user_data
    assert "faceswap_data" not in context.user_data


@pytest.mark.asyncio
async def test_quick_video_missing_image_path_shows_alert(monkeypatch):
    safe_answer_mock = AsyncMock()
    query = SimpleNamespace(
        from_user=SimpleNamespace(id=12345),
        message=SimpleNamespace(chat_id=10001),
        answer=AsyncMock(),
    )

    monkeypatch.setattr("src.utils.safe_answer_query", safe_answer_mock)

    update = SimpleNamespace(
        callback_query=query,
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(),
        user_data={
            "in_conversation": "QUICK_VIDEO_test",
            "quick_video_data": {
                "mode": "test-mode",
                "resolution": "512p",
                "duration": "5s",
                "image_path": None,
            },
        },
    )

    result = await quick_video_fsm.start_generation(update, context)

    assert result == ConversationHandler.END
    safe_answer_mock.assert_awaited_once()
    query.answer.assert_awaited_once()
    assert query.answer.await_args.kwargs["show_alert"] is True
    assert "任务已提交或状态已失效" in query.answer.await_args.args[0]
    assert "in_conversation" not in context.user_data
    assert "quick_video_data" not in context.user_data
