import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal

import aiohttp
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert

from src.database.core import AsyncSessionLocal
from src.database.models import MembershipPlan, Order, User, UserLog
from src.core.affiliate_core import (
    calculate_and_set_commission_for_paid_order,
    invalidate_invitation_recharge_cache,
    record_affiliate_commission_transaction,
)
from src.services.affiliate_redeem_service import is_membership_settlement_v2_enabled
from src.services.membership_settlement_service import (
    MembershipSettlementAuditSource,
    settle_membership_plan_in_session,
)
from src.services.order_v2_service import build_order_public_lookup_stmt
from config import TELEGRAM_API_BASE_URL

logger = logging.getLogger("payment_fulfillment")
RMB_AMOUNT_QUANT = Decimal("0.01")
PaymentChannel = Literal["RMB", "TON", "XTR"]
PaidUnit = Literal["rmb", "nanoton", "stars"]
FulfillmentStatus = Literal["success", "amount_mismatch", "noop"]


@dataclass(frozen=True)
class PaymentFulfillmentResult:
    status: FulfillmentStatus
    user_id: int | None = None
    notify_chat_id: int | None = None
    plan_name: str | None = None
    order_id: str | None = None
    tx_hash: str | None = None
    credits_granted: int = 0
    converted_days: int = 0
    final_identity: str | None = None
    final_expire_at: str | None = None
    is_pure_credit_plan: bool = False
    is_downgrade: bool = False
    applied_snapshot: dict[str, Any] | None = None


@dataclass(frozen=True)
class PaymentFulfillmentCommand:
    channel: PaymentChannel
    order_lookup: str | None
    external_tx_id: str
    paid_amount: Decimal | str | int
    paid_unit: PaidUnit
    source: str
    affiliate_source: str
    audit_source: str
    now: datetime | None = None
    legacy_order_id: str | None = None
    legacy_internal_user_id: int | None = None
    legacy_display_user_id: int | None = None
    legacy_plan_id: int | None = None
    legacy_original_price: Decimal | str | int | None = None
    notify: Callable[[PaymentFulfillmentResult], Awaitable[None]] | None = None


@dataclass(frozen=True)
class PaymentFulfillmentDependencies:
    session_factory: Callable[[], Any]
    is_settlement_v2_enabled: Callable[[], bool]
    settle_membership_plan_in_session_func: Callable[..., Awaitable[dict]]
    calculate_commission_func: Callable[..., Awaitable[Any]]
    record_affiliate_transaction_func: Callable[..., Awaitable[bool]]
    invalidate_invitation_cache_func: Callable[[int], Awaitable[None]]
    warning_func: Callable[..., None] = logger.warning


@dataclass(frozen=True)
class _PaymentResolution:
    command: PaymentFulfillmentCommand
    order: Any | None
    plan: Any | None
    user: Any | None
    early_result: PaymentFulfillmentResult | None = None


def build_default_payment_fulfillment_dependencies() -> PaymentFulfillmentDependencies:
    return PaymentFulfillmentDependencies(
        session_factory=AsyncSessionLocal,
        is_settlement_v2_enabled=is_membership_settlement_v2_enabled,
        settle_membership_plan_in_session_func=settle_membership_plan_in_session,
        calculate_commission_func=calculate_and_set_commission_for_paid_order,
        record_affiliate_transaction_func=record_affiliate_commission_transaction,
        invalidate_invitation_cache_func=invalidate_invitation_recharge_cache,
        warning_func=logger.warning,
    )


def _normalize_rmb_amount(amount: Decimal | str | int) -> Decimal:
    return Decimal(str(amount)).quantize(RMB_AMOUNT_QUANT, rounding=ROUND_HALF_UP)


def _truncate_tx_hash(tx_hash: str) -> str:
    return str(tx_hash)[:100]


async def _load_rmb_order(session, out_trade_no: str):
    order_res = await session.execute(
        build_order_public_lookup_stmt(out_trade_no, for_update=True)
    )
    return order_res.scalar_one_or_none()


async def _load_membership_plan(session, plan_id: int):
    plan_res = await session.execute(
        select(MembershipPlan).where(MembershipPlan.id == plan_id)
    )
    return plan_res.scalar_one_or_none()


