from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.handlers import message_handler_common


def test_build_private_prompt_fallback_supports_bilingual_copy():
    assert "不认识的指令" in message_handler_common.build_private_prompt_fallback("zh")
    assert "Unrecognized command" in message_handler_common.build_private_prompt_fallback(
        "en"
    )


def test_build_private_prompt_fallback_payload_returns_text_and_keyboard(monkeypatch):
    monkeypatch.setattr(
        "src.i18n.keyboards.get_main_menu_keyboard",
        lambda lang: f"keyboard:{lang}",
    )

    text, keyboard = message_handler_common.build_private_prompt_fallback_payload("zh")

    assert "不认识的指令" in text
    assert keyboard == "keyboard:zh"


def test_extract_prompt_message_text_prefers_edited_message_and_strips_text():
    edited_message = SimpleNamespace(text="  主菜单  ", chat=SimpleNamespace(type="private"))
    update = SimpleNamespace(
        effective_message=None,
        message=None,
        edited_message=edited_message,
    )

    message, text = message_handler_common.extract_prompt_message_text(update)

    assert message is edited_message
    assert text == "主菜单"


def test_resolve_prompt_route_handler_returns_registered_handler():
    handler = object()

    assert (
        message_handler_common.resolve_prompt_route_handler(
            "主菜单",
            {"menu.main_menu": handler},
            {"主菜单": "menu.main_menu"},
        )
        is handler
    )
    assert (
        message_handler_common.resolve_prompt_route_handler(
            "未知指令",
            {"menu.main_menu": handler},
            {"主菜单": "menu.main_menu"},
        )
        is None
    )


@pytest.mark.asyncio
async def test_dispatch_prompt_route_calls_matched_handler():
    route_handler = AsyncMock(return_value="handled")
    update = SimpleNamespace()
    context = SimpleNamespace()

    matched, result = await message_handler_common.dispatch_prompt_route(
        update,
        context,
        "主菜单",
        prompt_routes={"menu.main_menu": route_handler},
        reverse_map={"主菜单": "menu.main_menu"},
    )

    assert matched is True
    assert result == "handled"
    route_handler.assert_awaited_once_with(update, context, "主菜单")


@pytest.mark.asyncio
async def test_reply_private_prompt_fallback_replies_only_in_private_chat(monkeypatch):
    reply_text = AsyncMock()
    monkeypatch.setattr(
        message_handler_common,
        "build_private_prompt_fallback_payload",
        lambda lang: ("fallback", f"keyboard:{lang}"),
    )

    private_message = SimpleNamespace(chat=SimpleNamespace(type="private"))
    group_message = SimpleNamespace(chat=SimpleNamespace(type="group"))

    await message_handler_common.reply_private_prompt_fallback(
        private_message,
        lang="zh",
        reply_text=reply_text,
    )
    await message_handler_common.reply_private_prompt_fallback(
        group_message,
        lang="zh",
        reply_text=reply_text,
    )

    reply_text.assert_awaited_once_with(
        private_message,
        "fallback",
        reply_markup="keyboard:zh",
    )


def test_format_invitation_stats_uses_balance_semantics():
    text = message_handler_common.format_invitation_stats(
        {
            "recharged_invitees_count": 3,
            "total_recharge_count": 4,
            "total_ton": 1.23,
            "total_rmb": 45.67,
            "total_stars": 89,
            "total_commission_usdt": 9.99,
            "spent_commission_usdt": 1.11,
            "available_balance_usdt": 8.88,
        }
    )

    assert "首笔邀请充值" in text
    assert "完成 `4` 笔首充" in text
    assert "历史累计返佣：`USDT 9.99`" in text
    assert "已兑换返佣：`USDT 1.11`" in text
    assert "当前可兑换余额：`USDT 8.88`" in text


def test_format_invitation_stats_supports_english_locale():
    text = message_handler_common.format_invitation_stats(
        {
            "recharged_invitees_count": 3,
            "total_recharge_count": 4,
            "total_ton": 1.23,
            "total_rmb": 45.67,
            "total_stars": 89,
            "total_commission_usdt": 9.99,
            "spent_commission_usdt": 1.11,
            "available_balance_usdt": 8.88,
        },
        lang="en",
    )

    assert "Invitation stats" in text
    assert "First recharge invitees" in text
    assert "completed `4` first top-ups" in text
    assert "Historical commission: `USDT 9.99`" in text
    assert "Available balance: `USDT 8.88`" in text


@pytest.mark.asyncio
async def test_ensure_user_access_reward_triggers_inviter_notification(monkeypatch):
    user = SimpleNamespace(id=123, username="dao", full_name="道友")
    context = SimpleNamespace(bot="bot")
    reward_coro = object()
    background_task_mock = MagicMock()

    monkeypatch.setattr(
        message_handler_common,
        "get_user_channel_status",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        message_handler_common.permission_service,
        "check_access",
        AsyncMock(return_value=456),
    )
    monkeypatch.setattr(
        message_handler_common,
        "create_background_task",
        background_task_mock,
    )
    monkeypatch.setattr(
        message_handler_common,
        "notify_inviter_reward",
        lambda bot, inviter_id, full_name: reward_coro,
    )

    inviter_id = await message_handler_common.ensure_user_access_reward(context, user)

    assert inviter_id == 456
    background_task_mock.assert_called_once_with(context, reward_coro)
