from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services import telegram_affiliate_service


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_query_affiliate_available_balance_for_telegram_user_uses_internal_user_id(
    monkeypatch,
):
    session = SimpleNamespace()
    query_mock = AsyncMock(return_value=Decimal("1.2500"))

    monkeypatch.setattr(
        telegram_affiliate_service,
        "resolve_internal_user_id_for_telegram",
        AsyncMock(return_value=42),
    )
    monkeypatch.setattr(
        telegram_affiliate_service, "AsyncSessionLocal", lambda: _SessionContext(session)
    )
    monkeypatch.setattr(
        telegram_affiliate_service,
        "query_affiliate_available_balance",
        query_mock,
    )

    balance = await telegram_affiliate_service.query_affiliate_available_balance_for_telegram_user(
        telegram_user_id=123,
        username="dao",
    )

    query_mock.assert_awaited_once_with(session, 42)
    assert balance == Decimal("1.2500")


@pytest.mark.asyncio
async def test_redeem_affiliate_credits_for_telegram_user_wraps_session_call(monkeypatch):
    session = SimpleNamespace()
    redeem_mock = AsyncMock(return_value=SimpleNamespace(current_credits=99))

    monkeypatch.setattr(
        telegram_affiliate_service,
        "resolve_internal_user_id_for_telegram",
        AsyncMock(return_value=42),
    )
    monkeypatch.setattr(
        telegram_affiliate_service, "AsyncSessionLocal", lambda: _SessionContext(session)
    )
    monkeypatch.setattr(
        telegram_affiliate_service,
        "redeem_affiliate_balance_to_credits",
        redeem_mock,
    )

    result = await telegram_affiliate_service.redeem_affiliate_credits_for_telegram_user(
        telegram_user_id=123,
        amount_usdt=Decimal("2.5000"),
        idempotency_key="k1",
    )

    redeem_mock.assert_awaited_once_with(
        session,
        user_id=42,
        amount_usdt=Decimal("2.5000"),
        idempotency_key="k1",
    )
    assert result.current_credits == 99