async def _load_locked_user(session, internal_user_id: int):
    user_res = await session.execute(
        select(User).where(User.id == internal_user_id).with_for_update()
    )
    return user_res.scalar_one_or_none()


def _paid_amount_as_decimal(command: PaymentFulfillmentCommand) -> Decimal:
    if command.paid_unit == "nanoton":
        from src.constants import TON_TO_NANOTON

        return Decimal(str(command.paid_amount)) / Decimal(str(TON_TO_NANOTON))
    return Decimal(str(command.paid_amount))


def _amount_matches(command: PaymentFulfillmentCommand, *, order, plan) -> bool:
    if command.channel == "RMB":
        return _normalize_rmb_amount(order.final_price) == _normalize_rmb_amount(
            command.paid_amount
        )
    if command.channel == "XTR":
        return int(command.paid_amount) == int(getattr(plan, "price_stars", 0))

    from src.constants import TON_SLIPPAGE_NANOTON, TON_TO_NANOTON

    expected_min_nanotons = (
        int(plan.price_ton * Decimal(str(TON_TO_NANOTON))) - TON_SLIPPAGE_NANOTON
    )
    return int(command.paid_amount) >= max(expected_min_nanotons, 0)


def _mark_order(
    order,
    *,
    command: PaymentFulfillmentCommand,
    status: Literal["SUCCESS", "FAILED"],
    paid_at: datetime,
) -> None:
    order.payment_channel = command.channel
    order.status = status
    order.tx_hash = _truncate_tx_hash(command.external_tx_id)
    if command.channel == "TON":
        order.final_price = _paid_amount_as_decimal(command)
    order.paid_at = paid_at
    if status != "SUCCESS":
        order.paid_at = None


async def _record_order_affiliate_ledger(
    session,
    order,
    *,
    command: PaymentFulfillmentCommand,
    dependencies: PaymentFulfillmentDependencies,
):
    referral = await dependencies.calculate_commission_func(session, order)
    if not referral or Decimal(str(order.commission_usdt or 0)) <= 0:
        return referral

    inserted = await dependencies.record_affiliate_transaction_func(
        session,
        order,
        referral,
        source=command.affiliate_source,
    )
    if not inserted:
        dependencies.warning_func(
            "affiliate ledger insert skipped for %s order_id=%s order_pk=%s tx_hash=%s",
            command.channel,
            order.order_id,
            order.id,
            order.tx_hash,
        )
    return referral


async def _settle_order_membership(
    *,
    session,
    user,
    plan,
    order,
    command: PaymentFulfillmentCommand,
    dependencies: PaymentFulfillmentDependencies,
    now: datetime,
) -> dict:
    if dependencies.is_settlement_v2_enabled():
        return await dependencies.settle_membership_plan_in_session_func(
            locked_user=user,
            plan=plan,
            audit_source=MembershipSettlementAuditSource(
                source=command.audit_source,
                source_channel=command.channel,
                source_order_id=str(order.order_id),
                source_tx_hash=_truncate_tx_hash(command.external_tx_id),
            ),
            session=session,
            now=now,
            grant_reward_credits=True,
        )

    from src.core.billing_core import calculate_identity_conversion

    final_identity, new_expire_at = calculate_identity_conversion(
        current_identity=user.current_identity,
        current_expire_at=user.identity_expire_at,
        new_identity=plan.identity_name,
        duration_days=plan.duration_days,
    )
    user.credits += plan.reward_credits
    user.current_identity = final_identity
    user.identity_expire_at = new_expire_at
    if command.channel in {"TON", "XTR"}:
        import json

        reason = (
            f"Telegram Stars 购买: {plan.name}"
            if command.channel == "XTR"
            else f"TON 购买: {plan.name}"
        )
        session.add(
            UserLog(
                user_id=user.id,
                username=user.username,
                operation_type="recharge",
                credit_change=int(plan.reward_credits or 0),
                current_balance=user.credits,
                extra_info=json.dumps(
                    {
                        "reason": reason,
                        "via": command.channel,
                        "order_id": str(order.order_id),
                        "plan_id": plan.id,
                        "tx_hash": _truncate_tx_hash(command.external_tx_id),
                    },
                    ensure_ascii=False,
                ),
            )
        )
    return {
        "credits_granted": int(plan.reward_credits or 0),
        "converted_days": 0,
        "final_identity": final_identity,
        "final_expire_at": new_expire_at.isoformat() if new_expire_at else None,
        "current_credits": int(user.credits or 0),
        "settlement_reason": "LEGACY_FALLBACK",
        "is_pure_credit_plan": int(plan.duration_days or 0) == 0,
        "kept_current_identity": final_identity == user.current_identity,
        "is_downgrade": False,
    }


