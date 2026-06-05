from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock
import warnings

import pytest
from telegram.ext import ConversationHandler
from telegram.warnings import PTBUserWarning

from src.constants import (
    MODE_CUSTOM_VIDEO,
    MODE_EDIT,
    MODE_IMAGE_TO_VIDEO,
    MODE_IMG2IMG_LORA,
)
from src.core.exceptions import InsufficientCreditsError
from src.handlers.fsm import (
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
        callback_query=None,
    )


def test_image_to_video_fsm_exposes_unified_handler():
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=PTBUserWarning)
        handler = image_to_video_fsm.get_image_to_video_fsm_handler()
    assert handler.name == "image_to_video_fsm"
    assert len(handler.entry_points) == 8


def test_legacy_video_lora_exports_are_removed():
    assert not hasattr(image_to_video_fsm, "start_video_lora")
    assert not hasattr(image_to_video_fsm, "get_video_lora_fsm_handler")


def test_image_to_video_private_video_lora_aliases_are_removed():
    assert not hasattr(image_to_video_fsm, "_initialize_video_lora_context")
    assert not hasattr(image_to_video_fsm, "_start_video_lora_flow")


def test_conversation_states_uses_only_image_to_video_state():
    from src.handlers import conversation_states

    assert conversation_states.ImageToVideoState is image_to_video_fsm.ImageToVideoState
    assert not hasattr(conversation_states, "VideoLoraState")


def test_custom_video_fsm_handler_reuses_unified_state_graph():
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=PTBUserWarning)
        unified_handler = image_to_video_fsm.get_image_to_video_fsm_handler()
    custom_entry_callbacks = [
        handler.callback
        for handler in unified_handler.entry_points
        if getattr(handler, "callback", None) is image_to_video_fsm.start_custom_video
    ]

    assert len(custom_entry_callbacks) == 3
    assert unified_handler.name == "image_to_video_fsm"
    assert unified_handler.fallbacks[0].callback is image_to_video_fsm.cancel_conversation


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

    result = await image_to_video_fsm.receive_prompt(update, context)

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
async def test_edit_image_duplicate_prompt_during_submission_is_ignored(monkeypatch):
    reply_mock = AsyncMock()
    quota_mock = AsyncMock()

    monkeypatch.setattr(edit_image_fsm, "is_global_menu_command", lambda _text: False)
    monkeypatch.setattr(edit_image_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(edit_image_fsm.permission_service, "check_quota", quota_mock)

    update = SimpleNamespace(
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
        message=_build_message(text="duplicate prompt"),
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(),
        user_data={
            "in_conversation": "EDIT_IMAGE",
            "edit_image_data": {
                "mode": "edit",
                "cost": 2,
                "images": ["/tmp/demo.png"],
                "lora_name": "",
                "submitting": True,
            }
        },
    )

    result = await edit_image_fsm.receive_prompt(update, context)

    assert result == ConversationHandler.END
    quota_mock.assert_not_awaited()
    reply_mock.assert_awaited_once()
    assert "任务已提交" in reply_mock.await_args.args[1]
    assert context.user_data["edit_image_data"]["submitting"] is True


@pytest.mark.asyncio
async def test_start_edit_image_routes_free_edit_to_lora_selection(monkeypatch):
    reply_mock = AsyncMock()

    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr(edit_image_fsm, "robust_reply_text", reply_mock)

    update = _build_update_with_message(text="自由P图")
    context = SimpleNamespace(
        user_data={},
    )

    monkeypatch.setitem(
        __import__("src.handlers.prompt_router", fromlist=["GLOBAL_REVERSE_MAP"]).GLOBAL_REVERSE_MAP,
        "自由P图",
        "menu.free_edit",
    )

    result = await edit_image_fsm.start_edit_image(update, context)

    assert result == edit_image_fsm.EditImageState.WAIT_LORA_SELECTION
    assert context.user_data["edit_image_data"]["mode"] == MODE_EDIT
    reply_mock.assert_awaited_once()
    assert "已进入【自由P图】模式" in reply_mock.await_args.args[1]
    assert reply_mock.await_args.kwargs["reply_markup"] is not None


@pytest.mark.asyncio
async def test_start_edit_image_english_lora_buttons(monkeypatch):
    reply_mock = AsyncMock()

    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr(edit_image_fsm, "robust_reply_text", reply_mock)

    update = _build_update_with_message(text="🎨 Free Edit")
    context = SimpleNamespace(user_data={}, lang="en")

    monkeypatch.setitem(
        __import__("src.handlers.prompt_router", fromlist=["GLOBAL_REVERSE_MAP"]).GLOBAL_REVERSE_MAP,
        "🎨 Free Edit",
        "menu.free_edit",
    )

    result = await edit_image_fsm.start_edit_image(update, context)

    assert result == edit_image_fsm.EditImageState.WAIT_LORA_SELECTION
    keyboard = reply_mock.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].text == "None"
    assert keyboard.inline_keyboard[0][1].text == "Realistic"


