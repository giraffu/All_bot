from __future__ import annotations

from decimal import Decimal

from src.database.core import AsyncSessionLocal
from src.services.affiliate_redeem_service import (
    query_affiliate_available_balance,
    redeem_affiliate_balance_to_credits,
    redeem_affiliate_balance_to_membership,
)
from src.services.affiliate_usdt_redeem_service import create_affiliate_usdt_redeem
from src.services.telegram_identity_service import resolve_internal_user_id_for_telegram


async def resolve_internal_user_id_for_telegram_user(
    *,
    telegram_user_id: int,
    username: str | None = None,
    full_name: str | None = None,
    language_code: str | None = None,
) -> int:
    return await resolve_internal_user_id_for_telegram(
        telegram_user_id,
        username,
        full_name,
        language_code,
    )


async def query_affiliate_available_balance_for_telegram_user(
    *,
    telegram_user_id: int,
    username: str | None = None,
    full_name: str | None = None,
    language_code: str | None = None,
) -> Decimal:
    internal_user_id = await resolve_internal_user_id_for_telegram_user(
        telegram_user_id=telegram_user_id,
        username=username,
        full_name=full_name,
        language_code=language_code,
    )
    async with AsyncSessionLocal() as session:
        return await query_affiliate_available_balance(session, internal_user_id)


async def redeem_affiliate_credits_for_telegram_user(
    *,
    telegram_user_id: int,
    amount_usdt: Decimal,
    idempotency_key: str,
    username: str | None = None,
    full_name: str | None = None,
    language_code: str | None = None,
):
    internal_user_id = await resolve_internal_user_id_for_telegram_user(
        telegram_user_id=telegram_user_id,
        username=username,
        full_name=full_name,
        language_code=language_code,
    )
    async with AsyncSessionLocal() as session:
        return await redeem_affiliate_balance_to_credits(
            session,
            user_id=internal_user_id,
            amount_usdt=amount_usdt,
            idempotency_key=idempotency_key,
        )


async def redeem_affiliate_membership_for_telegram_user(
    *,
    telegram_user_id: int,
    option_key: str,
    idempotency_key: str,
    username: str | None = None,
    full_name: str | None = None,
    language_code: str | None = None,
):
    internal_user_id = await resolve_internal_user_id_for_telegram_user(
        telegram_user_id=telegram_user_id,
        username=username,
        full_name=full_name,
        language_code=language_code,
    )
    async with AsyncSessionLocal() as session:
        return await redeem_affiliate_balance_to_membership(
            session,
            user_id=internal_user_id,
            option_key=option_key,
            idempotency_key=idempotency_key,
        )


async def request_affiliate_usdt_for_telegram_user(
    *,
    telegram_user_id: int,
    amount_usdt: Decimal,
    payout_address: str,
    idempotency_key: str,
    username: str | None = None,
    full_name: str | None = None,
    language_code: str | None = None,
):
    internal_user_id = await resolve_internal_user_id_for_telegram_user(
        telegram_user_id=telegram_user_id,
        username=username,
        full_name=full_name,
        language_code=language_code,
    )
    async with AsyncSessionLocal() as session:
        return await create_affiliate_usdt_redeem(
            session,
            user_id=internal_user_id,
            amount_usdt=amount_usdt,
            payout_address=payout_address,
            idempotency_key=idempotency_key,
        )
