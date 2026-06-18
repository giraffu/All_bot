from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from paid_group_guard_bot.config import PaidGroupBotSettings
from paid_group_guard_bot.eligibility import PaidGroupEligibilityDecision
from paid_group_guard_bot.handlers import handle_chat_join_request


def _settings(**overrides):
    values = {
        "token": "token",
        "target_chat_id": -100123,
        "decline_unqualified": False,
        "dry_run": False,
    }
    values.update(overrides)
    return PaidGroupBotSettings(**values)


def _update(chat_id=-100123, user_id=777):
    return SimpleNamespace(
        chat_join_request=SimpleNamespace(
            chat=SimpleNamespace(id=chat_id),
            from_user=SimpleNamespace(id=user_id, username="paid_user"),
        )
    )


def _context():
    return SimpleNamespace(
        bot=SimpleNamespace(
            approve_chat_join_request=AsyncMock(),
            decline_chat_join_request=AsyncMock(),
        )
    )


@pytest.mark.asyncio
async def test_handle_chat_join_request_approves_eligible_user():
    context = _context()
    checker = AsyncMock(
        return_value=PaidGroupEligibilityDecision(
            eligible=True,
            reason="matched_successful_paid_or_gift_order",
            telegram_id=777,
            internal_user_id=9001,
            matched_order_id=3,
        )
    )

    await handle_chat_join_request(
        _update(),
        context,
        settings=_settings(),
        eligibility_checker=checker,
    )

    checker.assert_awaited_once_with(777)
    context.bot.approve_chat_join_request.assert_awaited_once_with(
        chat_id=-100123,
        user_id=777,
    )
    context.bot.decline_chat_join_request.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_chat_join_request_leaves_unqualified_pending_by_default():
    context = _context()
    checker = AsyncMock(
        return_value=PaidGroupEligibilityDecision(
            eligible=False,
            reason="no_successful_paid_or_gift_order",
            telegram_id=777,
            internal_user_id=9001,
        )
    )

    await handle_chat_join_request(
        _update(),
        context,
        settings=_settings(),
        eligibility_checker=checker,
    )

    context.bot.approve_chat_join_request.assert_not_awaited()
    context.bot.decline_chat_join_request.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_chat_join_request_can_decline_unqualified_user():
    context = _context()
    checker = AsyncMock(
        return_value=PaidGroupEligibilityDecision(
            eligible=False,
            reason="user_not_found",
            telegram_id=777,
        )
    )

    await handle_chat_join_request(
        _update(),
        context,
        settings=_settings(decline_unqualified=True),
        eligibility_checker=checker,
    )

    context.bot.approve_chat_join_request.assert_not_awaited()
    context.bot.decline_chat_join_request.assert_awaited_once_with(
        chat_id=-100123,
        user_id=777,
    )


@pytest.mark.asyncio
async def test_handle_chat_join_request_ignores_unexpected_group():
    context = _context()
    checker = AsyncMock()

    await handle_chat_join_request(
        _update(chat_id=-100999),
        context,
        settings=_settings(),
        eligibility_checker=checker,
    )

    checker.assert_not_awaited()
    context.bot.approve_chat_join_request.assert_not_awaited()
    context.bot.decline_chat_join_request.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_chat_join_request_dry_run_takes_no_action():
    context = _context()
    checker = AsyncMock(
        return_value=PaidGroupEligibilityDecision(
            eligible=True,
            reason="matched_successful_paid_or_gift_order",
            telegram_id=777,
            internal_user_id=9001,
            matched_order_id=3,
        )
    )

    await handle_chat_join_request(
        _update(),
        context,
        settings=_settings(dry_run=True),
        eligibility_checker=checker,
    )

    checker.assert_awaited_once_with(777)
    context.bot.approve_chat_join_request.assert_not_awaited()
    context.bot.decline_chat_join_request.assert_not_awaited()

