from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, TypeHandler

from qqcc_bot import keyboards, main as qqcc_main, prompt_handlers
from qqcc_bot import commands as qqcc_commands
from src.handlers.fsm import quick_image_fsm, quick_video_fsm
from src.constants import MODE_PERFECT_VIDEO_INSERT
from src.handlers.fsm.quick_video_callback_data import (
    build_quick_video_mode_callback_data,
)
from src.handlers import prompt_router
from src.i18n.translator import get_text
from src.services.qqcc_config_service import normalize_qqcc_config


def _keyboard_texts(reply_markup):
    return [[getattr(button, "text", button) for button in row] for row in reply_markup.keyboard]


def _inline_keyboard_texts(reply_markup):
    return [[button.text for button in row] for row in reply_markup.inline_keyboard]


def _clear_main_bot_link_env(monkeypatch):
    for name in (
        "QQCC_MAIN_BOT_URL",
        "QQCC_MAIN_BOT_USERNAME",
    ):
        monkeypatch.delenv(name, raising=False)


def test_qqcc_main_menu_only_contains_lazy_generation_entries():
    keyboard = _keyboard_texts(keyboards.get_qqcc_main_menu_keyboard("zh"))

    assert keyboard == [
        ["💃 快速脱衣"],
        ["🖼️ 懒人P图", "AI动图"],
        ["前往主bot"],
    ]
    assert get_text("menu.video_edit", "zh") == "🎬 视频创作"


def test_qqcc_main_bot_link_keyboard_uses_url_button():
    keyboard = keyboards.get_qqcc_main_bot_link_keyboard(
        "zh", "https://t.me/main_bot"
    )

    button = keyboard.inline_keyboard[0][0]
    assert button.text == "前往主bot"
    assert button.url == "https://t.me/main_bot"


def test_resolve_main_bot_url_prefers_configured_url(monkeypatch):
    _clear_main_bot_link_env(monkeypatch)
    monkeypatch.setenv("QQCC_MAIN_BOT_URL", "https://t.me/main_bot?start=qqcc")
    monkeypatch.setenv("QQCC_MAIN_BOT_USERNAME", "@fallback_bot")

    assert qqcc_commands.resolve_main_bot_url() == "https://t.me/main_bot?start=qqcc"


def test_resolve_main_bot_url_can_build_from_username(monkeypatch):
    _clear_main_bot_link_env(monkeypatch)
    monkeypatch.setenv("QQCC_MAIN_BOT_USERNAME", "@main_bot")

    assert qqcc_commands.resolve_main_bot_url() == "https://t.me/main_bot"


def test_qqcc_photo_menu_excludes_fast_face_swap():
    rows = _keyboard_texts(keyboards.get_qqcc_photo_edit_keyboard("zh"))
    flat = [text for row in rows for text in row]

    assert "💃 快速脱衣" not in flat
    assert "🥵 快速自慰" in flat
    assert "🎭 随机换脸" in flat
    assert "🎭 快速换脸" not in flat


def test_qqcc_config_hides_closed_main_and_submenu_buttons():
    config = normalize_qqcc_config(
        {
            "main_buttons": {
                "quick_undress": False,
                "photo_edit": True,
                "video_edit": False,
                "main_bot_link": True,
            },
            "photo_buttons": {
                "masturbation": False,
                "random_faceswap": True,
            },
        }
    )

    main_rows = _keyboard_texts(keyboards.get_qqcc_main_menu_keyboard("zh", config))
    photo_rows = _keyboard_texts(keyboards.get_qqcc_photo_edit_keyboard("zh", config))

    assert main_rows == [["🖼️ 懒人P图"], ["前往主bot"]]
    assert photo_rows == [["🎭 随机换脸"], ["🔙 返回主菜单"]]


def test_qqcc_video_menu_contains_lazy_video_scenes():
    reply_markup = keyboards.get_qqcc_video_edit_inline_keyboard("zh")
    rows = _inline_keyboard_texts(reply_markup)
    flat = [text for row in rows for text in row]

    assert [len(row) for row in rows] == [3, 2]
    assert "🛌 动图传教士" in flat
    assert "🎬 动图后入" in flat
    assert "🎬 口交黑人" in flat
    assert "🎬 脱衣吐舌" in flat
    assert "🎬 特写口交" in flat
    assert reply_markup.inline_keyboard[0][0].callback_data == (
        build_quick_video_mode_callback_data("menu.video_edit_missionary")
    )