@pytest.mark.asyncio
async def test_start_quick_image_uses_english_locale(monkeypatch):
    reply_mock = AsyncMock()

    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr("src.handlers.fsm.quick_image_fsm.robust_reply_text", reply_mock)

    from src.handlers.fsm import quick_image_fsm

    update = _build_update_with_message(text="💃 Quick Undress")
    context = SimpleNamespace(user_data={}, lang="en")

    monkeypatch.setitem(
        __import__("src.handlers.prompt_router", fromlist=["GLOBAL_REVERSE_MAP"]).GLOBAL_REVERSE_MAP,
        "💃 Quick Undress",
        "menu.photo_edit_undress",
    )

    result = await quick_image_fsm.start_quick_image(update, context)

    assert result == quick_image_fsm.QuickImageState.WAIT_IMAGE
    reply_mock.assert_awaited_once()
    assert "Entered Quick Undress mode" in reply_mock.await_args.args[1]


@pytest.mark.asyncio
async def test_start_edit_image_routes_i2i_pro_to_reference_image(monkeypatch):
    reply_mock = AsyncMock()

    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr(edit_image_fsm, "robust_reply_text", reply_mock)

    update = _build_update_with_message(text="幻想换脸")
    context = SimpleNamespace(
        user_data={},
    )

    monkeypatch.setitem(
        __import__("src.handlers.prompt_router", fromlist=["GLOBAL_REVERSE_MAP"]).GLOBAL_REVERSE_MAP,
        "幻想换脸",
        "menu.i2i_pro",
    )

    result = await edit_image_fsm.start_edit_image(update, context)

    assert result == edit_image_fsm.EditImageState.WAIT_REFERENCE_IMAGES
    assert context.user_data["edit_image_data"]["mode"] == "i2i_pro"
    reply_mock.assert_awaited_once()
    assert "已进入【幻想换脸】模式" in reply_mock.await_args.args[1]
    assert reply_mock.await_args.kwargs["reply_markup"] is None


