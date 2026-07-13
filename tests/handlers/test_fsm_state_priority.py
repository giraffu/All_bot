from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock
import warnings

import pytest
from telegram.ext import CallbackQueryHandler, ConversationHandler
from telegram.warnings import PTBUserWarning

from src.constants import (
    MODE_CUSTOM_VIDEO,
    MODE_DOGGY_STYLE,
    MODE_EDIT,
    MODE_FREE_EDIT_V2,
    MODE_IMAGE_TO_VIDEO,
    MODE_I2I_DRAW,
    MODE_IMG2IMG_LORA,
    MODE_RANDOM_FACESWAP,
    MODE_PORNMASTER_FLUX2_MULTI_EDIT,
    MODE_PORNMASTER_FLUX2_EDIT_BF16,
    MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
)
from src.core.exceptions import InsufficientCreditsError
from src.handlers.fsm import (
    edit_image_fsm,
    faceswap_fsm,
    image_to_video_fsm,
    ltx_video_fsm,
    quick_image_fsm,
    quick_video_fsm,
)
from src.handlers.fsm.quick_draw_callback_data import (
    build_quick_draw_scene_callback_data,
    build_quick_filter_scene_callback_data,
)
from src.services.qqcc_config_service import (
    QQCC_SCENE_PRESET_PROMPTS,
    normalize_qqcc_config,
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
    monkeypatch.setattr(edit_image_fsm, "ENABLE_FREE_EDIT_V2", True)
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
    assert "请选择生成方式" in reply_mock.await_args.args[1]
    reply_markup = reply_mock.await_args.kwargs["reply_markup"]
    assert reply_markup is not None
    inline_buttons = [
        button
        for row in reply_markup.inline_keyboard
        for button in row
    ]
    assert any(
        button.text == "🎨 自由P图 v3"
        and button.callback_data == edit_image_fsm.EDIT_LORA_FREE_EDIT_V2_CALLBACK
        for button in inline_buttons
    )


@pytest.mark.asyncio
async def test_start_edit_image_v2_skips_lora_selection(monkeypatch):
    reply_mock = AsyncMock()

    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr(edit_image_fsm, "ENABLE_FREE_EDIT_V2", True)
    monkeypatch.setattr(edit_image_fsm, "robust_reply_text", reply_mock)

    update = _build_update_with_message(text="自由P图 v2")
    context = SimpleNamespace(user_data={})

    monkeypatch.setitem(
        __import__("src.handlers.prompt_router", fromlist=["GLOBAL_REVERSE_MAP"]).GLOBAL_REVERSE_MAP,
        "自由P图 v2",
        "menu.free_edit_v2",
    )

    result = await edit_image_fsm.start_edit_image(update, context)

    assert result == edit_image_fsm.EditImageState.WAIT_REFERENCE_IMAGES
    assert context.user_data["edit_image_data"]["mode"] == "free_edit_v3"
    assert context.user_data["edit_image_data"]["cost"] == 5
    reply_mock.assert_awaited_once()
    assert "自由P图 v3" in reply_mock.await_args.args[1]
    assert reply_mock.await_args.kwargs["reply_markup"] is None


@pytest.mark.asyncio
async def test_edit_image_v2_submit_upgrades_to_v3_chain(monkeypatch):
    reply_mock = AsyncMock()
    scheduled = []
    captured = []

    async def fake_process_generation_task(**kwargs):
        captured.append(kwargs)
        return None, None

    def fake_create_background_task(_context, coroutine):
        scheduled.append(coroutine)

    monkeypatch.setattr(edit_image_fsm, "is_global_menu_command", lambda _text: False)
    monkeypatch.setattr(edit_image_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(edit_image_fsm.permission_service, "check_quota", AsyncMock())
    monkeypatch.setattr(edit_image_fsm, "process_generation_task", fake_process_generation_task)
    monkeypatch.setattr(edit_image_fsm, "create_background_task", fake_create_background_task)

    update = _build_update_with_message(text="make it cinematic")
    context = SimpleNamespace(
        bot=SimpleNamespace(),
        user_data={
            "in_conversation": "EDIT_IMAGE",
            "edit_image_data": {
                "mode": MODE_FREE_EDIT_V2,
                "cost": 5,
                "images": ["/tmp/single.png"],
            },
        },
    )

    result = await edit_image_fsm.receive_prompt(update, context)
    assert result == ConversationHandler.END
    await scheduled.pop()
    assert captured[-1]["task_type"] == MODE_PORNMASTER_FLUX2_EDIT_BF16
    assert captured[-1]["cost_override"] == 5
    assert captured[-1]["images"] == ["/tmp/single.png"]


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
@pytest.mark.parametrize(
    ("button_text", "route_key"),
    [
        ("💃 快速脱衣", "menu.photo_edit_undress"),
        ("🥵 快速自慰", "menu.photo_edit_masturbation"),
    ],
)
async def test_main_bot_stale_quick_image_entries_route_to_lazy_bot(
    monkeypatch, button_text, route_key
):
    reply_mock = AsyncMock()

    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr(quick_image_fsm, "robust_reply_text", reply_mock)
    monkeypatch.delenv("QQCC_LAZY_BOT_URL", raising=False)
    monkeypatch.setenv("QQCC_LAZY_BOT_USERNAME", "@QQCC666_bot")

    update = _build_update_with_message(text=button_text)
    context = SimpleNamespace(
        user_data={},
        lang="zh",
        t=lambda key, **_kwargs: {
            "system.open_lazy_bot_hint": "请前往懒人bot使用该功能",
            "menu.open_lazy_bot": "前往懒人bot",
            "system.lazy_bot_link_unavailable": "懒人bot入口暂未配置",
        }.get(key, key),
    )

    monkeypatch.setitem(
        __import__("src.handlers.prompt_router", fromlist=["GLOBAL_REVERSE_MAP"]).GLOBAL_REVERSE_MAP,
        button_text,
        route_key,
    )

    result = await quick_image_fsm.start_quick_image(update, context)

    assert result == ConversationHandler.END
    assert "quick_image_data" not in context.user_data
    reply_mock.assert_awaited_once()
    assert reply_mock.await_args.args[1] == "请前往懒人bot使用该功能"
    button = reply_mock.await_args.kwargs["reply_markup"].inline_keyboard[0][0]
    assert button.text == "前往懒人bot"
    assert button.url == "https://t.me/QQCC666_bot"


@pytest.mark.asyncio
async def test_qqcc_stale_quick_undress_entry_is_blocked(monkeypatch):
    reply_mock = AsyncMock()

    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr(quick_image_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        quick_image_fsm,
        "load_runtime_qqcc_config",
        AsyncMock(return_value=normalize_qqcc_config(None)),
    )
    monkeypatch.setitem(
        __import__(
            "src.handlers.prompt_router", fromlist=["GLOBAL_REVERSE_MAP"]
        ).GLOBAL_REVERSE_MAP,
        "💃 快速脱衣",
        "menu.photo_edit_undress",
    )

    update = _build_update_with_message(text="💃 快速脱衣")
    context = SimpleNamespace(
        bot=SimpleNamespace(id=100),
        user_data={},
        bot_data={"bot_client_type": "bot:qqcc"},
        lang="zh",
        t=lambda key, **_kwargs: {"qqcc.feature_disabled": "功能暂未开放"}.get(
            key, key
        ),
    )

    result = await quick_image_fsm.start_quick_image(update, context)

    assert result == ConversationHandler.END
    assert "in_conversation" not in context.user_data
    reply_mock.assert_awaited_once()
    assert reply_mock.await_args.args[1] == "功能暂未开放"


@pytest.mark.asyncio
async def test_qqcc_quick_faceswap_entry_waits_for_image(monkeypatch):
    reply_mock = AsyncMock()

    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr(quick_image_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        quick_image_fsm,
        "load_runtime_qqcc_config",
        AsyncMock(return_value=normalize_qqcc_config(None)),
    )
    monkeypatch.setitem(
        __import__(
            "src.handlers.prompt_router", fromlist=["GLOBAL_REVERSE_MAP"]
        ).GLOBAL_REVERSE_MAP,
        "快速换脸",
        "qqcc.menu.quick_faceswap",
    )

    update = _build_update_with_message(text="快速换脸")
    context = SimpleNamespace(
        bot=SimpleNamespace(id=100),
        user_data={},
        bot_data={"bot_client_type": "bot:qqcc"},
        lang="zh",
    )

    result = await quick_image_fsm.start_quick_image(update, context)

    assert result == quick_image_fsm.QuickImageState.WAIT_IMAGE
    assert context.user_data["quick_image_data"]["mode"] == MODE_RANDOM_FACESWAP
    assert context.user_data["quick_image_data"]["cost"] == 1
    reply_mock.assert_awaited_once()
    assert "快速换脸" in reply_mock.await_args.args[1]


@pytest.mark.asyncio
async def test_qqcc_ai_draw_scene_callback_waits_for_image(monkeypatch):
    reply_mock = AsyncMock()
    answer_mock = AsyncMock()
    config = normalize_qqcc_config(
        {
            "draw_scenes": [
                {
                    "id": "soft_light",
                    "name": "柔光写真",
                    "prompt": "soft light prompt",
                }
            ]
        }
    )

    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr(quick_image_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        quick_image_fsm,
        "load_runtime_qqcc_config",
        AsyncMock(return_value=config),
    )

    user = _build_user()
    callback_message = SimpleNamespace(chat_id=10001)
    update = SimpleNamespace(
        effective_user=user,
        effective_chat=SimpleNamespace(id=10001),
        message=None,
        edited_message=None,
        callback_query=SimpleNamespace(
            data=build_quick_draw_scene_callback_data("soft_light"),
            message=callback_message,
            answer=answer_mock,
            from_user=user,
        ),
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(id=100),
        user_data={},
        bot_data={"bot_client_type": "bot:qqcc"},
        lang="zh",
    )

    result = await quick_image_fsm.start_quick_image(update, context)

    assert result == quick_image_fsm.QuickImageState.WAIT_IMAGE
    assert context.user_data["quick_image_data"] == {
        "mode": MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
        "cost": 2,
        "image_path": None,
        "scene_id": "soft_light",
        "scene_kind": "draw",
        "mode_name": "柔光写真",
        "prompt_override": "soft light prompt",
        "engine": "free_edit_v2",
        "lora_name": "",
    }
    answer_mock.assert_awaited_once()
    reply_mock.assert_awaited_once()
    assert "柔光写真" in reply_mock.await_args.args[1]


@pytest.mark.asyncio
async def test_qqcc_ai_filter_scene_callback_waits_for_image(monkeypatch):
    reply_mock = AsyncMock()
    answer_mock = AsyncMock()
    config = normalize_qqcc_config(
        {
            "scene_preset_version": 1,
            "filter_scenes": [
                {
                    "id": "real_skin",
                    "name": "真实质感",
                    "prompt": "real skin prompt",
                }
            ],
        }
    )

    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr(quick_image_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        quick_image_fsm,
        "load_runtime_qqcc_config",
        AsyncMock(return_value=config),
    )

    user = _build_user()
    callback_message = SimpleNamespace(chat_id=10001)
    update = SimpleNamespace(
        effective_user=user,
        effective_chat=SimpleNamespace(id=10001),
        message=None,
        edited_message=None,
        callback_query=SimpleNamespace(
            data=build_quick_filter_scene_callback_data("real_skin"),
            message=callback_message,
            answer=answer_mock,
            from_user=user,
        ),
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(id=100),
        user_data={},
        bot_data={"bot_client_type": "bot:qqcc"},
        lang="zh",
    )

    result = await quick_image_fsm.start_quick_image(update, context)

    assert result == quick_image_fsm.QuickImageState.WAIT_IMAGE
    assert context.user_data["quick_image_data"]["scene_id"] == "real_skin"
    assert context.user_data["quick_image_data"]["scene_kind"] == "filter"
    assert context.user_data["quick_image_data"]["mode_name"] == "真实质感"
    answer_mock.assert_awaited_once()
    reply_mock.assert_awaited_once()
    assert "真实质感" in reply_mock.await_args.args[1]


@pytest.mark.asyncio
async def test_qqcc_ai_draw_deleted_scene_callback_is_blocked(monkeypatch):
    edit_mock = AsyncMock()
    answer_mock = AsyncMock()
    config = normalize_qqcc_config(
        {
            "draw_scenes": [
                {
                    "id": "anime",
                    "name": "动漫风",
                    "prompt": "anime style prompt",
                }
            ]
        }
    )

    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr(quick_image_fsm, "robust_edit_text", edit_mock)
    monkeypatch.setattr(
        quick_image_fsm,
        "load_runtime_qqcc_config",
        AsyncMock(return_value=config),
    )

    user = _build_user()
    callback_message = SimpleNamespace(chat_id=10001)
    update = SimpleNamespace(
        effective_user=user,
        effective_chat=SimpleNamespace(id=10001),
        message=None,
        edited_message=None,
        callback_query=SimpleNamespace(
            data=build_quick_draw_scene_callback_data("soft_light"),
            message=callback_message,
            answer=answer_mock,
            from_user=user,
        ),
    )
    context = SimpleNamespace(
        user_data={},
        bot_data={"bot_client_type": "bot:qqcc"},
        lang="zh",
        t=lambda key, **_kwargs: {"qqcc.feature_disabled": "功能暂未开放"}.get(
            key, key
        ),
    )

    result = await quick_image_fsm.start_quick_image(update, context)

    assert result == ConversationHandler.END
    assert "quick_image_data" not in context.user_data
    answer_mock.assert_awaited_once()
    edit_mock.assert_awaited_once_with(
        callback_message, "功能暂未开放", parse_mode="Markdown"
    )


@pytest.mark.asyncio
async def test_quick_image_i2i_draw_submits_inpaint_task(monkeypatch):
    reply_mock = AsyncMock()
    scheduled = []
    captured = {}

    async def fake_process_generation_task(**kwargs):
        captured.update(kwargs)
        return None, None

    def fake_create_background_task(_context, coroutine):
        scheduled.append(coroutine)

    monkeypatch.setattr(quick_image_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        quick_image_fsm,
        "_validate_quick_image_submission",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        quick_image_fsm,
        "_download_quick_image_input",
        AsyncMock(return_value="/tmp/i2i-draw.png"),
    )
    monkeypatch.setattr(
        quick_image_fsm, "process_generation_task", fake_process_generation_task
    )
    monkeypatch.setattr(
        quick_image_fsm, "create_background_task", fake_create_background_task
    )
    monkeypatch.setattr(
        quick_image_fsm,
        "load_prompts",
        lambda: {"i2i_draw_quick_undress": "保持面部稳定，保持身体姿势不变"},
    )

    update = SimpleNamespace(
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
        message=SimpleNamespace(
            document=None,
            photo=[SimpleNamespace(file_id="photo-file-id")],
            chat_id=10001,
        ),
    )
    context = SimpleNamespace(
        user_data={
            "in_conversation": "QUICK_IMAGE_i2i_draw",
            "quick_image_data": {
                "mode": MODE_I2I_DRAW,
                "cost": 3,
                "image_path": None,
            },
        },
        bot=SimpleNamespace(),
        lang="zh",
    )

    result = await quick_image_fsm.receive_image(update, context)

    assert result == ConversationHandler.END
    assert len(scheduled) == 1
    await scheduled[0]
    assert captured["task_type"] == MODE_I2I_DRAW
    assert captured["images"] == ["/tmp/i2i-draw.png"]
    assert "保持面部" in captured["prompt"]


@pytest.mark.asyncio
async def test_quick_image_cleans_downloaded_input_when_planning_rejects(
    tmp_path, monkeypatch
):
    reply_mock = AsyncMock()
    temp_root = tmp_path / "tmp"
    temp_root.mkdir()
    downloaded_path = temp_root / "quick-face.png"
    downloaded_path.write_text("x")

    monkeypatch.setattr(quick_image_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        quick_image_fsm,
        "_validate_quick_image_submission",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        quick_image_fsm,
        "_download_quick_image_input",
        AsyncMock(return_value=str(downloaded_path)),
    )
    monkeypatch.setattr(quick_image_fsm, "load_prompts", lambda: {})
    monkeypatch.setattr(quick_image_fsm, "list_quick_faceswap_template_files", lambda: [])
    monkeypatch.setattr("src.services.fsm_temp_file_service.TMP_DIR", str(temp_root))

    update = SimpleNamespace(
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
        message=SimpleNamespace(
            document=None,
            photo=[SimpleNamespace(file_id="photo-file-id")],
            chat_id=10001,
        ),
    )
    context = SimpleNamespace(
        user_data={
            "in_conversation": "QUICK_IMAGE_random_faceswap",
            "quick_image_data": {
                "mode": MODE_RANDOM_FACESWAP,
                "cost": 1,
                "image_path": None,
            },
        },
        bot=SimpleNamespace(),
        lang="zh",
    )

    result = await quick_image_fsm.receive_image(update, context)

    assert result == ConversationHandler.END
    assert not downloaded_path.exists()
    assert "quick_image_data" not in context.user_data
    assert "in_conversation" not in context.user_data


@pytest.mark.asyncio
async def test_qqcc_ai_draw_scene_submits_free_edit_v2_single_task(monkeypatch):
    reply_mock = AsyncMock()
    scheduled = []
    captured = {}
    config = normalize_qqcc_config(
        {
            "draw_scenes": [
                {
                    "id": "soft_light",
                    "name": "柔光写真",
                    "prompt": "soft light prompt",
                }
            ]
        }
    )

    async def fake_process_generation_task(**kwargs):
        captured.update(kwargs)
        return None, None

    def fake_create_background_task(_context, coroutine):
        scheduled.append(coroutine)

    monkeypatch.setattr(quick_image_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        quick_image_fsm,
        "load_runtime_qqcc_config",
        AsyncMock(return_value=config),
    )
    monkeypatch.setattr(
        quick_image_fsm,
        "_validate_quick_image_submission",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        quick_image_fsm,
        "_download_quick_image_input",
        AsyncMock(return_value="/tmp/draw.png"),
    )
    monkeypatch.setattr(
        quick_image_fsm, "process_generation_task", fake_process_generation_task
    )
    monkeypatch.setattr(
        quick_image_fsm, "create_background_task", fake_create_background_task
    )
    monkeypatch.setattr(quick_image_fsm, "load_prompts", lambda: {})

    update = SimpleNamespace(
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
        message=SimpleNamespace(
            document=None,
            photo=[SimpleNamespace(file_id="photo-file-id")],
            chat_id=10001,
        ),
    )
    context = SimpleNamespace(
        user_data={
            "in_conversation": "QUICK_IMAGE_pornmaster_flux2_single_edit",
            "quick_image_data": {
                "mode": MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
                "cost": 2,
                "image_path": None,
                "scene_id": "soft_light",
            },
        },
        bot=SimpleNamespace(),
        bot_data={"bot_client_type": "bot:qqcc"},
        lang="zh",
    )

    result = await quick_image_fsm.receive_image(update, context)

    assert result == ConversationHandler.END
    assert len(scheduled) == 1
    await scheduled[0]
    assert captured["task_type"] == MODE_PORNMASTER_FLUX2_SINGLE_EDIT
    assert captured["images"] == ["/tmp/draw.png"]
    assert captured["prompt"] == "soft light prompt"
    assert context.bot_data["bot_client_type"] == "bot:qqcc"


@pytest.mark.asyncio
async def test_qqcc_default_ai_draw_scene_uses_scene_prompt_with_free_edit(monkeypatch):
    reply_mock = AsyncMock()
    scheduled = []
    captured = {}
    config = normalize_qqcc_config(None)

    async def fake_process_generation_task(**kwargs):
        captured.update(kwargs)
        return None, None

    def fake_create_background_task(_context, coroutine):
        scheduled.append(coroutine)

    monkeypatch.setattr(quick_image_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        quick_image_fsm,
        "load_runtime_qqcc_config",
        AsyncMock(return_value=config),
    )
    monkeypatch.setattr(
        quick_image_fsm,
        "_validate_quick_image_submission",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        quick_image_fsm,
        "_download_quick_image_input",
        AsyncMock(return_value="/tmp/default-draw.png"),
    )
    monkeypatch.setattr(
        quick_image_fsm, "process_generation_task", fake_process_generation_task
    )
    monkeypatch.setattr(
        quick_image_fsm, "create_background_task", fake_create_background_task
    )
    load_prompts_mock = Mock(side_effect=AssertionError("QQCC draw scenes must not read prompts.ini"))
    monkeypatch.setattr(quick_image_fsm, "load_prompts", load_prompts_mock)

    update = SimpleNamespace(
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
        message=SimpleNamespace(
            document=None,
            photo=[SimpleNamespace(file_id="photo-file-id")],
            chat_id=10001,
        ),
    )
    context = SimpleNamespace(
        user_data={
            "in_conversation": "QUICK_IMAGE_edit",
            "quick_image_data": {
                "mode": MODE_EDIT,
                "cost": 2,
                "image_path": None,
                "scene_id": "quick_undress",
            },
        },
        bot=SimpleNamespace(),
        bot_data={"bot_client_type": "bot:qqcc"},
        lang="zh",
    )

    result = await quick_image_fsm.receive_image(update, context)

    assert result == ConversationHandler.END
    assert len(scheduled) == 1
    await scheduled[0]
    assert captured["task_type"] == MODE_EDIT
    assert captured["images"] == ["/tmp/default-draw.png"]
    assert captured["prompt"] == QQCC_SCENE_PRESET_PROMPTS["undress"]
    load_prompts_mock.assert_not_called()


@pytest.mark.asyncio
async def test_qqcc_ai_draw_scene_runs_postprocess_chain_before_final_result(monkeypatch):
    reply_mock = AsyncMock(return_value=SimpleNamespace(message_id=77))
    scheduled = []
    calls = []
    config = normalize_qqcc_config(
        {
            "draw_scenes": [
                {
                    "id": "soft_light",
                    "name": "柔光写真",
                    "prompt": "soft light prompt",
                    "postprocess_draw_scene_id": "polish",
                },
                {
                    "id": "polish",
                    "name": "精修",
                    "prompt": "polish prompt",
                },
            ]
        }
    )

    async def fake_process_generation_task(**kwargs):
        calls.append(kwargs)
        return b"image-bytes", f"output-{len(calls)}.png"

    def fake_create_background_task(_context, coroutine):
        scheduled.append(coroutine)

    validate_submission = AsyncMock(return_value=True)
    monkeypatch.setattr(quick_image_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        quick_image_fsm,
        "load_runtime_qqcc_config",
        AsyncMock(return_value=config),
    )
    monkeypatch.setattr(
        quick_image_fsm,
        "_validate_quick_image_submission",
        validate_submission,
    )
    monkeypatch.setattr(
        quick_image_fsm,
        "_download_quick_image_input",
        AsyncMock(return_value="/tmp/draw.png"),
    )
    monkeypatch.setattr(
        quick_image_fsm, "process_generation_task", fake_process_generation_task
    )
    monkeypatch.setattr(
        quick_image_fsm,
        "download_output_file_to_fsm_temp",
        AsyncMock(return_value="/tmp/soft-light-output.png"),
    )
    monkeypatch.setattr(
        quick_image_fsm, "create_background_task", fake_create_background_task
    )
    monkeypatch.setattr(quick_image_fsm, "load_prompts", lambda: {})

    update = SimpleNamespace(
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
        message=SimpleNamespace(
            document=None,
            photo=[SimpleNamespace(file_id="photo-file-id")],
            chat_id=10001,
        ),
    )
    context = SimpleNamespace(
        user_data={
            "in_conversation": "QUICK_IMAGE_pornmaster_flux2_single_edit",
            "quick_image_data": {
                "mode": MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
                "cost": 2,
                "image_path": None,
                "scene_id": "soft_light",
            },
        },
        bot=SimpleNamespace(),
        bot_data={"bot_client_type": "bot:qqcc"},
        lang="zh",
    )

    result = await quick_image_fsm.receive_image(update, context)

    assert result == ConversationHandler.END
    assert validate_submission.await_args.kwargs["cost"] == 4
    assert len(scheduled) == 1
    await scheduled[0]
    assert calls[0]["prompt"] == "soft light prompt"
    assert calls[0]["images"] == ["/tmp/draw.png"]
    assert calls[0]["send_result"] is False
    assert calls[0]["allow_contribute"] is False
    assert calls[1]["prompt"] == "polish prompt"
    assert calls[1]["images"] == ["/tmp/soft-light-output.png"]
    assert calls[1]["send_result"] is True
    assert calls[1]["allow_contribute"] is False


@pytest.mark.asyncio
async def test_qqcc_ai_draw_scene_submits_legacy_free_edit_with_lora(monkeypatch):
    reply_mock = AsyncMock()
    scheduled = []
    captured = {}
    config = normalize_qqcc_config(
        {
            "draw_scenes": [
                {
                    "id": "realistic",
                    "name": "逼真质感",
                    "prompt": "realistic prompt",
                    "engine": "free_edit",
                    "lora_name": "qwen/YARN_1.0.safetensors",
                }
            ]
        }
    )

    async def fake_process_generation_task(**kwargs):
        captured.update(kwargs)
        return None, None

    def fake_create_background_task(_context, coroutine):
        scheduled.append(coroutine)

    monkeypatch.setattr(quick_image_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        quick_image_fsm,
        "load_runtime_qqcc_config",
        AsyncMock(return_value=config),
    )
    monkeypatch.setattr(
        quick_image_fsm,
        "_validate_quick_image_submission",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        quick_image_fsm,
        "_download_quick_image_input",
        AsyncMock(return_value="/tmp/draw.png"),
    )
    monkeypatch.setattr(
        quick_image_fsm, "process_generation_task", fake_process_generation_task
    )
    monkeypatch.setattr(
        quick_image_fsm, "create_background_task", fake_create_background_task
    )
    monkeypatch.setattr(quick_image_fsm, "load_prompts", lambda: {})

    update = SimpleNamespace(
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
        message=SimpleNamespace(
            document=None,
            photo=[SimpleNamespace(file_id="photo-file-id")],
            chat_id=10001,
        ),
    )
    context = SimpleNamespace(
        user_data={
            "in_conversation": "QUICK_IMAGE_img2img_lora",
            "quick_image_data": {
                "mode": MODE_IMG2IMG_LORA,
                "cost": 2,
                "image_path": None,
                "scene_id": "realistic",
            },
        },
        bot=SimpleNamespace(),
        bot_data={"bot_client_type": "bot:qqcc"},
        lang="zh",
    )

    result = await quick_image_fsm.receive_image(update, context)

    assert result == ConversationHandler.END
    assert len(scheduled) == 1
    await scheduled[0]
    assert captured["task_type"] == MODE_IMG2IMG_LORA
    assert captured["images"] == ["/tmp/draw.png"]
    assert captured["prompt"] == "realistic prompt"
    assert captured["lora_name"] == "qwen/YARN_1.0.safetensors"
    assert captured["lora_strength"] == 0.3


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
async def test_edit_image_lora_selection_can_switch_to_free_edit_v2(monkeypatch):
    edit_mock = AsyncMock()
    monkeypatch.setattr(edit_image_fsm, "robust_edit_text", edit_mock)

    query = SimpleNamespace(
        data=edit_image_fsm.EDIT_LORA_FREE_EDIT_V2_CALLBACK,
        answer=AsyncMock(),
        message=SimpleNamespace(),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(
        user_data={
            "edit_image_data": {
                "mode": MODE_IMG2IMG_LORA,
                "cost": 6,
                "images": [],
                "lora_name": "legacy-lora",
                "lora_strength": 0.8,
            }
        }
    )

    result = await edit_image_fsm.handle_lora_selection(update, context)

    assert result == edit_image_fsm.EditImageState.WAIT_REFERENCE_IMAGES
    query.answer.assert_awaited_once()
    fsm_data = context.user_data["edit_image_data"]
    assert fsm_data["mode"] == "free_edit_v3"
    assert fsm_data["cost"] == 5
    assert "lora_name" not in fsm_data
    assert "lora_strength" not in fsm_data
    edit_mock.assert_awaited_once()
    assert "自由P图 v3" in edit_mock.await_args.args[1]


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
async def test_ltx_video_receive_image_after_setup_requests_prompt(monkeypatch):
    reply_mock = AsyncMock()
    download_mock = AsyncMock(return_value="/tmp/ltx_video.png")

    monkeypatch.setattr(ltx_video_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        ltx_video_fsm,
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
        effective_chat=SimpleNamespace(id=10001),
        message=message,
    )
    def translate(key, **kwargs):
        if key == "fsm.ltx_video.prompt_request_text":
            return (
                f"素材已收到。{kwargs['mode']} {kwargs['resolution']} "
                f"{kwargs['duration']} {kwargs['cost']}。请发送提示词。"
            )
        return f"T:{key}"

    context = SimpleNamespace(
        bot=SimpleNamespace(get_file=AsyncMock(return_value=SimpleNamespace())),
        user_data={
            "ltx_video_data": {
                "resolution": "1280x704",
                "duration": "5s",
                "ltx_mode": "i2v",
                "image_path": None,
            }
        },
        lang="zh",
        t=translate,
    )

    result = await ltx_video_fsm.receive_image(update, context)

    assert result == ltx_video_fsm.LtxVideoState.WAIT_SETTINGS_AND_PROMPT
    context.bot.get_file.assert_awaited_once_with("photo-file-id")
    download_mock.assert_awaited_once()
    assert context.user_data["ltx_video_data"]["image_path"] == "/tmp/ltx_video.png"
    reply_mock.assert_awaited_once()
    assert reply_mock.await_args.args[0] is message
    assert "提示词" in reply_mock.await_args.args[1]
    assert "请在下方选择" not in reply_mock.await_args.args[1]
    assert "T:fsm.image_to_video.current_lora" in reply_mock.await_args.args[1]
    assert reply_mock.await_args.kwargs == {"parse_mode": "Markdown"}


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
async def test_ltx_video_lora_selection_sets_name_and_opens_setup_panel(monkeypatch):
    edit_mock = AsyncMock()
    monkeypatch.setattr(ltx_video_fsm, "robust_edit_text", edit_mock)

    query = SimpleNamespace(
        data="toggle_ltx_lora_reasoning",
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

    assert result == ltx_video_fsm.LtxVideoState.WAIT_LORA_SELECTION
    assert context.user_data["ltx_video_data"]["lora_items"] == [
        {
            "name": "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors",
            "strength": 0.8,
        }
    ]
    query.answer.assert_awaited_once()

    query.data = "done_ltx_lora_select"
    result = await ltx_video_fsm.handle_lora_selection(update, context)

    assert result == ltx_video_fsm.LtxVideoState.WAIT_MODE_SELECTION
    assert edit_mock.await_count == 2
    callback_data = [
        button.callback_data
        for row in edit_mock.await_args.kwargs["reply_markup"].inline_keyboard
        for button in row
    ]
    assert "ltx_mode_i2v" in callback_data
    assert "ltx_mode_flf2v" in callback_data
    assert "ltx_mode_v2v_audio" not in callback_data
    assert "set_ltxdur_10s" in callback_data
    assert "ltx_setup_confirm" not in callback_data
    assert "发送起始帧图片" in edit_mock.await_args.args[1]


@pytest.mark.asyncio
async def test_ltx_video_setup_panel_updates_mode_and_duration(monkeypatch):
    edit_mock = AsyncMock()
    monkeypatch.setattr(ltx_video_fsm, "robust_edit_text", edit_mock)

    query = SimpleNamespace(
        data="ltx_mode_flf2v",
        answer=AsyncMock(),
        message=SimpleNamespace(),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(
        user_data={
            "ltx_video_data": {
                "resolution": "1280x704",
                "duration": "5s",
                "ltx_mode": "i2v",
                "image_path": None,
                "lora_items": [],
            }
        },
        lang="zh",
        t=lambda key, **kwargs: f"T:{key}",
    )

    result = await ltx_video_fsm.process_initial_setup(update, context)

    assert result == ltx_video_fsm.LtxVideoState.WAIT_MODE_SELECTION
    assert context.user_data["ltx_video_data"]["ltx_mode"] == "flf2v"
    callback_data = [
        button.callback_data
        for row in edit_mock.await_args.kwargs["reply_markup"].inline_keyboard
        for button in row
    ]
    assert "ltx_setup_confirm" not in callback_data

    query.data = "set_ltxdur_15s"
    result = await ltx_video_fsm.process_initial_setup(update, context)

    assert result == ltx_video_fsm.LtxVideoState.WAIT_MODE_SELECTION
    assert context.user_data["ltx_video_data"]["duration"] == "15s"


@pytest.mark.asyncio
async def test_ltx_video_setup_panel_accepts_start_image_without_confirm(monkeypatch):
    reply_mock = AsyncMock()
    download_mock = AsyncMock(return_value="/tmp/ltx_setup_start.png")

    monkeypatch.setattr(ltx_video_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        ltx_video_fsm,
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
        effective_chat=SimpleNamespace(id=10001),
        message=message,
    )

    def translate(key, **kwargs):
        if key == "fsm.ltx_video.prompt_request_text":
            return f"素材已收到。{kwargs['mode']}。请发送提示词。"
        return f"T:{key}"

    context = SimpleNamespace(
        bot=SimpleNamespace(get_file=AsyncMock(return_value=SimpleNamespace())),
        user_data={
            "ltx_video_data": {
                "resolution": "1280x704",
                "duration": "5s",
                "ltx_mode": "i2v",
                "image_path": None,
                "lora_items": [],
            }
        },
        lang="zh",
        t=translate,
    )

    result = await ltx_video_fsm.receive_initial_setup_image(update, context)

    assert result == ltx_video_fsm.LtxVideoState.WAIT_SETTINGS_AND_PROMPT
    context.bot.get_file.assert_awaited_once_with("photo-file-id")
    assert context.user_data["ltx_video_data"]["image_path"] == (
        "/tmp/ltx_setup_start.png"
    )
    assert "提示词" in reply_mock.await_args.args[1]


@pytest.mark.asyncio
async def test_ltx_video_setup_confirm_routes_start_end_mode_to_image_upload(
    monkeypatch,
):
    edit_mock = AsyncMock()
    monkeypatch.setattr(ltx_video_fsm, "robust_edit_text", edit_mock)

    query = SimpleNamespace(
        data="ltx_setup_confirm",
        answer=AsyncMock(),
        message=SimpleNamespace(),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(
        user_data={
            "ltx_video_data": {
                "resolution": "1280x704",
                "duration": "10s",
                "ltx_mode": "flf2v",
                "image_path": None,
                "end_image_path": None,
                "lora_items": [],
            }
        },
        lang="zh",
        t=lambda key, **kwargs: f"T:{key}",
    )

    result = await ltx_video_fsm.process_initial_setup(update, context)

    assert result == ltx_video_fsm.LtxVideoState.WAIT_IMAGE
    edit_mock.assert_awaited_once()
    assert "起始帧" in edit_mock.await_args.args[1]


@pytest.mark.asyncio
async def test_ltx_video_confirm_generation_forwards_selected_lora(monkeypatch):
    safe_answer_mock = AsyncMock()
    create_background_task_mock = MagicMock()
    process_task_mock = MagicMock(return_value=object())
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
    assert process_task_mock.call_args.kwargs["resolution"] == "1280x704"
    assert process_task_mock.call_args.kwargs["duration"] == "10s"
    assert "ltx_video_resolution" not in context.user_data
    assert "ltx_video_duration" not in context.user_data
    assert "ltx_video_mode" not in context.user_data


@pytest.mark.asyncio
async def test_ltx_video_confirm_generation_forwards_start_end_mode(monkeypatch):
    safe_answer_mock = AsyncMock()
    create_background_task_mock = MagicMock()
    process_task_mock = MagicMock(return_value=object())
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
                "duration": "15s",
                "ltx_mode": "flf2v",
                "prompt": "bridge the motion",
                "image_path": "/tmp/start.png",
                "end_image_path": "/tmp/end.png",
                "lora_items": [],
            }
        },
        t=lambda key, **kwargs: f"T:{key}",
    )

    result = await ltx_video_fsm.confirm_generation(update, context)

    assert result == ConversationHandler.END
    quota_mock.assert_awaited_once()
    process_task_mock.assert_called_once()
    assert process_task_mock.call_args.kwargs["ltx_mode"] == "flf2v"
    assert process_task_mock.call_args.kwargs["resolution"] == "1280x704"
    assert process_task_mock.call_args.kwargs["duration"] == "15s"
    assert process_task_mock.call_args.kwargs["image_path"] == "/tmp/start.png"
    assert process_task_mock.call_args.kwargs["end_image_path"] == "/tmp/end.png"


@pytest.mark.asyncio
async def test_ltx_video_extension_initializes_single_start_frame_with_chain_context(
    monkeypatch,
):
    reply_mock = AsyncMock()
    prepare_seed_mock = AsyncMock(
        return_value=SimpleNamespace(
            base_task_id="ltx-task-2",
            history=SimpleNamespace(task_id="ltx-task-2"),
            fsm_data={
                "resolution": "1280x704",
                "duration": "10s",
                "ltx_mode": "i2v",
                "image_path": "/tmp/ltx-tail.png",
                "end_image_path": None,
                "video_path": None,
                "lora_items": [
                    {
                        "name": "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors",
                        "strength": 0.8,
                    }
                ],
                "is_extension": True,
                "extension_prev_task_id": "ltx-task-2",
                "chain_task_ids": ["ltx-task-1", "ltx-task-2"],
            },
        )
    )

    monkeypatch.setattr(ltx_video_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        ltx_video_fsm,
        "prepare_ltx_extension_fsm_data",
        prepare_seed_mock,
    )

    query = SimpleNamespace(
        data="ltx_extend:ltx-task-2",
        answer=AsyncMock(),
        message=SimpleNamespace(message_id=77),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=_build_user(),
        effective_message=query.message,
    )
    context = SimpleNamespace(
        user_data={},
        bot_data={},
        lang="zh",
        t=lambda key, **kwargs: f"T:{key}",
    )

    result = await ltx_video_fsm.start_ltx_video_extension(update, context)

    assert result == ltx_video_fsm.LtxVideoState.WAIT_MODE_SELECTION
    prepare_seed_mock.assert_awaited_once_with(
        base_task_id="ltx-task-2",
        telegram_user_id=12345,
        username="tester",
        meta={},
        max_loras=3,
    )
    data = context.user_data["ltx_video_data"]
    assert data["ltx_mode"] == "i2v"
    assert data["image_path"] == "/tmp/ltx-tail.png"
    assert data["is_extension"] is True
    assert data["extension_prev_task_id"] == "ltx-task-2"
    assert data["chain_task_ids"] == ["ltx-task-1", "ltx-task-2"]
    assert data["lora_items"] == [
        {
            "name": "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors",
            "strength": 0.8,
        }
    ]
    reply_mock.assert_awaited_once()
    assert "上一段尾帧" in reply_mock.await_args.args[1]
    callback_data = [
        button.callback_data
        for row in reply_mock.await_args.kwargs["reply_markup"].inline_keyboard
        for button in row
    ]
    assert "ltx_mode_i2v" in callback_data
    assert "ltx_mode_flf2v" in callback_data
    assert "ltx_mode_v2v_audio" not in callback_data
    assert "set_ltxdur_10s" in callback_data
    assert "ltx_setup_confirm" not in callback_data
    assert "直接发送提示词" in reply_mock.await_args.args[1]
    assert "发送终止帧图片" in reply_mock.await_args.args[1]
    assert "确定" not in reply_mock.await_args.args[1]


@pytest.mark.asyncio
async def test_ltx_video_extension_accepts_end_frame_image_without_confirm(
    monkeypatch,
):
    reply_mock = AsyncMock()
    download_mock = AsyncMock(return_value="/tmp/ltx-extension-end.png")

    monkeypatch.setattr(ltx_video_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        ltx_video_fsm,
        "download_telegram_file_to_fsm_temp",
        download_mock,
    )

    message = SimpleNamespace(
        document=None,
        photo=[SimpleNamespace(file_id="end-frame-file-id")],
        chat_id=10001,
    )
    update = SimpleNamespace(
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
        message=message,
    )

    def translate(key, **kwargs):
        if key == "fsm.ltx_video.prompt_request_text":
            return f"素材已收到。{kwargs['mode']}。请发送提示词。"
        return f"T:{key}"

    context = SimpleNamespace(
        bot=SimpleNamespace(get_file=AsyncMock(return_value=SimpleNamespace())),
        user_data={
            "ltx_video_data": {
                "resolution": "1280x704",
                "duration": "10s",
                "ltx_mode": "i2v",
                "image_path": "/tmp/ltx-tail.png",
                "end_image_path": None,
                "lora_items": [],
                "is_extension": True,
            }
        },
        lang="zh",
        t=translate,
    )

    result = await ltx_video_fsm.receive_initial_setup_image(update, context)

    assert result == ltx_video_fsm.LtxVideoState.WAIT_SETTINGS_AND_PROMPT
    context.bot.get_file.assert_awaited_once_with("end-frame-file-id")
    data = context.user_data["ltx_video_data"]
    assert data["ltx_mode"] == "flf2v"
    assert data["image_path"] == "/tmp/ltx-tail.png"
    assert data["end_image_path"] == "/tmp/ltx-extension-end.png"
    assert "提示词" in reply_mock.await_args.args[1]


@pytest.mark.asyncio
async def test_ltx_video_extension_accepts_prompt_without_setup_confirm(
    monkeypatch,
):
    reply_mock = AsyncMock()
    monkeypatch.setattr(ltx_video_fsm, "robust_reply_text", reply_mock)

    message = SimpleNamespace(
        text="continue the motion",
        chat_id=10001,
    )
    update = SimpleNamespace(
        effective_user=_build_user(),
        effective_chat=SimpleNamespace(id=10001),
        message=message,
    )
    context = SimpleNamespace(
        user_data={
            "ltx_video_data": {
                "resolution": "1280x704",
                "duration": "10s",
                "ltx_mode": "i2v",
                "image_path": "/tmp/ltx-tail.png",
                "end_image_path": None,
                "lora_items": [],
                "is_extension": True,
            }
        },
        lang="zh",
        t=lambda key, **kwargs: f"T:{key}",
    )

    result = await ltx_video_fsm.receive_initial_setup_text(update, context)

    assert result == ltx_video_fsm.LtxVideoState.WAIT_CONFIRMATION
    assert context.user_data["ltx_video_data"]["prompt"] == "continue the motion"
    reply_markup = reply_mock.await_args.kwargs["reply_markup"]
    assert reply_markup.inline_keyboard[0][0].callback_data == "confirm_ltx_video"


@pytest.mark.asyncio
async def test_ltx_video_extension_confirm_add_end_frame_requests_end_image(
    monkeypatch,
):
    edit_mock = AsyncMock()
    monkeypatch.setattr(ltx_video_fsm, "robust_edit_text", edit_mock)

    query = SimpleNamespace(
        data="ltx_setup_confirm",
        answer=AsyncMock(),
        message=SimpleNamespace(),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(
        user_data={
            "ltx_video_data": {
                "resolution": "1280x704",
                "duration": "10s",
                "ltx_mode": "flf2v",
                "image_path": "/tmp/ltx-tail.png",
                "end_image_path": None,
                "lora_items": [],
                "is_extension": True,
            }
        },
        lang="zh",
        t=lambda key, **kwargs: f"T:{key}",
    )

    result = await ltx_video_fsm.process_initial_setup(update, context)

    assert result == ltx_video_fsm.LtxVideoState.WAIT_END_IMAGE
    assert context.user_data["ltx_video_data"]["image_path"] == "/tmp/ltx-tail.png"
    edit_mock.assert_awaited_once()
    assert "终止帧" in edit_mock.await_args.args[1]


@pytest.mark.asyncio
async def test_ltx_video_extension_confirm_direct_continuation_requests_prompt(
    monkeypatch,
):
    edit_mock = AsyncMock()
    monkeypatch.setattr(ltx_video_fsm, "robust_edit_text", edit_mock)

    def translate(key, **kwargs):
        if key == "fsm.ltx_video.prompt_request_text":
            return f"素材已收到。{kwargs['mode']} {kwargs['duration']}。请发送提示词。"
        return f"T:{key}"

    query = SimpleNamespace(
        data="ltx_setup_confirm",
        answer=AsyncMock(),
        message=SimpleNamespace(),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(
        user_data={
            "ltx_video_data": {
                "resolution": "1280x704",
                "duration": "10s",
                "ltx_mode": "i2v",
                "image_path": "/tmp/ltx-tail.png",
                "end_image_path": None,
                "lora_items": [],
                "is_extension": True,
            }
        },
        lang="zh",
        t=translate,
    )

    result = await ltx_video_fsm.process_initial_setup(update, context)

    assert result == ltx_video_fsm.LtxVideoState.WAIT_SETTINGS_AND_PROMPT
    edit_mock.assert_awaited_once()
    assert "提示词" in edit_mock.await_args.args[1]
    assert "请在下方选择" not in edit_mock.await_args.args[1]


@pytest.mark.asyncio
async def test_ltx_video_confirm_generation_forwards_extension_chain_context(
    monkeypatch,
):
    safe_answer_mock = AsyncMock()
    create_background_task_mock = MagicMock()
    process_task_mock = MagicMock(return_value=object())
    edit_mock = AsyncMock()
    quota_mock = AsyncMock()

    monkeypatch.setattr("src.utils.safe_answer_query", safe_answer_mock)
    monkeypatch.setattr(
        ltx_video_fsm,
        "create_background_task",
        create_background_task_mock,
    )
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
                "duration": "5s",
                "ltx_mode": "i2v",
                "prompt": "continue the motion",
                "image_path": "/tmp/ltx-tail.png",
                "extension_prev_task_id": "ltx-task-2",
                "chain_task_ids": ["ltx-task-1", "ltx-task-2"],
                "lora_items": [],
            }
        },
        t=lambda key, **kwargs: f"T:{key}",
    )

    result = await ltx_video_fsm.confirm_generation(update, context)

    assert result == ConversationHandler.END
    process_task_mock.assert_called_once()
    assert process_task_mock.call_args.kwargs["ltx_mode"] == "i2v"
    assert process_task_mock.call_args.kwargs["ltx_prev_task_id"] == "ltx-task-2"
    assert process_task_mock.call_args.kwargs["ltx_chain_task_ids"] == [
        "ltx-task-1",
        "ltx-task-2",
    ]


def test_ltx_video_fsm_has_no_bot_video_audio_upload_state():
    handler = ltx_video_fsm.get_ltx_video_fsm_handler()
    state_names = {
        getattr(state, "name", str(state))
        for state in handler.states
        if state != ConversationHandler.TIMEOUT
    }
    mode_patterns = [
        getattr(callback, "pattern", None).pattern
        for callbacks in handler.states.values()
        for callback in callbacks
        if isinstance(callback, CallbackQueryHandler) and getattr(callback, "pattern", None)
    ]

    assert "WAIT_VIDEO" not in state_names
    assert not hasattr(ltx_video_fsm, "receive_video")
    assert all("v2v_audio" not in pattern for pattern in mode_patterns)


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
        "i2v_setup_res_small",
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
    assert [button.text for button in keyboard.inline_keyboard[4]] == [
        "✅ 5s (*1)",
        "8s (*2)",
        "10s (*3)",
    ]
    callback_data = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
    ]
    assert image_to_video_fsm.I2V_SETUP_CONFIRM not in callback_data
    assert "send the start image" in reply_mock.await_args.args[1]


@pytest.mark.asyncio
async def test_image_to_video_initial_setup_updates_all_choices(monkeypatch):
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

    query.answer.assert_awaited()


@pytest.mark.asyncio
async def test_image_to_video_setup_panel_accepts_start_image_without_confirm(
    monkeypatch,
):
    reply_mock = AsyncMock()
    download_mock = AsyncMock(return_value="/tmp/setup-start.png")
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

    result = await image_to_video_fsm.receive_initial_setup_image(update, context)

    assert result == image_to_video_fsm.ImageToVideoState.WAIT_SETTINGS_AND_PROMPT
    assert context.bot.get_file.await_args.args == ("photo-file-id",)
    assert context.user_data["image_to_video_data"]["image_path"] == (
        "/tmp/setup-start.png"
    )
    assert "请直接发送提示词" in reply_mock.await_args.args[1]


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
async def test_main_bot_stale_quick_video_text_entry_routes_to_lazy_bot(monkeypatch):
    reply_mock = AsyncMock()

    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr(quick_video_fsm, "robust_reply_text", reply_mock)
    monkeypatch.delenv("QQCC_LAZY_BOT_URL", raising=False)
    monkeypatch.setenv("QQCC_LAZY_BOT_USERNAME", "@QQCC666_bot")

    update = _build_update_with_message(text="🛏️ GIF Missionary")
    context = SimpleNamespace(
        user_data={},
        lang="en",
        t=lambda key, **_kwargs: {
            "system.open_lazy_bot_hint": "Please open Lazy Bot for this feature.",
            "menu.open_lazy_bot": "Open Lazy Bot",
            "system.lazy_bot_link_unavailable": "Lazy Bot link is not configured.",
        }.get(key, key),
    )

    monkeypatch.setitem(
        __import__("src.handlers.prompt_router", fromlist=["GLOBAL_REVERSE_MAP"]).GLOBAL_REVERSE_MAP,
        "🛏️ GIF Missionary",
        "menu.video_edit_missionary",
    )

    result = await quick_video_fsm.start_quick_video(update, context)

    assert result == ConversationHandler.END
    assert "quick_video_data" not in context.user_data
    reply_mock.assert_awaited_once()
    assert reply_mock.await_args.args[1] == "Please open Lazy Bot for this feature."
    button = reply_mock.await_args.kwargs["reply_markup"].inline_keyboard[0][0]
    assert button.text == "Open Lazy Bot"
    assert button.url == "https://t.me/QQCC666_bot"


@pytest.mark.asyncio
async def test_main_bot_stale_quick_video_callback_entry_routes_to_lazy_bot(monkeypatch):
    edit_mock = AsyncMock()
    answer_mock = AsyncMock()

    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr(quick_video_fsm, "robust_edit_text", edit_mock)
    monkeypatch.delenv("QQCC_LAZY_BOT_URL", raising=False)
    monkeypatch.setenv("QQCC_LAZY_BOT_USERNAME", "@QQCC666_bot")

    user = _build_user()
    callback_message = SimpleNamespace(chat_id=10001)
    update = SimpleNamespace(
        effective_user=user,
        effective_chat=SimpleNamespace(id=10001),
        message=None,
        edited_message=None,
        callback_query=SimpleNamespace(
            data="qvid_mode:menu.video_edit_doggy",
            message=callback_message,
            answer=answer_mock,
            from_user=user,
        ),
    )
    context = SimpleNamespace(
        user_data={},
        lang="zh",
        t=lambda key, **_kwargs: {
            "system.open_lazy_bot_hint": "请前往懒人bot使用该功能",
            "menu.open_lazy_bot": "前往懒人bot",
            "system.lazy_bot_link_unavailable": "懒人bot入口暂未配置",
        }.get(key, key),
    )

    result = await quick_video_fsm.start_quick_video(update, context)

    assert result == ConversationHandler.END
    assert "quick_video_data" not in context.user_data
    answer_mock.assert_awaited_once()
    edit_mock.assert_awaited_once()
    assert edit_mock.await_args.args == (callback_message, "请前往懒人bot使用该功能")
    button = edit_mock.await_args.kwargs["reply_markup"].inline_keyboard[0][0]
    assert button.text == "前往懒人bot"
    assert button.url == "https://t.me/QQCC666_bot"


@pytest.mark.asyncio
async def test_qqcc_legacy_quick_video_callback_selects_scene(monkeypatch):
    reply_mock = AsyncMock()
    answer_mock = AsyncMock()

    monkeypatch.setattr("src.utils.is_maintenance_mode", lambda: False)
    monkeypatch.setattr(quick_video_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        quick_video_fsm,
        "load_runtime_qqcc_config",
        AsyncMock(return_value=normalize_qqcc_config(None)),
    )

    user = _build_user()
    callback_message = SimpleNamespace(chat_id=10001)
    update = SimpleNamespace(
        effective_user=user,
        effective_chat=SimpleNamespace(id=10001),
        message=None,
        edited_message=None,
        callback_query=SimpleNamespace(
            data="qvid_mode:menu.video_edit_doggy",
            message=callback_message,
            answer=answer_mock,
            from_user=user,
        ),
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(id=100),
        user_data={},
        bot_data={"bot_client_type": "bot:qqcc"},
        lang="zh",
    )

    result = await quick_video_fsm.start_quick_video(update, context)

    assert result == quick_video_fsm.QuickVideoState.WAIT_IMAGE
    assert context.user_data["quick_video_data"]["scene_id"] == "doggy"
    assert context.user_data["quick_video_data"]["mode_name"] == "🎬 动图后入"
    answer_mock.assert_awaited_once()
    reply_mock.assert_awaited_once()
    assert reply_mock.await_args.args[0] is callback_message
    assert "动图后入" in reply_mock.await_args.args[1]


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
                    "mode": MODE_DOGGY_STYLE,
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
    cleanup_mock = Mock()
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
    monkeypatch.setattr(quick_video_fsm, "cleanup_fsm_temp_files", cleanup_mock)

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
                "mode": MODE_DOGGY_STYLE,
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
    cleanup_mock.assert_any_call(["/tmp/quick-video-input.png"])
    assert "in_conversation" not in context.user_data
    assert "quick_video_data" not in context.user_data


@pytest.mark.asyncio
async def test_quick_video_submission_uses_explicit_settings_without_user_data_bridge(
    monkeypatch,
):
    safe_answer_mock = AsyncMock()
    scheduled = []
    captured = {}
    query = SimpleNamespace(
        from_user=SimpleNamespace(id=12345),
        message=SimpleNamespace(chat_id=10001, message_id=777),
        answer=AsyncMock(),
    )

    async def fake_process_video_task_template(**kwargs):
        captured.update(kwargs)
        return None, None

    def fake_create_background_task(_context, coroutine):
        scheduled.append(coroutine)

    monkeypatch.setattr("src.utils.safe_answer_query", safe_answer_mock)
    monkeypatch.setattr(quick_video_fsm, "robust_edit_text", AsyncMock())
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "check_quota",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        quick_video_fsm,
        "process_video_task_template",
        fake_process_video_task_template,
    )
    monkeypatch.setattr(
        quick_video_fsm,
        "create_background_task",
        fake_create_background_task,
    )

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
                "mode": MODE_DOGGY_STYLE,
                "resolution": "720p",
                "duration": "8s",
                "image_path": "/tmp/quick-video-input.png",
            },
        },
    )

    result = await quick_video_fsm.start_generation(update, context)

    assert result == ConversationHandler.END
    assert len(scheduled) == 1
    await scheduled[0]
    assert captured["resolution"] == "720p"
    assert captured["duration"] == "8s"
    assert "custom_video_resolution" not in context.user_data
    assert "custom_video_duration" not in context.user_data
    assert "mode" not in context.user_data
    assert "quick_video_data" not in context.user_data
