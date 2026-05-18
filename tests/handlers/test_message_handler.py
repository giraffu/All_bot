from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.handlers import message_handler


def _build_private_update_with_edited_message(text: str = "unknown text"):
    chat = SimpleNamespace(type="private", id=10001)
    edited_message = SimpleNamespace(
        text=text,
        chat=chat,
        chat_id=chat.id,
    )
    user = SimpleNamespace(
        id=20001,
        username="tester",
        full_name="Test User",
    )
    return SimpleNamespace(
        message=None,
        edited_message=edited_message,
        effective_user=user,
        effective_chat=chat,
    )


def _build_context():
    return SimpleNamespace(
        bot=SimpleNamespace(),
        lang="zh",
        user_data={},
        t=lambda key: key,
    )


@pytest.mark.asyncio
async def test_handle_prompt_uses_edited_message_for_private_fallback(monkeypatch):
    reply_mock = AsyncMock()

    monkeypatch.setattr(message_handler, "get_user_channel_status", AsyncMock(return_value=False))
    monkeypatch.setattr(
        message_handler.permission_service,
        "check_access",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(message_handler, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        "src.handlers.prompt_router.GLOBAL_REVERSE_MAP",
        {},
        raising=False,
    )
    monkeypatch.setattr(
        "src.i18n.keyboards.get_main_menu_keyboard",
        lambda _lang: "fake-keyboard",
    )

    update = _build_private_update_with_edited_message()
    context = _build_context()

    result = await message_handler.handle_prompt(update, context)

    assert result is None
    reply_mock.assert_awaited_once()
    call_args = reply_mock.await_args
    assert call_args.args[0] is update.edited_message
    assert "不认识的指令" in call_args.args[1]
    assert call_args.kwargs["reply_markup"] == "fake-keyboard"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "route_key", "keyboard_attr", "expected_text"),
    [
        ("主菜单", "menu.main_menu", "get_main_menu_keyboard", "已返回主菜单"),
        ("懒人P图", "menu.photo_edit", "get_photo_edit_keyboard", "system.photo_edit_hint"),
    ],
)
async def test_handle_prompt_route_uses_edited_message_reply_target(
    monkeypatch, text, route_key, keyboard_attr, expected_text
):
    reply_mock = AsyncMock()

    monkeypatch.setattr(
        message_handler, "get_user_channel_status", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        message_handler.permission_service,
        "check_access",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(message_handler, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        "src.handlers.prompt_router.GLOBAL_REVERSE_MAP",
        {text: route_key},
        raising=False,
    )
    monkeypatch.setattr(
        f"src.i18n.keyboards.{keyboard_attr}",
        lambda _lang: "fake-keyboard",
    )

    update = _build_private_update_with_edited_message(text=text)
    context = _build_context()

    result = await message_handler.handle_prompt(update, context)

    assert result is None
    reply_mock.assert_awaited_once()
    call_args = reply_mock.await_args
    assert call_args.args[0] is update.edited_message
    assert expected_text in call_args.args[1]
