from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.handlers import message_handler_common


def test_build_private_prompt_fallback_supports_bilingual_copy():
    assert "不认识的指令" in message_handler_common.build_private_prompt_fallback("zh")
    assert "Unrecognized command" in message_handler_common.build_private_prompt_fallback(
        "en"
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

    assert "历史累计返佣：*$ 9.99 USDT*" in text
    assert "已兑换返佣：*$ 1.11 USDT*" in text
    assert "当前可兑换余额：*$ 8.88 USDT*" in text


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
