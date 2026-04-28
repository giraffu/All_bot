import logging

from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

from src.database.core import AsyncSessionLocal
from src.database.models import User, UserLog
from src.handlers.utils import with_db_logging_context
from src.utils import safe_answer_query

logger = logging.getLogger("bot.payment")

@with_db_logging_context
async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Answers the PreQecheckoutQuery"""
    query = update.pre_checkout_query
    # 检查 payload
    if query.invoice_payload.startswith("ORDER:"):
        await safe_answer_query(query, ok=True)
    else:
        await safe_answer_query(query, ok=False, error_message="无效的订单信息，请重试。")

@with_db_logging_context
async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理支付成功后的发货逻辑"""
    import math

    from src.database.models import MembershipPlan
    
    message = update.message
    successful_payment = message.successful_payment
    payload = successful_payment.invoice_payload
    
    logger.info(f"Received successful payment: {payload}")
    
    if not payload.startswith("ORDER:"):
        return
        
    parts = payload.split(":")
    if len(parts) < 3:
        return
        
    try:
        user_id = int(parts[1])
        plan_id = int(parts[2])
    except ValueError:
        logger.error(f"Invalid payload format: {payload}")
        return
        
    async with AsyncSessionLocal() as session:
        try:
            # 查找套餐
            plan_res = await session.execute(select(MembershipPlan).where(MembershipPlan.id == plan_id))
            plan = plan_res.scalar_one_or_none()
            
            if not plan:
                logger.error(f"Unknown plan_id: {plan_id}")
                return
                
            # 校验金额
            if successful_payment.total_amount != getattr(plan, 'price_stars', 0):
                logger.error(f"Amount mismatch for plan {plan_id}: paid {successful_payment.total_amount}, expected {getattr(plan, 'price_stars', 0)}")
                await message.reply_text("❌ 支付金额与套餐价格不匹配，请联系管理员。")
                return

            added_credits = plan.reward_credits
            
            # 查找用户
            from sqlalchemy import or_
            result = await session.execute(select(User).where(or_(User.telegram_id == user_id, User.id == user_id)))
            user = result.scalar_one_or_none()
            
            if not user:
                logger.error(f"User {user_id} not found during payment")
                return
                
            from datetime import datetime, timedelta
            now = datetime.utcnow()
            
            # 身份和有效期逻辑
            new_expire_at = user.identity_expire_at
            converted_days = 0
            final_identity = plan.identity_name
            is_downgrade = False
            is_pure_credit = (plan.duration_days == 0)
            
            # 定义身份优先级和折算比例
            identity_priority = {
                "外门弟子": 0,
                "内门弟子": 1,
                "核心弟子": 2,
                "真传弟子": 3
            }
            identity_ratio = {
                "外门弟子": 1,
                "内门弟子": 2,
                "核心弟子": 5,
                "真传弟子": 10
            }
            
            current_priority = identity_priority.get(user.current_identity, 0)
            new_priority = identity_priority.get(plan.identity_name, 0)
            
            if is_pure_credit:
                # 直购模式：完全不改变原有的身份和到期时间
                final_identity = user.current_identity
                new_expire_at = user.identity_expire_at
            elif new_expire_at and new_expire_at > now:
                if user.current_identity == plan.identity_name:
                    # 同套餐续费
                    new_expire_at += timedelta(days=plan.duration_days)
                elif new_priority > current_priority:
                    # 升级：将旧身份残值折算为新身份天数
                    remaining_days = (new_expire_at - now).total_seconds() / 86400.0
                    old_ratio = identity_ratio.get(user.current_identity, 1)
                    new_ratio = identity_ratio.get(plan.identity_name, 1)
                    
                    # 残值 = 剩余天数 * 旧比例，折算天数 = 残值 / 新比例
                    converted_days = math.ceil((remaining_days * old_ratio) / new_ratio)
                    new_expire_at = now + timedelta(days=plan.duration_days + converted_days)
                else:
                    # 降级或同级：保留高等级身份，将新购买的低等级套餐价值折算为高等级身份的天数
                    is_downgrade = True
                    final_identity = user.current_identity # 保持原身份
                    
                    old_ratio = identity_ratio.get(user.current_identity, 1)
                    new_ratio = identity_ratio.get(plan.identity_name, 1)
                    
                    # 新购价值 = 新套餐天数 * 新比例，折算天数 = 新购价值 / 旧比例
                    extra_days = math.ceil((plan.duration_days * new_ratio) / old_ratio)
                    converted_days = extra_days
                    new_expire_at += timedelta(days=extra_days)
            else:
                # 身份已过期或首次充值
                new_expire_at = now + timedelta(days=plan.duration_days)
                
            # 更新用户信息
            user.credits += added_credits
            user.current_identity = final_identity
            user.identity_expire_at = new_expire_at
                
            # 记录订单
            from src.database.models import Order
            telegram_charge_id = successful_payment.telegram_payment_charge_id
            
            # Use truncated id for both checking and saving to prevent double processing bugs
            tx_hash_truncated = telegram_charge_id[:100]
            
            # Check if order already exists (prevent double processing)
            existing_order = await session.execute(select(Order).where(Order.tx_hash == tx_hash_truncated))
            if existing_order.scalar_one_or_none():
                logger.warning(f"Order already processed for charge_id: {telegram_charge_id}")
                return
                
            new_order = Order(
                order_id=payload[:64], # Truncate to avoid StringDataRightTruncationError
                telegram_id=user.id, # Must be internal_id
                plan_id=plan_id,
                original_price=successful_payment.total_amount, # In stars
                final_price=successful_payment.total_amount,
                status="SUCCESS",
                tx_hash=tx_hash_truncated # Truncate to avoid StringDataRightTruncationError
            )
            session.add(new_order)
                
            # 记录流水 (遵循开发者红线)
            import json
            log = UserLog(
                user_id=user.id,
                username=user.username,
                operation_type="recharge",
                credit_change=added_credits,
                current_balance=user.credits,
                extra_info=json.dumps({"reason": f"Telegram Stars 购买: {plan.name}", "via": "telegram_stars", "plan_id": plan_id}, ensure_ascii=False)
            )
            session.add(log)
            await session.commit()
            
            logger.info(f"Payment success processed for user {user_id}, plan: {plan.name}")
            
            # 发送成功通知
            success_msg = (
                f"🎉 **支付成功！**\n\n"
                f"感谢您的赞助，您已成功购买 **{plan.name}**。\n"
                f"💰 **获得永久灵石**：`{added_credits}`\n"
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
                    success_msg += f"⚖️ **老套餐残值已折算**：`{converted_days}` 天新套餐时长\n"
                
            if new_expire_at:
                success_msg += f"⏳ **身份到期时间**：`{new_expire_at.strftime('%Y-%m-%d %H:%M:%S')}` (UTC)\n\n"
            success_msg += f"祝您仙途坦荡，早日登峰造极！"
            await message.reply_text(success_msg, parse_mode="Markdown")
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Error processing payment for user {user_id}: {e}")
            await message.reply_text("❌ 发货异常，请联系管理员核实订单。")
