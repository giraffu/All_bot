from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, TypeHandler

from qqcc_bot import keyboards, main as qqcc_main, prompt_handlers
from qqcc_bot import commands as qqcc_commands
from src.handlers import prompt_router


def _keyboard_texts(reply_markup):
    return [[getattr(button, "text", button) for button in row] for row in reply_markup.keyboard]


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
        ["🖼️ 懒人P图", "🎬 视频创作"],
        ["前往主bot"],
    ]


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


def test_qqcc_video_menu_contains_lazy_video_scenes():
    rows = _keyboard_texts(keyboards.get_qqcc_video_edit_keyboard("zh"))
    flat = [text for row in rows for text in row]

    assert "🛌 动图传教士" in flat
    assert "🎬 动图后入" in flat
    assert "🎬 口交黑人" in flat
    assert "🎬 脱衣吐舌" in flat
    assert "🎬 特写口交" in flat


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
        ["🖼️ 懒人P图", "🎬 视频创作"],
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
        ["🖼️ 懒人P图", "🎬 视频创作"],
        ["前往主bot"],
    ]


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