@pytest.mark.asyncio
async def test_edit_image_lora_selection_switches_to_img2img_lora(monkeypatch):
    edit_mock = AsyncMock()
    monkeypatch.setattr(edit_image_fsm, "robust_edit_text", edit_mock)

    query = SimpleNamespace(
        data="editlora_select_test-lora",
        answer=AsyncMock(),
        message=SimpleNamespace(),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(
        user_data={"edit_image_data": {"mode": MODE_EDIT, "cost": 2, "images": []}}
    )

    result = await edit_image_fsm.handle_lora_selection(update, context)

    assert result == edit_image_fsm.EditImageState.WAIT_REFERENCE_IMAGES
    query.answer.assert_awaited_once()
    assert context.user_data["edit_image_data"]["lora_name"] == "test-lora"
    assert context.user_data["edit_image_data"]["mode"] == MODE_IMG2IMG_LORA
    assert context.user_data["edit_image_data"]["cost"] == 2
    edit_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_edit_image_second_reference_image_updates_fusion_cost(monkeypatch):
    reply_mock = AsyncMock()
    download_mock = AsyncMock()
    get_file_mock = AsyncMock(
        return_value=SimpleNamespace(download_to_drive=download_mock)
    )

    monkeypatch.setattr(edit_image_fsm, "robust_reply_text", reply_mock)

    update = SimpleNamespace(
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
        message=SimpleNamespace(
            document=None,
            photo=[SimpleNamespace(file_id="new-photo-file-id")],
            chat_id=10001,
        ),
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(get_file=get_file_mock),
        user_data={
            "edit_image_data": {
                "mode": MODE_EDIT,
                "cost": 2,
                "images": ["/tmp/first.png"],
                "lora_name": "",
            }
        },
    )

    result = await edit_image_fsm.receive_reference_image(update, context)

    assert result == edit_image_fsm.EditImageState.WAIT_PROMPT
    get_file_mock.assert_awaited_once_with("new-photo-file-id")
    download_mock.assert_awaited_once()
    assert len(context.user_data["edit_image_data"]["images"]) == 2
    assert context.user_data["edit_image_data"]["cost"] == 6
    reply_mock.assert_awaited_once()
    assert "已收到 2 张参考图" in reply_mock.await_args.args[1]
    assert "双图融合将消耗 6 灵石" in reply_mock.await_args.args[1]


@pytest.mark.asyncio
async def test_edit_image_global_menu_command_exits_current_flow(monkeypatch):
    reply_mock = AsyncMock()
    quota_mock = AsyncMock()

    monkeypatch.setattr(edit_image_fsm, "is_global_menu_command", lambda _text: True)
    monkeypatch.setattr(edit_image_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(edit_image_fsm.permission_service, "check_quota", quota_mock)

    update = SimpleNamespace(
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
        message=_build_message(text="主菜单"),
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(),
        t=lambda key: {
            "system.fsm_exit_hint": "已退出当前流程",
            "system.fsm_in_progress_hint": "流程进行中",
        }[key],
        user_data={
            "in_conversation": "EDIT_IMAGE",
            "edit_image_data": {
                "mode": MODE_EDIT,
                "cost": 2,
                "images": ["/tmp/demo.png"],
                "lora_name": "",
            },
        },
    )

    result = await edit_image_fsm.receive_prompt(update, context)

    assert result == ConversationHandler.END
    quota_mock.assert_not_awaited()
    reply_mock.assert_awaited_once_with(update.message, "已退出当前流程")
    assert "in_conversation" not in context.user_data
    assert "edit_image_data" not in context.user_data


@pytest.mark.asyncio
async def test_edit_image_special_lora_normalizes_prompt_before_submit(monkeypatch):
    reply_mock = AsyncMock()
    quota_mock = AsyncMock()
    create_background_task_mock = Mock()

    monkeypatch.setattr(edit_image_fsm, "is_global_menu_command", lambda _text: False)
    monkeypatch.setattr(edit_image_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(edit_image_fsm.permission_service, "check_quota", quota_mock)
    monkeypatch.setattr(edit_image_fsm, "create_background_task", create_background_task_mock)
    monkeypatch.setattr(
        edit_image_fsm,
        "process_generation_task",
        lambda *args, **kwargs: ("bg-task", args, kwargs),
    )

    update = SimpleNamespace(
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
        message=_build_message(text="make it better"),
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(),
        user_data={
            "in_conversation": "EDIT_IMAGE",
            "edit_image_data": {
                "mode": MODE_IMG2IMG_LORA,
                "cost": 2,
                "images": ["/tmp/demo.png"],
                "lora_name": "qwen/adjust_pussy_anus.safetensors",
            },
        },
    )

    result = await edit_image_fsm.receive_prompt(update, context)

    assert result == ConversationHandler.END
    quota_mock.assert_awaited_once()
    create_background_task_mock.assert_called_once()
    service_call = create_background_task_mock.call_args.args[1]
    assert service_call[0] == "bg-task"
    assert service_call[2]["prompt"] == "adjust her pussy and anus, make it better"


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
async def test_ltx_video_receive_image_returns_settings_keyboard(monkeypatch):
    reply_mock = AsyncMock()
    download_mock = AsyncMock(return_value="/tmp/ltx_video.png")
    get_or_create_user_mock = AsyncMock(return_value=(SimpleNamespace(id=999), False))
    get_user_group_mock = AsyncMock(return_value="pro")
    get_user_identity_mock = AsyncMock(return_value="vip")

    monkeypatch.setattr(ltx_video_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        ltx_video_fsm,
        "download_telegram_file_to_fsm_temp",
        download_mock,
    )
    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        get_or_create_user_mock,
    )
    monkeypatch.setattr(
        ltx_video_fsm.permission_service,
        "get_user_group",
        get_user_group_mock,
    )
    monkeypatch.setattr(
        ltx_video_fsm.permission_service,
        "get_user_identity",
        get_user_identity_mock,
    )
    monkeypatch.setattr(
        ltx_video_fsm,
        "get_ltx_video_settings_keyboard",
        lambda *args, **kwargs: "ltx-keyboard",
    )

    message = SimpleNamespace(
        document=None,
        photo=[SimpleNamespace(file_id="photo-file-id")],
        chat_id=10001,
    )
    update = SimpleNamespace(
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
        message=message,
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(get_file=AsyncMock(return_value=SimpleNamespace())),
        user_data={
            "ltx_video_data": {
                "resolution": "1280x704",
                "duration": "5s",
                "image_path": None,
            }
        },
        lang="zh",
        t=lambda key, **kwargs: f"T:{key}",
    )

    result = await ltx_video_fsm.receive_image(update, context)

    assert result == ltx_video_fsm.LtxVideoState.WAIT_SETTINGS_AND_PROMPT
    context.bot.get_file.assert_awaited_once_with("photo-file-id")
    download_mock.assert_awaited_once()
    get_or_create_user_mock.assert_awaited_once_with(update.effective_user.id)
    get_user_group_mock.assert_awaited_once_with(999)
    get_user_identity_mock.assert_awaited_once_with(999)
    assert context.user_data["ltx_video_data"]["image_path"] == "/tmp/ltx_video.png"
    reply_mock.assert_awaited_once()
    assert reply_mock.await_args.args[0] is message
    assert "T:fsm.ltx_video.settings_text" in reply_mock.await_args.args[1]
    assert "T:fsm.image_to_video.current_lora" in reply_mock.await_args.args[1]
    assert reply_mock.await_args.kwargs == {
        "reply_markup": "ltx-keyboard",
        "parse_mode": "Markdown",
    }


@pytest.mark.asyncio
async def test_start_ltx_video_uses_english_locale(monkeypatch):
    reply_mock = AsyncMock()

    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr(ltx_video_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        ltx_video_fsm,
        "_build_ltx_lora_selection_keyboard",
        lambda _lang="en": "ltx-lora-keyboard",
    )

    update = _build_update_with_message(text="🎬 Pro Video")
    context = SimpleNamespace(user_data={}, lang="en", t=lambda key, **kwargs: f"T:{key}")

    result = await ltx_video_fsm.start_ltx_video(update, context)

    assert result == ltx_video_fsm.LtxVideoState.WAIT_LORA_SELECTION
    reply_mock.assert_awaited_once_with(
        update.message,
        "T:fsm.ltx_video.select_lora\n\n当前附加模型: None\nYou can select up to 3 LoRAs. Each one uses its default strength automatically.",
        reply_markup="ltx-lora-keyboard",
        parse_mode="Markdown",
    )


@pytest.mark.asyncio
async def test_start_ltx_video_opens_lora_selection_first(monkeypatch):
    reply_mock = AsyncMock()

    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr(ltx_video_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        ltx_video_fsm,
        "_build_ltx_lora_selection_keyboard",
        lambda _lang="zh": "ltx-lora-keyboard",
    )

    update = _build_update_with_message(text="🎬 高级图生视频")
    context = SimpleNamespace(user_data={}, lang="zh", t=lambda key, **kwargs: f"T:{key}")

    result = await ltx_video_fsm.start_ltx_video(update, context)

    assert result == ltx_video_fsm.LtxVideoState.WAIT_LORA_SELECTION
    assert context.user_data["ltx_video_data"]["lora_items"] == []
    reply_mock.assert_awaited_once_with(
        update.message,
        "T:fsm.ltx_video.select_lora\n\n当前附加模型: 无\n可多选，最多 3 个。提交时将自动使用各模型默认强度。",
        reply_markup="ltx-lora-keyboard",
        parse_mode="Markdown",
    )


@pytest.mark.asyncio
async def test_ltx_video_lora_selection_sets_name_and_requests_image(monkeypatch):
    edit_mock = AsyncMock()
    monkeypatch.setattr(ltx_video_fsm, "robust_edit_text", edit_mock)

    query = SimpleNamespace(
        data="ltx_lora_select_reasoning",
        answer=AsyncMock(),
        message=SimpleNamespace(),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(
        user_data={
            "ltx_video_data": {
                "resolution": "1280x704",
                "duration": "5s",
                "image_path": None,
                "lora_items": [],
            }
        },
        lang="zh",
        t=lambda key, **kwargs: f"T:{key}",
    )

    result = await ltx_video_fsm.handle_lora_selection(update, context)

    assert result == ltx_video_fsm.LtxVideoState.WAIT_IMAGE
    assert context.user_data["ltx_video_data"]["lora_items"] == [
        {
            "name": "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors",
            "strength": 0.8,
        }
    ]
    query.answer.assert_awaited_once()
    edit_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_ltx_video_confirm_generation_forwards_selected_lora(monkeypatch):
    safe_answer_mock = AsyncMock()
    create_background_task_mock = MagicMock()
    process_task_mock = AsyncMock(return_value=(None, None))
    edit_mock = AsyncMock()
    quota_mock = AsyncMock()

    monkeypatch.setattr("src.utils.safe_answer_query", safe_answer_mock)
    monkeypatch.setattr(ltx_video_fsm, "create_background_task", create_background_task_mock)
    monkeypatch.setattr(ltx_video_fsm, "process_ltx_video_task", process_task_mock)
    monkeypatch.setattr(ltx_video_fsm, "robust_edit_text", edit_mock)
    monkeypatch.setattr(ltx_video_fsm.permission_service, "check_quota", quota_mock)

    query = SimpleNamespace(
        from_user=SimpleNamespace(id=12345),
        message=SimpleNamespace(chat_id=10001),
        answer=AsyncMock(),
    )
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
                "duration": "10s",
                "prompt": "make video",
                "image_path": "/tmp/ltx.png",
                "lora_items": [
                    {
                        "name": "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors",
                        "strength": 0.8,
                    }
                ],
            }
        },
        t=lambda key, **kwargs: f"T:{key}",
    )

    result = await ltx_video_fsm.confirm_generation(update, context)

    assert result == ConversationHandler.END
    quota_mock.assert_awaited_once()
    create_background_task_mock.assert_called_once()
    process_task_mock.assert_called_once()
    assert (
        process_task_mock.call_args.kwargs["lora_name"]
        == "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors"
    )
    assert process_task_mock.call_args.kwargs["lora_strength"] == 0.8


