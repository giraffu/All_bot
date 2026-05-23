from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telegram.ext import ConversationHandler

from src.constants import MODE_CUSTOM_VIDEO, MODE_IMAGE_TO_VIDEO
from src.handlers.conversation_states import ImageToVideoState
from src.handlers.fsm import (
    custom_video_fsm,
    edit_image_fsm,
    faceswap_fsm,
    image_to_video_fsm,
    ltx_video_fsm,
    quick_video_fsm,
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


def _build_update_with_message(*, text: str = "test prompt"):
    user = _build_user()
    return SimpleNamespace(
        effective_user=user,
        effective_chat=SimpleNamespace(id=10001),
        message=_build_message(text=text),
    )


def test_deprecated_video_lora_fsm_module_reexports_unified_handler():
    from src.handlers.fsm import video_lora_fsm

    assert (
        image_to_video_fsm.get_image_to_video_fsm_handler
        is video_lora_fsm.get_image_to_video_fsm_handler
    )
    handler = image_to_video_fsm.get_image_to_video_fsm_handler()
    assert handler.name == "image_to_video_fsm"


@pytest.mark.asyncio
async def test_custom_video_state_expired_before_quota_check(monkeypatch):
    reply_mock = AsyncMock()
    quota_mock = AsyncMock()

    monkeypatch.setattr(image_to_video_fsm, "is_global_menu_command", lambda _text: False)
    monkeypatch.setattr(image_to_video_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(image_to_video_fsm.permission_service, "check_quota", quota_mock)

    update = SimpleNamespace(
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
        message=_build_message(),
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(),
        user_data={
            "in_conversation": "CUSTOM_VIDEO",
            "image_to_video_data": {
                "resolution": "512p",
                "duration": "5s",
                "lora_name": "",
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
    assert "video_lora_data" not in context.user_data
    assert "image_to_video_data" not in context.user_data


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

    monkeypatch.setattr(image_to_video_fsm, "is_global_menu_command", lambda _text: False)
    monkeypatch.setattr(image_to_video_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(image_to_video_fsm.permission_service, "check_quota", quota_mock)

    update = SimpleNamespace(
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
        message=_build_message(),
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(),
        user_data={
            "in_conversation": "VIDEO_LORA",
            "image_to_video_data": {
                "resolution": "512p",
                "duration": "5s",
                "lora_name": "test-lora",
                "image_path": None,
            }
        },
    )

    result = await image_to_video_fsm.receive_prompt(update, context)

    assert result == ConversationHandler.END
    quota_mock.assert_not_awaited()
    reply_mock.assert_awaited_once()
    assert "任务状态已过期" in reply_mock.await_args.args[1]
    assert "in_conversation" not in context.user_data
    assert "video_lora_data" not in context.user_data
    assert "image_to_video_data" not in context.user_data


@pytest.mark.asyncio
async def test_image_to_video_legacy_video_lora_data_fallback(monkeypatch):
    edit_mock = AsyncMock()
    monkeypatch.setattr(image_to_video_fsm, "robust_edit_text", edit_mock)

    query = SimpleNamespace(
        data="lora_select_",
        answer=AsyncMock(),
        message=SimpleNamespace(),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(
        user_data={
            "video_lora_data": {
                "resolution": "512p",
                "duration": "5s",
                "lora_name": None,
                "image_path": None,
            }
        }
    )

    result = await image_to_video_fsm.handle_lora_selection(update, context)

    assert result == ImageToVideoState.WAIT_IMAGE
    query.answer.assert_awaited_once()
    assert context.user_data["video_lora_data"]["lora_name"] == ""
    edit_mock.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("conversation_tag", "lora_name", "expected_task_type"),
    [
        ("VIDEO_LORA", "BreastGrow", MODE_IMAGE_TO_VIDEO),
        ("CUSTOM_VIDEO", "", MODE_CUSTOM_VIDEO),
    ],
)
async def test_image_to_video_receive_prompt_uses_unified_image_to_video_service(
    monkeypatch, conversation_tag, lora_name, expected_task_type
):
    reply_mock = AsyncMock()
    quota_mock = AsyncMock()
    create_background_task_mock = Mock()

    monkeypatch.setattr(image_to_video_fsm, "is_global_menu_command", lambda _text: False)
    monkeypatch.setattr(image_to_video_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(image_to_video_fsm.permission_service, "check_quota", quota_mock)
    monkeypatch.setattr(image_to_video_fsm, "create_background_task", create_background_task_mock)
    monkeypatch.setattr(
        image_to_video_fsm.TaskService,
        "process_image_to_video_task",
        lambda **kwargs: ("bg-task", kwargs),
    )

    update = _build_update_with_message()
    context = SimpleNamespace(
        bot=SimpleNamespace(),
        user_data={
            "in_conversation": conversation_tag,
            "image_to_video_data": {
                "resolution": "720p",
                "duration": "8s",
                "lora_name": lora_name,
                "image_path": "/tmp/demo.png",
            },
        },
    )

    result = await image_to_video_fsm.receive_prompt(update, context)

    assert result == ConversationHandler.END
    quota_mock.assert_awaited_once()
    create_background_task_mock.assert_called_once()
    service_call = create_background_task_mock.call_args.args[1]
    assert service_call[0] == "bg-task"
    assert service_call[1]["task_type"] == expected_task_type
    assert service_call[1]["resolution"] == "720p"
    assert service_call[1]["duration"] == "8s"
    assert service_call[1]["lora_name"] == lora_name
    assert "in_conversation" not in context.user_data
    assert "video_lora_data" not in context.user_data
    assert "image_to_video_data" not in context.user_data


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