async def _load_existing_order(session, command: PaymentFulfillmentCommand):
    if not command.order_lookup:
        return None
    return (
        await session.execute(
            build_order_public_lookup_stmt(command.order_lookup, for_update=True)
        )
    ).scalar_one_or_none()


async def _load_legacy_user(session, command: PaymentFulfillmentCommand):
    if command.legacy_internal_user_id is None:
        return None
    user_res = await session.execute(
        select(User)
        .where(
            or_(
                User.id == command.legacy_internal_user_id,
                User.telegram_id == command.legacy_internal_user_id,
            )
        )
        .with_for_update()
    )
    return user_res.scalar_one_or_none()


async def _build_legacy_order(session, command: PaymentFulfillmentCommand, *, plan):
    if command.legacy_order_id is None or command.legacy_plan_id is None:
        return None
    legacy_order_id = command.legacy_order_id[:64]

    inserted_order_id = (
        await session.execute(
            insert(Order)
            .values(
                order_id=legacy_order_id,
                internal_user_id=command.legacy_internal_user_id,
                plan_id=command.legacy_plan_id,
                original_price=(
                    command.legacy_original_price
                    if command.legacy_original_price is not None
                    else plan.price_ton
                ),
                final_price=_paid_amount_as_decimal(command),
                status="SUCCESS",
                tx_hash=_truncate_tx_hash(command.external_tx_id),
                payment_channel=command.channel,
                paid_at=command.now or datetime.now(),
            )
            .on_conflict_do_nothing(index_elements=["tx_hash"])
            .returning(Order.id)
        )
    ).scalar_one_or_none()
    if inserted_order_id is None:
        return None
    order = await session.get(Order, inserted_order_id)
    if order is None:
        raise RuntimeError(
            "failed to reload inserted order for tx_hash: "
            f"{_truncate_tx_hash(command.external_tx_id)}"
        )
    if order.tx_hash != _truncate_tx_hash(command.external_tx_id):
        raise RuntimeError(
            "inserted order tx_hash mismatch for tx_hash: "
            f"{_truncate_tx_hash(command.external_tx_id)}"
        )
    return order


def _result_from_snapshot(
    *,
    status: FulfillmentStatus,
    user,
    plan=None,
    order=None,
    command: PaymentFulfillmentCommand,
    applied_snapshot: dict[str, Any] | None = None,
) -> PaymentFulfillmentResult:
    snapshot = applied_snapshot or {}
    return PaymentFulfillmentResult(
        status=status,
        user_id=getattr(user, "id", None),
        notify_chat_id=getattr(user, "telegram_id", None)
        or command.legacy_display_user_id
        or getattr(user, "id", None),
        plan_name=str(getattr(plan, "name", "")) if plan is not None else None,
        order_id=str(getattr(order, "order_id", "")) if order is not None else None,
        tx_hash=_truncate_tx_hash(command.external_tx_id),
        credits_granted=int(snapshot.get("credits_granted", 0)),
        converted_days=int(snapshot.get("converted_days", 0)),
        final_identity=str(
            snapshot.get("final_identity", getattr(user, "current_identity", ""))
        )
        if user is not None
        else None,
        final_expire_at=snapshot.get("final_expire_at"),
        is_pure_credit_plan=bool(snapshot.get("is_pure_credit_plan", False)),
        is_downgrade=bool(snapshot.get("is_downgrade", False)),
        applied_snapshot=snapshot,
    )