@pytest.mark.asyncio
async def test_ltx_video_unexpected_input_switch_lang_exits_and_switches_immediately(
    monkeypatch,
):
    reply_mock = AsyncMock()
    toggle_mock = AsyncMock(return_value=("切到中文", "zh-keyboard"))
    monkeypatch.setattr(ltx_video_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(ltx_video_fsm, "is_global_menu_command", lambda _text: True)
    monkeypatch.setitem(
        __import__("src.handlers.prompt_router", fromlist=["GLOBAL_REVERSE_MAP"]).GLOBAL_REVERSE_MAP,
        "🌐 中文",
        "menu.switch_lang",
    )
    monkeypatch.setattr(
        "src.handlers.message_handler_runtime.toggle_user_language",
        toggle_mock,
    )

    update = _build_update_with_message(text="🌐 中文")
    context = SimpleNamespace(
        user_data={
            "in_conversation": "LTX_VIDEO",
            "ltx_video_data": {"image_path": None},
        }
    )

    result = await ltx_video_fsm.unexpected_input(update, context)

    assert result == ConversationHandler.END
    toggle_mock.assert_awaited_once_with(context, update.effective_user)
    reply_mock.assert_awaited_once_with(
        update.message, "切到中文", reply_markup="zh-keyboard"
    )
    assert "in_conversation" not in context.user_data
    assert "ltx_video_data" not in context.user_data


@pytest.mark.asyncio
async def test_image_to_video_state_expired_before_quota_check(monkeypatch):
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
            "in_conversation": image_to_video_fsm.IMAGE_TO_VIDEO_CONVERSATION_TAG,
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
async def test_image_to_video_legacy_video_lora_data_no_longer_used():
    query = SimpleNamespace(
        data="lora_select_",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
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

    assert result == ConversationHandler.END
    query.answer.assert_awaited_once()
    query.edit_message_text.assert_awaited_once_with("交互已失效或任务已提交，请重新开始")
    assert "video_lora_data" in context.user_data


@pytest.mark.asyncio
async def test_image_to_video_unexpected_input_switch_lang_exits_and_switches_immediately(
    monkeypatch,
):
    reply_mock = AsyncMock()
    toggle_mock = AsyncMock(return_value=("切到中文", "zh-keyboard"))
    monkeypatch.setattr(image_to_video_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(image_to_video_fsm, "is_global_menu_command", lambda _text: True)
    monkeypatch.setitem(
        __import__("src.handlers.prompt_router", fromlist=["GLOBAL_REVERSE_MAP"]).GLOBAL_REVERSE_MAP,
        "🌐 中文",
        "menu.switch_lang",
    )
    monkeypatch.setattr(
        "src.handlers.message_handler_runtime.toggle_user_language",
        toggle_mock,
    )

    update = _build_update_with_message(text="🌐 中文")
    context = SimpleNamespace(
        user_data={
            "in_conversation": image_to_video_fsm.IMAGE_TO_VIDEO_CONVERSATION_TAG,
            "image_to_video_data": {"image_path": None},
        }
    )

    result = await image_to_video_fsm.unexpected_input(update, context)

    assert result == ConversationHandler.END
    toggle_mock.assert_awaited_once_with(context, update.effective_user)
    reply_mock.assert_awaited_once_with(
        update.message, "切到中文", reply_markup="zh-keyboard"
    )
    assert "in_conversation" not in context.user_data
    assert "image_to_video_data" not in context.user_data


@pytest.mark.asyncio
async def test_start_image_to_video_english_lora_buttons(monkeypatch):
    reply_mock = AsyncMock()

    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr(image_to_video_fsm, "robust_reply_text", reply_mock)

    update = _build_update_with_message(text="🎬 Img2Video")
    context = SimpleNamespace(user_data={}, lang="en")

    monkeypatch.setitem(
        __import__("src.handlers.prompt_router", fromlist=["GLOBAL_REVERSE_MAP"]).GLOBAL_REVERSE_MAP,
        "🎬 Img2Video",
        "menu.video_lora",
    )

    result = await image_to_video_fsm.start_image_to_video(update, context)

    assert result == image_to_video_fsm.ImageToVideoState.WAIT_LORA_SELECTION
    keyboard = reply_mock.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].text == "✅ None"
    assert keyboard.inline_keyboard[0][1].text == "Breast Growth"
    assert len(keyboard.inline_keyboard[0]) == 4
    assert len(keyboard.inline_keyboard[1]) == 4
    assert [
        button.callback_data
        for row in keyboard.inline_keyboard[:2]
        for button in row
    ] == [
        "i2v_setup_lora_",
        "i2v_setup_lora_BreastGrow",
        "i2v_setup_lora_BreastInsertion",
        "i2v_setup_lora_Cum",
        "i2v_setup_lora_Cunilingus",
        "i2v_setup_lora_Flatchested",
        "i2v_setup_lora_Footjob",
        "i2v_setup_lora_Insertion",
    ]
    assert [
        button.callback_data
        for button in keyboard.inline_keyboard[2]
    ] == [
        image_to_video_fsm.I2V_SETUP_MODE_SINGLE,
        image_to_video_fsm.I2V_SETUP_MODE_END,
    ]
    assert [
        button.callback_data
        for button in keyboard.inline_keyboard[3]
    ] == [
        "i2v_setup_res_preview",
        "i2v_setup_res_standard",
        "i2v_setup_res_hd",
    ]
    assert [
        button.callback_data
        for button in keyboard.inline_keyboard[4]
    ] == [
        "i2v_setup_dur_5",
        "i2v_setup_dur_8",
        "i2v_setup_dur_10",
    ]
    assert keyboard.inline_keyboard[5][0].callback_data == image_to_video_fsm.I2V_SETUP_CONFIRM


@pytest.mark.asyncio
async def test_image_to_video_initial_setup_updates_all_choices_and_confirms(monkeypatch):
    edit_mock = AsyncMock()
    monkeypatch.setattr(image_to_video_fsm, "robust_edit_text", edit_mock)

    query = SimpleNamespace(
        data="i2v_setup_mode_end",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        message=SimpleNamespace(),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(
        user_data={
            "in_conversation": image_to_video_fsm.IMAGE_TO_VIDEO_CONVERSATION_TAG,
            "image_to_video_data": {
                "resolution": "preview",
                "duration": "5s",
                "image_path": None,
                "end_image_path": None,
                "use_end_frame": False,
                "lora_name": "",
            },
        },
        lang="zh",
    )

    result = await image_to_video_fsm.handle_initial_setup_selection(update, context)

    assert result == image_to_video_fsm.ImageToVideoState.WAIT_LORA_SELECTION
    assert context.user_data["image_to_video_data"]["use_end_frame"] is True
    assert edit_mock.await_args.kwargs["reply_markup"].inline_keyboard[2][1].text.startswith("✅")

    query.data = "i2v_setup_res_hd"
    await image_to_video_fsm.handle_initial_setup_selection(update, context)
    assert context.user_data["image_to_video_data"]["resolution"] == "hd"

    query.data = "i2v_setup_lora_BreastGrow"
    await image_to_video_fsm.handle_initial_setup_selection(update, context)
    assert context.user_data["image_to_video_data"]["lora_name"] == "BreastGrow"

    query.data = image_to_video_fsm.I2V_SETUP_CONFIRM
    result = await image_to_video_fsm.handle_initial_setup_selection(update, context)

    assert result == image_to_video_fsm.ImageToVideoState.WAIT_IMAGE
    assert "起始图片" in edit_mock.await_args.args[1]
    query.answer.assert_awaited()


@pytest.mark.asyncio
async def test_image_to_video_receive_single_image_requests_prompt(monkeypatch):
    reply_mock = AsyncMock()
    download_mock = AsyncMock(return_value="/tmp/start.png")
    monkeypatch.setattr(image_to_video_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        image_to_video_fsm,
        "download_telegram_file_to_fsm_temp",
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
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(get_file=AsyncMock(return_value=SimpleNamespace())),
        user_data={
            "image_to_video_data": {
                "resolution": "standard",
                "duration": "5s",
                "image_path": None,
                "end_image_path": None,
                "use_end_frame": False,
                "lora_name": "",
            }
        },
        lang="zh",
    )

    result = await image_to_video_fsm.receive_image(update, context)

    assert result == image_to_video_fsm.ImageToVideoState.WAIT_SETTINGS_AND_PROMPT
    assert context.user_data["image_to_video_data"]["image_path"] == "/tmp/start.png"
    assert context.user_data["image_to_video_data"]["end_image_path"] is None
    reply_mock.assert_awaited_once()
    assert "已收到起始图片" in reply_mock.await_args.args[1]
    assert "请直接发送提示词" in reply_mock.await_args.args[1]
    assert reply_mock.await_args.kwargs == {"parse_mode": "Markdown"}


@pytest.mark.asyncio
async def test_image_to_video_receive_start_image_in_end_frame_mode_waits_for_end_image(
    monkeypatch,
):
    reply_mock = AsyncMock()
    monkeypatch.setattr(image_to_video_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        image_to_video_fsm,
        "download_telegram_file_to_fsm_temp",
        AsyncMock(return_value="/tmp/start.png"),
    )

    message = SimpleNamespace(
        document=None,
        photo=[SimpleNamespace(file_id="photo-file-id")],
        chat_id=10001,
    )
    update = SimpleNamespace(
        effective_user=_build_user(),
        message=message,
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(get_file=AsyncMock(return_value=SimpleNamespace())),
        user_data={
            "image_to_video_data": {
                "resolution": "hd",
                "duration": "5s",
                "image_path": None,
                "end_image_path": None,
                "use_end_frame": True,
                "lora_name": "BreastGrow",
            }
        },
        lang="zh",
    )

    result = await image_to_video_fsm.receive_image(update, context)

    assert result == image_to_video_fsm.ImageToVideoState.WAIT_END_IMAGE
    assert context.user_data["image_to_video_data"]["use_end_frame"] is True
    assert "终止图片" in reply_mock.await_args.args[1]


@pytest.mark.asyncio
async def test_image_to_video_receive_end_image_requests_prompt(monkeypatch):
    reply_mock = AsyncMock()
    monkeypatch.setattr(image_to_video_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        image_to_video_fsm,
        "download_telegram_file_to_fsm_temp",
        AsyncMock(return_value="/tmp/end.png"),
    )

    message = SimpleNamespace(
        document=None,
        photo=[SimpleNamespace(file_id="photo-file-id")],
        chat_id=10001,
    )
    update = SimpleNamespace(
        effective_user=_build_user(),
        message=message,
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(get_file=AsyncMock(return_value=SimpleNamespace())),
        user_data={
            "image_to_video_data": {
                "resolution": "hd",
                "duration": "5s",
                "image_path": "/tmp/start.png",
                "end_image_path": None,
                "use_end_frame": True,
                "lora_name": "BreastGrow",
            }
        },
        lang="zh",
    )

    result = await image_to_video_fsm.receive_end_image(update, context)

    assert result == image_to_video_fsm.ImageToVideoState.WAIT_SETTINGS_AND_PROMPT
    assert context.user_data["image_to_video_data"]["end_image_path"] == "/tmp/end.png"
    assert "已收到终止图片" in reply_mock.await_args.args[1]
    assert "请直接发送提示词" in reply_mock.await_args.args[1]


@pytest.mark.asyncio
async def test_start_custom_video_setup_keeps_lora_fixed_to_none(monkeypatch):
    reply_mock = AsyncMock()
    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr(image_to_video_fsm, "robust_reply_text", reply_mock)

    update = _build_update_with_message(text="🎬 自定义图生视频")
    context = SimpleNamespace(user_data={}, lang="zh")

    result = await image_to_video_fsm.start_custom_video(update, context)

    assert result == image_to_video_fsm.ImageToVideoState.WAIT_LORA_SELECTION
    assert context.user_data["image_to_video_data"]["allow_lora_selection"] is False
    keyboard = reply_mock.await_args.kwargs["reply_markup"]
    assert len(keyboard.inline_keyboard[0]) == 1
    assert keyboard.inline_keyboard[0][0].callback_data == "i2v_setup_lora_"


@pytest.mark.asyncio
async def test_start_quick_video_uses_english_locale(monkeypatch):
    reply_mock = AsyncMock()

    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr("src.handlers.fsm.quick_video_fsm.robust_reply_text", reply_mock)

    update = _build_update_with_message(text="🛏️ GIF Missionary")
    context = SimpleNamespace(user_data={}, lang="en")

    monkeypatch.setitem(
        __import__("src.handlers.prompt_router", fromlist=["GLOBAL_REVERSE_MAP"]).GLOBAL_REVERSE_MAP,
        "🛏️ GIF Missionary",
        "menu.video_edit_missionary",
    )

    result = await quick_video_fsm.start_quick_video(update, context)

    assert result == quick_video_fsm.QuickVideoState.WAIT_IMAGE
    reply_mock.assert_awaited_once()
    assert "Entered" in reply_mock.await_args.args[1]
    assert "mode" in reply_mock.await_args.args[1]


@pytest.mark.asyncio
async def test_start_faceswap_uses_english_locale(monkeypatch):
    reply_mock = AsyncMock()

    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr(faceswap_fsm, "robust_reply_text", reply_mock)

    update = _build_update_with_message(text="🎭 Quick Faceswap")
    context = SimpleNamespace(user_data={}, lang="en")

    result = await faceswap_fsm.start_faceswap(update, context)

    assert result == faceswap_fsm.FaceSwapState.WAIT_FACE_IMAGE
    reply_mock.assert_awaited_once()
    assert "Welcome to Two-Person Face Swap" in reply_mock.await_args.args[1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("conversation_tag", "lora_name", "expected_task_type"),
    [
        (image_to_video_fsm.IMAGE_TO_VIDEO_CONVERSATION_TAG, "BreastGrow", MODE_IMAGE_TO_VIDEO),
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
        image_to_video_fsm,
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
    assert service_call[1]["resolution"] == "standard"
    assert service_call[1]["duration"] == 8
    assert service_call[1]["use_end_frame"] is False
    assert service_call[1]["lora_name"] == lora_name
    assert "in_conversation" not in context.user_data
    assert "video_lora_data" not in context.user_data
    assert "image_to_video_data" not in context.user_data


@pytest.mark.asyncio
async def test_image_to_video_receive_prompt_submits_optional_end_frame(monkeypatch):
    reply_mock = AsyncMock()
    quota_mock = AsyncMock()
    create_background_task_mock = Mock()

    monkeypatch.setattr(image_to_video_fsm, "is_global_menu_command", lambda _text: False)
    monkeypatch.setattr(image_to_video_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(image_to_video_fsm.permission_service, "check_quota", quota_mock)
    monkeypatch.setattr(image_to_video_fsm, "create_background_task", create_background_task_mock)
    monkeypatch.setattr(
        image_to_video_fsm,
        "process_image_to_video_task",
        lambda **kwargs: ("bg-task", kwargs),
    )

    update = _build_update_with_message()
    context = SimpleNamespace(
        bot=SimpleNamespace(),
        user_data={
            "in_conversation": image_to_video_fsm.IMAGE_TO_VIDEO_CONVERSATION_TAG,
            "image_to_video_data": {
                "resolution": "1024p",
                "duration": "10s",
                "lora_name": "BreastGrow",
                "image_path": "/tmp/start.png",
                "end_image_path": "/tmp/end.png",
                "use_end_frame": True,
            },
        },
    )

    result = await image_to_video_fsm.receive_prompt(update, context)

    assert result == ConversationHandler.END
    create_background_task_mock.assert_called_once()
    service_call = create_background_task_mock.call_args.args[1]
    assert service_call[1]["images"] == ["/tmp/start.png", "/tmp/end.png"]
    assert service_call[1]["resolution"] == "hd"
    assert service_call[1]["duration"] == 10
    assert service_call[1]["use_end_frame"] is True
    assert service_call[1]["lora_name"] == "BreastGrow"


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


@pytest.mark.asyncio
async def test_quick_video_insufficient_credits_cleans_up_without_nameerror(monkeypatch):
    safe_answer_mock = AsyncMock()
    send_message_mock = AsyncMock()
    remove_mock = Mock()
    query = SimpleNamespace(
        from_user=SimpleNamespace(id=12345),
        message=SimpleNamespace(chat_id=10001, message_id=777),
        answer=AsyncMock(),
    )

    monkeypatch.setattr("src.utils.safe_answer_query", safe_answer_mock)
    monkeypatch.setattr("src.utils.robust_send_message", send_message_mock)
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "check_quota",
        AsyncMock(side_effect=InsufficientCreditsError(current=1, cost=6)),
    )
    monkeypatch.setattr(quick_video_fsm.os.path, "exists", lambda path: True)
    monkeypatch.setattr(quick_video_fsm.os, "remove", remove_mock)

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
                "image_path": "/tmp/quick-video-input.png",
            },
        },
    )

    result = await quick_video_fsm.start_generation(update, context)

    assert result == ConversationHandler.END
    safe_answer_mock.assert_awaited_once()
    send_message_mock.assert_awaited_once()
    remove_mock.assert_called_once_with("/tmp/quick-video-input.png")
    assert "in_conversation" not in context.user_data
    assert "quick_video_data" not in context.user_data
