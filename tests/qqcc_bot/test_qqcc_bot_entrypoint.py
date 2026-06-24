from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, TypeHandler

from qqcc_bot import keyboards, main as qqcc_main, prompt_handlers
from src.handlers import prompt_router


def _keyboard_texts(reply_markup):
    return [[getattr(button, "text", button) for button in row] for row in reply_markup.keyboard]


def test_qqcc_main_menu_only_contains_lazy_generation_entries():
    keyboard = _keyboard_texts(keyboards.get_qqcc_main_menu_keyboard("zh"))

    assert keyboard == [["🖼️ 懒人P图", "🎬 视频创作"]]


def test_qqcc_photo_menu_excludes_fast_face_swap():
    rows = _keyboard_texts(keyboards.get_qqcc_photo_edit_keyboard("zh"))
    flat = [text for row in rows for text in row]

    assert "💃 快速脱衣" in flat
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
    }


def test_qqcc_lazy_main_buttons_are_routable_without_main_bot_prompt_routes(monkeypatch):
    monkeypatch.setattr(prompt_router, "prompt_routes", {}, raising=False)

    prompt_router.build_global_menu_filter()

    assert prompt_router.GLOBAL_REVERSE_MAP["🖼️ 懒人P图"] == "menu.photo_edit"
    assert prompt_router.GLOBAL_REVERSE_MAP["🎬 视频创作"] == "menu.video_edit"


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
    assert _keyboard_texts(kwargs["reply_markup"]) == [["🖼️ 懒人P图", "🎬 视频创作"]]