async def _resolve_existing_order_target(
    *,
    session,
    command: PaymentFulfillmentCommand,
    order,
) -> _PaymentResolution:
    if order.status == "SUCCESS":
        logger.info(
            "Order %s is already SUCCESS. Idempotent return.",
            command.order_lookup or order.order_id,
        )
        return _PaymentResolution(
            command=command,
            order=order,
            plan=None,
            user=None,
            early_result=_result_from_snapshot(
                status="noop",
                user=None,
                order=order,
                command=command,
            ),
        )

    if command.channel == "XTR":
        user = await _load_locked_user(session, order.internal_user_id)
        if not user:
            logger.error("User not found: %s", order.internal_user_id)
            return _PaymentResolution(
                command=command,
                order=order,
                plan=None,
                user=None,
                early_result=_result_from_snapshot(
                    status="noop",
                    user=None,
                    order=order,
                    command=command,
                ),
            )
        plan = await _load_membership_plan(session, order.plan_id)
        if not plan:
            logger.error("Plan not found: %s", order.plan_id)
            return _PaymentResolution(
                command=command,
                order=order,
                plan=None,
                user=user,
                early_result=_result_from_snapshot(
                    status="noop",
                    user=user,
                    order=order,
                    command=command,
                ),
            )
        return _PaymentResolution(command=command, order=order, plan=plan, user=user)

    plan = await _load_membership_plan(session, order.plan_id)
    if not plan:
        logger.error("Plan not found: %s", order.plan_id)
        return _PaymentResolution(
            command=command,
            order=order,
            plan=None,
            user=None,
            early_result=_result_from_snapshot(
                status="noop",
                user=None,
                order=order,
                command=command,
            ),
        )
    user = await _load_locked_user(session, order.internal_user_id)
    if not user:
        logger.error("User not found: %s", order.internal_user_id)
        return _PaymentResolution(
            command=command,
            order=order,
            plan=plan,
            user=None,
            early_result=_result_from_snapshot(
                status="noop",
                user=None,
                plan=plan,
                order=order,
                command=command,
            ),
        )
    return _PaymentResolution(command=command, order=order, plan=plan, user=user)


async def _dedupe_ton_legacy_order_id(
    *,
    session,
    command: PaymentFulfillmentCommand,
) -> PaymentFulfillmentCommand:
    if command.channel != "TON" or not command.legacy_order_id:
        return command
    existing_order = await session.execute(
        select(Order).where(Order.order_id == command.legacy_order_id[:64])
    )
    if not existing_order.scalar_one_or_none():
        return command
    return replace(
        command,
        legacy_order_id=(
            f"{command.legacy_order_id[:64]}_"
            f"{_truncate_tx_hash(command.external_tx_id)[:8]}"
        ),
    )


async def _resolve_legacy_payment_target(
    *,
    session,
    command: PaymentFulfillmentCommand,
) -> _PaymentResolution:
    if command.legacy_plan_id is None:
        logger.error("Order not found: %s", command.order_lookup)
        return _PaymentResolution(
            command=command,
            order=None,
            plan=None,
            user=None,
            early_result=_result_from_snapshot(
                status="noop",
                user=None,
                command=command,
            ),
        )

    command = await _dedupe_ton_legacy_order_id(session=session, command=command)
    plan = await _load_membership_plan(session, command.legacy_plan_id)
    if not plan:
        logger.error("Plan not found: %s", command.legacy_plan_id)
        return _PaymentResolution(
            command=command,
            order=None,
            plan=None,
            user=None,
            early_result=_result_from_snapshot(
                status="noop",
                user=None,
                command=command,
            ),
        )

    user = await _load_legacy_user(session, command)
    if not user:
        logger.error(
            "User not found during %s legacy payment: %s",
            command.channel,
            command.legacy_internal_user_id,
        )
        return _PaymentResolution(
            command=command,
            order=None,
            plan=plan,
            user=None,
            early_result=_result_from_snapshot(
                status="noop",
                user=None,
                plan=plan,
                command=command,
            ),
        )

    if getattr(user, "id", None) is not None:
        command = replace(command, legacy_internal_user_id=int(user.id))
    return _PaymentResolution(command=command, order=None, plan=plan, user=user)


async def _resolve_payment_target(
    *,
    session,
    command: PaymentFulfillmentCommand,
) -> _PaymentResolution:
    order = await _load_existing_order(session, command)
    if order is not None:
        return await _resolve_existing_order_target(
            session=session,
            command=command,
            order=order,
        )
    return await _resolve_legacy_payment_target(session=session, command=command)


