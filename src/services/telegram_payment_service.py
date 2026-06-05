from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select

from src.core.user_core import get_or_create_user_by_telegram
from src.database.core import AsyncSessionLocal
from src.database.models import MembershipPlan
from src.services.affiliate_redeem_service import is_membership_settlement_v2_enabled
from src.services.membership_settlement_service import (
    settle_membership_plan_in_session,
)
from src.services.payment_fulfillment_service import (
    PaymentFulfillmentCommand,
    PaymentFulfillmentDependencies,
    fulfill_payment_command,
)
from src.services.order_v2_service import build_order_public_lookup_stmt, parse_order_payload

logger = logging.getLogger("bot.payment")


@dataclass(frozen=True)
class TelegramStarsPaymentResult:
    status: Literal["success", "amount_mismatch", "noop"]
    user_id: int | None = None
    plan_name: str | None = None
    credits_granted: int = 0
    converted_days: int = 0
    final_identity: str | None = None
    final_expire_at: str | None = None
    is_pure_credit_plan: bool = False
    is_downgrade: bool = False


async def validate_stars_precheckout(
    *,
    payload: str,
    telegram_user_id: int,
    total_amount: int,
) -> bool:
    parsed_payload = parse_order_payload(payload)
    if parsed_payload.kind == "legacy":
        return True
    if parsed_payload.kind != "v2" or not parsed_payload.business_order_id:
        return False

    internal_user, _ = await get_or_create_user_by_telegram(telegram_user_id)
    async with AsyncSessionLocal() as session:
        order = (
            await session.execute(
                build_order_public_lookup_stmt(parsed_payload.business_order_id)
            )
        ).scalar_one_or_none()
        if (
            not order
            or order.internal_user_id != internal_user.id
            or order.status != "PENDING"
        ):
            return False

        plan = (
            await session.execute(
                select(MembershipPlan).where(MembershipPlan.id == order.plan_id)
            )
        ).scalar_one_or_none()
        return bool(plan and int(getattr(plan, "price_stars", 0)) == int(total_amount))


async def process_successful_stars_payment(
    *,
    payload: str,
    total_amount: int,
    telegram_payment_charge_id: str,
) -> TelegramStarsPaymentResult | None:
    parsed_payload = parse_order_payload(payload)
    if parsed_payload.kind == "unknown":
        return None
    legacy_internal_user_id = None
    legacy_display_user_id = None
    legacy_plan_id = None
    if parsed_payload.kind == "legacy":
        try:
            legacy_display_user_id = int(parsed_payload.telegram_user_id)
            legacy_plan_id = int(parsed_payload.plan_id)
        except (TypeError, ValueError):
            logger.error("Invalid payload format: %s", payload)
            return TelegramStarsPaymentResult(status="noop")
        legacy_internal_user_id = legacy_display_user_id

    from src.core import affiliate_core

    result = await fulfill_payment_command(
        PaymentFulfillmentCommand(
            channel="XTR",
            order_lookup=parsed_payload.business_order_id
            if parsed_payload.kind == "v2"
            else None,
            external_tx_id=telegram_payment_charge_id,
            paid_amount=total_amount,
            paid_unit="stars",
            source="telegram_stars_payment",
            affiliate_source="telegram_stars_payment",
            audit_source="telegram_stars_payment",
            legacy_order_id=payload[:64] if parsed_payload.kind == "legacy" else None,
            legacy_internal_user_id=legacy_internal_user_id,
            legacy_display_user_id=legacy_display_user_id,
            legacy_plan_id=legacy_plan_id,
            legacy_original_price=total_amount if parsed_payload.kind == "legacy" else None,
        ),
        dependencies=PaymentFulfillmentDependencies(
            session_factory=AsyncSessionLocal,
            is_settlement_v2_enabled=is_membership_settlement_v2_enabled,
            settle_membership_plan_in_session_func=settle_membership_plan_in_session,
            calculate_commission_func=affiliate_core.calculate_and_set_commission_for_paid_order,
            record_affiliate_transaction_func=affiliate_core.record_affiliate_commission_transaction,
            invalidate_invitation_cache_func=affiliate_core.invalidate_invitation_recharge_cache,
            warning_func=logger.warning,
        ),
    )

    if result.status == "success":
        logger.info(
            "Payment success processed for user %s, plan: %s",
            result.user_id,
            result.plan_name,
        )
    return TelegramStarsPaymentResult(
        status=result.status,
        user_id=result.user_id,
        plan_name=result.plan_name,
        credits_granted=result.credits_granted,
        converted_days=result.converted_days,
        final_identity=result.final_identity,
        final_expire_at=result.final_expire_at,
        is_pure_credit_plan=result.is_pure_credit_plan,
        is_downgrade=result.is_downgrade,
    )
