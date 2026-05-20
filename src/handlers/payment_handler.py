import logging
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from telegram import Update
from telegram.ext import ContextTypes

from src.database.core import AsyncSessionLocal
from src.database.models import MembershipPlan, Order, User, UserLog
from src.handlers.utils import with_db_logging_context
from src.services.order_v2_service import (
    build_order_public_lookup_stmt,
    parse_order_payload,
)
from src.services.affiliate_redeem_service import is_membership_settlement_v2_enabled
from src.services.membership_settlement_service import (
    MembershipSettlementAuditSource,
    settle_membership_plan_in_session,
)
from src.utils import safe_answer_query

logger = logging.getLogger("bot.payment")


@with_db_logging_context
async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Answers the PreQecheckoutQuery"""
    query = update.pre_checkout_query
    parsed_payload = parse_order_payload(query.invoice_payload)
    if parsed_payload.kind == "v2" and parsed_payload.business_order_id:
        from src.core.user_core import get_or_create_user_by_telegram

        internal_user, _ = await get_or_create_user_by_telegram(query.from_user.id)
        async with AsyncSessionLocal() as session:
            order = (
                await session.execute(
                    build_order_public_lookup_stmt(parsed_payload.business_order_id)
                )
            ).scalar_one_or_none()
            if (
                order
                and order.telegram_id == internal_user.id
                and order.status == "PENDING"
            ):
                plan = (
                    await session.execute(
                        select(MembershipPlan).where(MembershipPlan.id == order.plan_id)
                    )
                ).scalar_one_or_none()
                if plan and int(getattr(plan, "price_stars", 0)) == int(query.total_amount):
                    await safe_answer_query(query, ok=True)
                    return
        await safe_answer_query(
            query, ok=False, error_message="无效的订单信息，请重试。"
        )
        return

    if parsed_payload.kind == "legacy":
        await safe_answer_query(query, ok=True)
        return

    await safe_answer_query(
        query, ok=False, error_message="无效的订单信息，请重试。"
    )


@with_db_logging_context
async def successful_payment_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """处理支付成功后的发货逻辑"""
    message = update.message
    successful_payment = message.successful_payment
    payload = successful_payment.invoice_payload

    logger.info(f"Received successful payment: {payload}")

    parsed_payload = parse_order_payload(payload)

    if parsed_payload.kind == "unknown":
        return

    async with AsyncSessionLocal() as session:
        try:
            user_id: int | None = None
            now = datetime.now()
            telegram_charge_id = successful_payment.telegram_payment_charge_id

            # Use truncated id for both checking and saving to prevent double processing bugs
            tx_hash_truncated = telegram_charge_id[:100]
            if parsed_payload.kind == "v2" and parsed_payload.business_order_id:
                new_order = (
                    await session.execute(
                        build_order_public_lookup_stmt(
                            parsed_payload.business_order_id, for_update=True
                        )
                    )
                ).scalar_one_or_none()
                if not new_order:
                    logger.error(
                        "Order not found for business_order_id=%s",
                        parsed_payload.business_order_id,
                    )
                    return
                if new_order.status == "SUCCESS":
                    logger.info(
                        "Stars order already SUCCESS for business_order_id=%s",
                        parsed_payload.business_order_id,
                    )
                    return
                user = (
                    await session.execute(
                        select(User).where(User.id == new_order.telegram_id).with_for_update()
                    )
                ).scalar_one_or_none()
                user_id = new_order.telegram_id
                if not user:
                    logger.error("User %s not found during stars v2 payment", new_order.telegram_id)
                    return
                plan = (
                    await session.execute(
                        select(MembershipPlan).where(MembershipPlan.id == new_order.plan_id)
                    )
                ).scalar_one_or_none()
                plan_id = new_order.plan_id
                if not plan:
                    logger.error("Unknown plan_id: %s", new_order.plan_id)
                    return
                if successful_payment.total_amount != getattr(plan, "price_stars", 0):
                    logger.error(
                        "Amount mismatch for business_order_id=%s: paid %s, expected %s",
                        parsed_payload.business_order_id,
                        successful_payment.total_amount,
                        getattr(plan, "price_stars", 0),
                    )
                    await message.reply_text("❌ 支付金额与套餐价格不匹配，请联系管理员。")
                    return
                new_order.status = "SUCCESS"
                new_order.tx_hash = tx_hash_truncated
                new_order.paid_at = now
                await session.flush()
            else:
                try:
                    user_id = int(parsed_payload.telegram_user_id)
                    plan_id = int(parsed_payload.plan_id)
                except (TypeError, ValueError):
                    logger.error(f"Invalid payload format: {payload}")
                    return

                plan = (
                    await session.execute(
                        select(MembershipPlan).where(MembershipPlan.id == plan_id)
                    )
                ).scalar_one_or_none()
                if not plan:
                    logger.error(f"Unknown plan_id: {plan_id}")
                    return
                if successful_payment.total_amount != getattr(plan, "price_stars", 0):
                    logger.error(
                        f"Amount mismatch for plan {plan_id}: paid {successful_payment.total_amount}, expected {getattr(plan, 'price_stars', 0)}"
                    )
                    await message.reply_text("❌ 支付金额与套餐价格不匹配，请联系管理员。")
                    return
                from sqlalchemy import or_

                user = (
                    await session.execute(
                        select(User)
                        .where(or_(User.telegram_id == user_id, User.id == user_id))
                        .with_for_update()
                    )
                ).scalar_one_or_none()
                if not user:
                    logger.error(f"User {user_id} not found during payment")
                    return

                inserted_order_id = (
                    await session.execute(
                        insert(Order)
                        .values(
                            order_id=payload[:64],
                            telegram_id=user.id,
                            plan_id=plan_id,
                            original_price=successful_payment.total_amount,
                            final_price=successful_payment.total_amount,
                            status="SUCCESS",
                            tx_hash=tx_hash_truncated,
                            payment_channel="XTR",
                            paid_at=now,
                        )
                        .on_conflict_do_nothing(index_elements=["tx_hash"])
                        .returning(Order.id)
                    )
                ).scalar_one_or_none()
                if inserted_order_id is None:
                    logger.warning(
                        f"Order already processed for charge_id: {telegram_charge_id}"
                    )
                    return
                new_order = await session.get(Order, inserted_order_id)
                if new_order is None:
                    raise RuntimeError(
                        f"failed to reload inserted Stars order for charge_id: {telegram_charge_id}"
                    )
                await session.flush()
                if new_order.tx_hash != tx_hash_truncated:
                    raise RuntimeError(
                        f"inserted Stars order tx_hash mismatch for charge_id: {telegram_charge_id}"
                    )

            from src.core.affiliate_core import (
                calculate_and_set_commission_for_paid_order,
                invalidate_invitation_recharge_cache,
                record_affiliate_commission_transaction,
            )

            referral = await calculate_and_set_commission_for_paid_order(
                session, new_order
            )
            if referral and Decimal(str(new_order.commission_usdt or 0)) > 0:
                inserted = await record_affiliate_commission_transaction(
                    session,
                    new_order,
                    referral,
                    source="telegram_stars_payment",
                )
                if not inserted:
                    logger.warning(
                        "affiliate ledger insert skipped for Stars order_id=%s order_pk=%s tx_hash=%s",
                        new_order.order_id,
                        new_order.id,
                        new_order.tx_hash,
                    )
            if is_membership_settlement_v2_enabled():
                applied_snapshot = await settle_membership_plan_in_session(
                    locked_user=user,
                    plan=plan,
                    audit_source=MembershipSettlementAuditSource(
                        source="telegram_stars_payment",
                        source_channel="XTR",
                        source_order_id=str(new_order.order_id),
                        source_tx_hash=tx_hash_truncated,
                    ),
                    session=session,
                    now=now,
                    grant_reward_credits=True,
                )
            else:
                from src.core.billing_core import calculate_identity_conversion
                import json

                final_identity, new_expire_at = calculate_identity_conversion(
                    current_identity=user.current_identity,
                    current_expire_at=user.identity_expire_at,
                    new_identity=plan.identity_name,
                    duration_days=plan.duration_days,
                )
                user.credits += plan.reward_credits
                user.current_identity = final_identity
                user.identity_expire_at = new_expire_at
                applied_snapshot = {
                    "credits_granted": int(plan.reward_credits or 0),
                    "converted_days": 0,
                    "final_identity": final_identity,
                    "final_expire_at": new_expire_at.isoformat()
                    if new_expire_at
                    else None,
                    "is_pure_credit_plan": int(plan.duration_days or 0) == 0,
                    "is_downgrade": False,
                }
                log = UserLog(
                    user_id=user.id,
                    username=user.username,
                    operation_type="recharge",
                    credit_change=int(plan.reward_credits or 0),
                    current_balance=user.credits,
                    extra_info=json.dumps(
                        {
                            "reason": f"Telegram Stars 购买: {plan.name}",
                            "via": "telegram_stars",
                            "plan_id": plan_id,
                        },
                        ensure_ascii=False,
                    ),
                )
                session.add(log)
            await session.commit()
            if referral:
                await invalidate_invitation_recharge_cache(referral.inviter_id)

            logger.info(
                f"Payment success processed for user {user_id}, plan: {plan.name}"
            )

            # 发送成功通知
            credits_granted = int(applied_snapshot.get("credits_granted", 0))
            converted_days = int(applied_snapshot.get("converted_days", 0))
            final_identity = str(applied_snapshot.get("final_identity", user.current_identity))
            final_expire_at = applied_snapshot.get("final_expire_at")
            is_pure_credit = bool(applied_snapshot.get("is_pure_credit_plan", False))
            is_downgrade = bool(applied_snapshot.get("is_downgrade", False))
            success_msg = (
                f"🎉 **支付成功！**\n\n"
                f"感谢您的赞助，您已成功购买 **{plan.name}**。\n"
                f"💰 **获得永久灵石**：`{credits_granted}`\n"
            )
            if is_pure_credit:
                success_msg += f"👑 **当前身份保持为**：`{final_identity}`\n"
            elif is_downgrade:
                success_msg += f"👑 **当前身份保持为**：`{final_identity}`\n"
                if converted_days > 0:
                    success_msg += f"⚖️ **新套餐价值已折算**：`{converted_days}` 天当前高级身份时长\n"
            else:
                success_msg += f"👑 **当前身份晋升为**：`{final_identity}`\n"
                if converted_days > 0:
                    success_msg += (
                        f"⚖️ **老套餐残值已折算**：`{converted_days}` 天新套餐时长\n"
                    )

            if final_expire_at:
                success_msg += f"⏳ **身份到期时间**：`{final_expire_at}`\n\n"
            success_msg += "祝您仙途坦荡，早日登峰造极！"
            await message.reply_text(success_msg, parse_mode="Markdown")

        except Exception as e:
            await session.rollback()
            logger.error(f"Error processing payment for user {user_id}: {e}")
            await message.reply_text("❌ 发货异常，请联系管理员核实订单。")