async def _amount_mismatch_result_if_needed(
    *,
    session,
    resolution: _PaymentResolution,
    now: datetime,
) -> PaymentFulfillmentResult | None:
    command = resolution.command
    if _amount_matches(command, order=resolution.order, plan=resolution.plan):
        return None

    logger.error(
        "Amount mismatch for %s payment %s: paid %s",
        command.channel,
        command.order_lookup or command.legacy_order_id,
        command.paid_amount,
    )
    order = resolution.order
    if command.channel == "TON":
        if order is None:
            order = await _build_legacy_order(session, command, plan=resolution.plan)
        if order is not None:
            _mark_order(
                order,
                command=command,
                status="FAILED",
                paid_at=now,
            )
            await session.commit()
    return _result_from_snapshot(
        status="amount_mismatch",
        user=resolution.user,
        plan=resolution.plan,
        order=order,
        command=command,
    )


async def _materialize_success_order(
    *,
    session,
    resolution: _PaymentResolution,
    now: datetime,
) -> _PaymentResolution:
    order = resolution.order
    command = resolution.command
    if order is None:
        order = await _build_legacy_order(session, command, plan=resolution.plan)
        if order is None:
            logger.info(
                "Transaction %s already processed.",
                _truncate_tx_hash(command.external_tx_id),
            )
            return replace(
                resolution,
                early_result=_result_from_snapshot(
                    status="noop",
                    user=resolution.user,
                    plan=resolution.plan,
                    command=command,
                ),
            )
        return replace(resolution, order=order)

    _mark_order(
        order,
        command=command,
        status="SUCCESS",
        paid_at=now,
    )
    return resolution


async def _apply_successful_payment_effects(
    *,
    session,
    resolution: _PaymentResolution,
    dependencies: PaymentFulfillmentDependencies,
    now: datetime,
) -> tuple[Any | None, dict[str, Any]]:
    await session.flush()
    referral = await _record_order_affiliate_ledger(
        session,
        resolution.order,
        command=resolution.command,
        dependencies=dependencies,
    )
    applied_snapshot = await _settle_order_membership(
        session=session,
        user=resolution.user,
        plan=resolution.plan,
        order=resolution.order,
        command=resolution.command,
        dependencies=dependencies,
        now=now,
    )
    return referral, applied_snapshot


async def _run_post_commit_payment_side_effects(
    *,
    command: PaymentFulfillmentCommand,
    dependencies: PaymentFulfillmentDependencies,
    referral,
    result: PaymentFulfillmentResult,
) -> None:
    if referral:
        await dependencies.invalidate_invitation_cache_func(referral.inviter_id)
    if command.notify:
        await command.notify(result)


async def fulfill_payment_command(
    command: PaymentFulfillmentCommand,
    *,
    dependencies: PaymentFulfillmentDependencies | None = None,
) -> PaymentFulfillmentResult:
    dependencies = dependencies or build_default_payment_fulfillment_dependencies()
    now = command.now or datetime.now()
    command = replace(command, now=now)

    async with dependencies.session_factory() as session:
        try:
            resolution = await _resolve_payment_target(
                session=session,
                command=command,
            )
            if resolution.early_result is not None:
                return resolution.early_result

            mismatch_result = await _amount_mismatch_result_if_needed(
                session=session,
                resolution=resolution,
                now=now,
            )
            if mismatch_result is not None:
                return mismatch_result

            resolution = await _materialize_success_order(
                session=session,
                resolution=resolution,
                now=now,
            )
            if resolution.early_result is not None:
                return resolution.early_result

            referral, applied_snapshot = await _apply_successful_payment_effects(
                session=session,
                resolution=resolution,
                dependencies=dependencies,
                now=now,
            )
            await session.commit()

            result = _result_from_snapshot(
                status="success",
                user=resolution.user,
                plan=resolution.plan,
                order=resolution.order,
                command=resolution.command,
                applied_snapshot=applied_snapshot,
            )
            await _run_post_commit_payment_side_effects(
                command=resolution.command,
                dependencies=dependencies,
                referral=referral,
                result=result,
            )
            logger.info(
                "%s order %s fulfilled for user %s",
                resolution.command.channel,
                resolution.command.order_lookup or resolution.command.legacy_order_id,
                resolution.user.id,
            )
            return result
        except Exception:
            await session.rollback()
            logger.exception(
                "Failed to fulfill %s payment %s",
                command.channel,
                command.order_lookup or command.legacy_order_id,
            )
            raise