@pytest.mark.asyncio
async def test_qqcc_video_menu_route_replies_with_inline_scene_buttons(monkeypatch):
    monkeypatch.setattr(
        prompt_handlers,
        "load_runtime_qqcc_config",
        AsyncMock(return_value=normalize_qqcc_config(None)),
    )
    reply_text = AsyncMock()
    message = SimpleNamespace(reply_text=reply_text)
    update = SimpleNamespace(
        effective_message=message,
        message=None,
        edited_message=None,
    )
    context = SimpleNamespace(
        lang="zh",
        t=lambda key: f"translated:{key}",
    )

    await prompt_handlers.handle_video_edit_menu(update, context)

    reply_text.assert_awaited_once()
    kwargs = reply_text.await_args.kwargs
    assert kwargs["text"] == "translated:system.video_edit_hint"
    assert _inline_keyboard_texts(kwargs["reply_markup"]) == [
        ["🛌 动图传教士", "🎬 动图后入", "🎬 口交黑人"],
        ["🎬 脱衣吐舌", "🎬 特写口交"],
    ]


@pytest.mark.asyncio
async def test_qqcc_stale_photo_menu_button_is_blocked(monkeypatch):
    config = normalize_qqcc_config({"main_buttons": {"photo_edit": False}})
    monkeypatch.setattr(
        prompt_handlers,
        "load_runtime_qqcc_config",
        AsyncMock(return_value=config),
    )

    reply_text = AsyncMock()
    message = SimpleNamespace(reply_text=reply_text)
    update = SimpleNamespace(
        effective_message=message,
        message=None,
        edited_message=None,
    )
    context = SimpleNamespace(
        lang="zh",
        t=lambda key: {"qqcc.feature_disabled": "功能暂未开放"}.get(key, key),
    )

    await prompt_handlers.handle_photo_edit_menu(update, context)

    kwargs = reply_text.await_args.kwargs
    assert kwargs["text"] == "功能暂未开放"
    assert "🖼️ 懒人P图" not in [
        text for row in _keyboard_texts(kwargs["reply_markup"]) for text in row
    ]


def test_qqcc_prompt_routes_are_limited_to_lazy_menus():
    assert set(prompt_handlers.QQCC_PROMPT_ROUTES) == {
        "menu.photo_edit",
        "menu.video_edit",
        "menu.main_menu",
        "menu.back_main",
        "menu.open_main_bot",
    }


def test_qqcc_lazy_main_buttons_are_routable_without_main_bot_prompt_routes(monkeypatch):
    monkeypatch.setattr(prompt_router, "prompt_routes", {}, raising=False)

    prompt_router.build_global_menu_filter()

    assert prompt_router.GLOBAL_REVERSE_MAP["💃 快速脱衣"] == "menu.photo_edit_undress"
    assert prompt_router.GLOBAL_REVERSE_MAP["🖼️ 懒人P图"] == "menu.photo_edit"
    assert prompt_router.GLOBAL_REVERSE_MAP["AI动图"] == "menu.video_edit"
    assert prompt_router.GLOBAL_REVERSE_MAP["🎬 视频创作"] == "menu.video_edit"
    assert prompt_router.GLOBAL_REVERSE_MAP["前往主bot"] == "menu.open_main_bot"


def test_register_handlers_only_registers_qqcc_surface(monkeypatch):
    added_handlers = []
    error_handlers = []

    class FakeApp:
        def add_handler(self, handler, *args, **kwargs):
            added_handlers.append((handler, args, kwargs))

        def add_error_handler(self, handler):
            error_handlers.append(handler)

    monkeypatch.setattr(qqcc_main, "get_quick_image_fsm_handler", lambda: "quick-image")
    monkeypatch.setattr(qqcc_main, "get_quick_video_fsm_handler", lambda: "quick-video")

    qqcc_main.register_handlers(FakeApp())

    handlers = [item[0] for item in added_handlers]
    assert handlers[0].__class__ is TypeHandler
    assert "quick-image" in handlers
    assert "quick-video" in handlers
    assert sum(isinstance(handler, CommandHandler) for handler in handlers) == 2
    assert sum(isinstance(handler, CallbackQueryHandler) for handler in handlers) == 1
    assert sum(isinstance(handler, MessageHandler) for handler in handlers) == 1
    assert len(error_handlers) == 1