def _build_rmb_payment_success_message(*, plan, user, applied_snapshot: dict) -> str:
    credits_granted = int(applied_snapshot.get("credits_granted", 0))
    converted_days = int(applied_snapshot.get("converted_days", 0))
    final_identity = str(applied_snapshot.get("final_identity", user.current_identity))
    final_expire_at = applied_snapshot.get("final_expire_at")
    is_pure_credit = bool(applied_snapshot.get("is_pure_credit_plan", False))
    is_downgrade = bool(applied_snapshot.get("is_downgrade", False))
    success_msg = (
        f"🎉 <b>支付成功！</b>\n\n"
        f"感谢您的赞助，您已成功购买 <b>{plan.name}</b>。\n"
        f"💎 <b>获得永久灵石</b>：<code>{credits_granted}</code>\n"
    )
    if is_pure_credit or is_downgrade:
        success_msg += f"👑 <b>当前身份保持为</b>：<code>{final_identity}</code>\n"
        if converted_days > 0:
            success_msg += (
                f"⚖️ <b>新套餐价值已折算</b>：<code>{converted_days}</code> "
                "天当前高级身份时长\n"
            )
    else:
        success_msg += f"👑 <b>当前身份晋升为</b>：<code>{final_identity}</code>\n"
        if converted_days > 0:
            success_msg += (
                f"⚖️ <b>老套餐残值已折算</b>：<code>{converted_days}</code> 天新套餐时长\n"
            )

    if final_expire_at:
        success_msg += f"⏳ <b>身份到期时间</b>：<code>{final_expire_at}</code>\n\n"
    return success_msg + "祝您仙途坦荡，早日登峰造极！"


async def _notify_rmb_payment_success(*, user, plan, applied_snapshot: dict) -> None:
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        return

    telegram_api_url = f"{TELEGRAM_API_BASE_URL}/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": user.telegram_id or user.id,
        "text": _build_rmb_payment_success_message(
            plan=plan,
            user=user,
            applied_snapshot=applied_snapshot,
        ),
        "parse_mode": "HTML",
    }
    try:
        async with aiohttp.ClientSession() as http_session:
            async with http_session.post(
                telegram_api_url,
                json=payload,
                timeout=10,
            ) as resp:
                if resp.status != 200:
                    response_text = await resp.text()
                    logger.error(
                        "Failed to send TG message, status: %s, response: %s",
                        resp.status,
                        response_text,
                    )
    except Exception as e:
        logger.error(f"Exception while sending TG message: {e}")


async def fulfill_order(
    out_trade_no: str, external_trade_no: str, paid_amount: Decimal | str | int
) -> bool:
    """
    统一发货逻辑，目前供 RMB 支付网关回调使用。
    """
    try:
        result = await fulfill_payment_command(
            PaymentFulfillmentCommand(
                channel="RMB",
                order_lookup=out_trade_no,
                external_tx_id=external_trade_no,
                paid_amount=paid_amount,
                paid_unit="rmb",
                source="rmb_payment_callback",
                affiliate_source="rmb_payment_callback",
                audit_source="rmb_payment_callback",
            )
        )
        if result.status == "success":
            await _notify_rmb_payment_success_from_result(result)
            return True
        return result.status == "noop"
    except Exception:
        logger.exception("Failed to fulfill order %s", out_trade_no)
        return False


async def _notify_rmb_payment_success_from_result(
    result: PaymentFulfillmentResult,
) -> None:
    if result.applied_snapshot is None or result.plan_name is None:
        return
    user = type(
        "PaymentNotificationUser",
        (),
        {
            "id": result.user_id,
            "telegram_id": result.notify_chat_id,
            "current_identity": result.final_identity,
        },
    )()
    plan = type("PaymentNotificationPlan", (), {"name": result.plan_name})()
    await _notify_rmb_payment_success(
        user=user,
        plan=plan,
        applied_snapshot=result.applied_snapshot,
    )