@pytest.mark.asyncio
async def test_qqcc_start_returns_simplified_menu(monkeypatch):
    _clear_main_bot_link_env(monkeypatch)
    monkeypatch.setattr(
        "qqcc_bot.commands.get_user_channel_status",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "qqcc_bot.commands.notify_inviter_reward",
        lambda *_args, **_kwargs: AsyncMock()(),
    )
    monkeypatch.setattr(
        "qqcc_bot.commands.load_runtime_qqcc_config",
        AsyncMock(return_value=normalize_qqcc_config(None)),
    )
    permission = SimpleNamespace(
        check_access=AsyncMock(return_value=None),
        ensure_user=AsyncMock(return_value=False),
    )
    monkeypatch.setattr("qqcc_bot.commands.permission_service", permission)

    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(
            id=123,
            username="tester",
            full_name="Tester",
            language_code="zh",
        ),
        message=SimpleNamespace(reply_text=reply_text),
    )
    context = SimpleNamespace(
        args=[],
        lang="zh",
        t=lambda key: f"translated:{key}",
        bot=object(),
        user_data={},
    )

    await qqcc_main.start(update, context)

    reply_text.assert_awaited_once()
    kwargs = reply_text.await_args.kwargs
    assert _keyboard_texts(kwargs["reply_markup"]) == [
        ["💃 快速脱衣"],
        ["🖼️ 懒人P图", "AI动图"],
        ["前往主bot"],
    ]


@pytest.mark.asyncio
async def test_qqcc_start_keeps_main_bot_jump_in_menu_when_configured(monkeypatch):
    _clear_main_bot_link_env(monkeypatch)
    monkeypatch.setenv("QQCC_MAIN_BOT_URL", "https://t.me/main_bot")
    monkeypatch.setattr(
        "qqcc_bot.commands.get_user_channel_status",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "qqcc_bot.commands.notify_inviter_reward",
        lambda *_args, **_kwargs: AsyncMock()(),
    )
    monkeypatch.setattr(
        "qqcc_bot.commands.load_runtime_qqcc_config",
        AsyncMock(return_value=normalize_qqcc_config(None)),
    )
    permission = SimpleNamespace(
        check_access=AsyncMock(return_value=None),
        ensure_user=AsyncMock(return_value=False),
    )
    monkeypatch.setattr("qqcc_bot.commands.permission_service", permission)

    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(
            id=123,
            username="tester",
            full_name="Tester",
            language_code="zh",
        ),
        message=SimpleNamespace(reply_text=reply_text),
    )
    context = SimpleNamespace(
        args=[],
        lang="zh",
        t=lambda key: f"translated:{key}",
        bot=object(),
        user_data={},
    )

    await qqcc_main.start(update, context)

    reply_text.assert_awaited_once()
    kwargs = reply_text.await_args.kwargs
    assert getattr(kwargs["reply_markup"], "inline_keyboard", None) is None
    assert _keyboard_texts(kwargs["reply_markup"]) == [
        ["💃 快速脱衣"],
        ["🖼️ 懒人P图", "AI动图"],
        ["前往主bot"],
    ]


@pytest.mark.asyncio
async def test_qqcc_quick_image_old_button_is_blocked(monkeypatch):
    reply_text = AsyncMock()
    monkeypatch.setattr(quick_image_fsm, "robust_reply_text", reply_text)
    monkeypatch.setattr(
        quick_image_fsm,
        "load_runtime_qqcc_config",
        AsyncMock(
            return_value=normalize_qqcc_config(
                {"photo_buttons": {"random_faceswap": False}}
            )
        ),
    )

    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        callback_query=None,
        message=SimpleNamespace(text="🎭 随机换脸"),
        edited_message=None,
    )
    context = SimpleNamespace(
        bot_data={"bot_client_type": "bot:qqcc"},
        user_data={},
        lang="zh",
        t=lambda key, **_kwargs: {"qqcc.feature_disabled": "功能暂未开放"}.get(
            key, key
        ),
    )

    result = await quick_image_fsm.start_quick_image(update, context)

    assert result == -1
    reply_text.assert_awaited_once()
    assert reply_text.await_args.args[1] == "功能暂未开放"


@pytest.mark.asyncio
async def test_qqcc_video_settings_buttons_are_filtered(monkeypatch):
    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=7), False)),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "get_user_group",
        AsyncMock(return_value="金丹期"),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "get_user_identity",
        AsyncMock(return_value="核心弟子"),
    )
    config = normalize_qqcc_config(
        {
            "video_settings": {
                "resolutions": {"512p": True, "720p": False, "1024p": True},
                "durations": {"5s": True, "8s": False, "10s": True},
            }
        }
    )
    context = SimpleNamespace(
        lang="zh",
        t=lambda key, **_kwargs: "灵石" if key == "app.credits" else key,
    )

    markup = await quick_video_fsm._build_quick_video_settings_markup(
        context=context,
        user_id=123,
        resolution="512p",
        duration="5s",
        qqcc_config=config,
    )
    callbacks = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
    ]

    assert "set_res_512p" in callbacks
    assert "set_res_720p" not in callbacks
    assert "set_res_1024p" in callbacks
    assert "set_dur_5s" in callbacks
    assert "set_dur_8s" not in callbacks
    assert "set_dur_10s" in callbacks


@pytest.mark.asyncio
async def test_qqcc_video_prompt_override_does_not_affect_main_bot(monkeypatch):
    captured = []

    monkeypatch.setattr(
        quick_video_fsm,
        "load_runtime_qqcc_config",
        AsyncMock(
            return_value=normalize_qqcc_config(
                {"prompts": {"perfect_video_insert": "qqcc override"}}
            )
        ),
    )
    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=7), False)),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "get_user_group",
        AsyncMock(return_value="金丹期"),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "get_user_identity",
        AsyncMock(return_value="核心弟子"),
    )
    monkeypatch.setattr(
        quick_video_fsm.permission_service,
        "check_quota",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(quick_video_fsm, "robust_edit_text", AsyncMock())

    def fake_process_video_task_template(**kwargs):
        captured.append(kwargs)
        return "queued"

    monkeypatch.setattr(
        quick_video_fsm,
        "process_video_task_template",
        fake_process_video_task_template,
    )
    monkeypatch.setattr(
        quick_video_fsm,
        "create_background_task",
        lambda _context, task: task,
    )

    def make_update_and_context(bot_data):
        query = SimpleNamespace(
            from_user=SimpleNamespace(id=123, username="tester"),
            data="qvid_start_generation",
            answer=AsyncMock(),
            message=SimpleNamespace(chat_id=456, message_id=77),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(
                id=123,
                username="tester",
                full_name="Tester",
            ),
            effective_chat=SimpleNamespace(id=456),
        )
        context = SimpleNamespace(
            bot_data=bot_data,
            user_data={
                "quick_video_data": {
                    "mode": MODE_PERFECT_VIDEO_INSERT,
                    "resolution": "512p",
                    "duration": "5s",
                    "image_path": "/tmp/input.png",
                }
            },
            lang="zh",
            t=lambda key, **_kwargs: key,
        )
        return update, context

    update, context = make_update_and_context({"bot_client_type": "bot:qqcc"})
    await quick_video_fsm.start_generation(update, context)

    update, context = make_update_and_context({})
    await quick_video_fsm.start_generation(update, context)

    assert captured[0]["prompt_override"] == "qqcc override"
    assert captured[1]["prompt_override"] is None


@pytest.mark.asyncio
async def test_qqcc_main_bot_menu_route_replies_with_url_button(monkeypatch):
    _clear_main_bot_link_env(monkeypatch)
    monkeypatch.setenv("QQCC_MAIN_BOT_URL", "https://t.me/main_bot")

    reply_text = AsyncMock()
    message = SimpleNamespace(reply_text=reply_text)
    update = SimpleNamespace(
        effective_message=message,
        message=None,
        edited_message=None,
    )
    context = SimpleNamespace(
        lang="zh",
        t=lambda key: f"translated:{key}",
    )

    await prompt_handlers.handle_open_main_bot(update, context)

    reply_text.assert_awaited_once()
    kwargs = reply_text.await_args.kwargs
    assert kwargs["text"] == "translated:system.open_main_bot_hint"
    button = kwargs["reply_markup"].inline_keyboard[0][0]
    assert button.text == "前往主bot"
    assert button.url == "https://t.me/main_bot"
