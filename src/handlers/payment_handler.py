from telegram import Update
from telegram.ext import ContextTypes
import logging
from src.database.models import User, UserLog
from src.database.core import AsyncSessionLocal
from sqlalchemy import select
from src.handlers.utils import with_db_logging_context
from contextvars import ContextVar
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
    from src.database.models import MembershipPlan
    import math
    
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
            new_identity = plan.identity_name
            
            # 查找用户
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            
            if not user:
                logger.error(f"User {user_id} not found during payment")
                return
                
            from datetime import datetime, timedelta
            now = datetime.utcnow()
            
            # 残值折算与过期时间计算
            new_expire_at = user.identity_expire_at
            converted_days = 0
            
            if new_expire_at and new_expire_at > now:
                if user.current_identity == plan.identity_name:
                    # 同套餐续费
                    new_expire_at += timedelta(days=plan.duration_days)
                else:
                    # 跨套餐折算
                    old_plan_res = await session.execute(
                        select(MembershipPlan).where(MembershipPlan.identity_name == user.current_identity)
                    )
                    old_plan = old_plan_res.scalar_one_or_none()
                    
                    # 使用 reward_credits 作为通用等价物进行残值折算，因为 Stars 和 TON 的计价单位不同
                    if old_plan and old_plan.reward_credits > 0 and plan.duration_days > 0 and plan.reward_credits > 0:
                        remaining_days = (new_expire_at - now).total_seconds() / 86400.0
                        
                        # 老套餐日均价值 (以灵石为锚定物)
                        old_daily_value = old_plan.reward_credits / old_plan.duration_days
                        # 剩余总价值 (灵石)
                        residual_value = remaining_days * old_daily_value
                        
                        # 新套餐日均价值 (以灵石为锚定物)
                        new_daily_value = plan.reward_credits / plan.duration_days
                        
                        # 折算新套餐天数
                        converted_days = math.ceil(residual_value / new_daily_value)
                        new_expire_at = now + timedelta(days=plan.duration_days + converted_days)
                    else:
                        new_expire_at = now + timedelta(days=plan.duration_days)
            else:
                new_expire_at = now + timedelta(days=plan.duration_days)
                
            # 更新用户信息
            user.credits += added_credits
            user.current_identity = new_identity
            user.identity_expire_at = new_expire_at
            user.is_first_charge = False
                
            # 记录订单
            from src.database.models import Order
            telegram_charge_id = successful_payment.telegram_payment_charge_id
            
            # Check if order already exists (prevent double processing)
            existing_order = await session.execute(select(Order).where(Order.tx_hash == telegram_charge_id))
            if existing_order.scalar_one_or_none():
                logger.warning(f"Order already processed for charge_id: {telegram_charge_id}")
                return
                
            new_order = Order(
                order_id=payload[:64], # Truncate to avoid StringDataRightTruncationError
                telegram_id=user_id,
                plan_id=plan_id,
                original_price=successful_payment.total_amount, # In stars
                final_price=successful_payment.total_amount,
                status="SUCCESS",
                tx_hash=telegram_charge_id[:100] # Truncate to avoid StringDataRightTruncationError
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
                f"👑 **当前身份**：`{new_identity}`\n"
            )
            if converted_days > 0:
                success_msg += f"⚖️ **老套餐残值已折算**：`{converted_days}` 天新套餐时长\n"
                
            success_msg += (
                f"⏳ **身份到期时间**：`{new_expire_at.strftime('%Y-%m-%d %H:%M:%S')}` (UTC)\n\n"
                f"祝您仙途坦荡，早日登峰造极！"
            )
            await message.reply_text(success_msg, parse_mode="Markdown")
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Error processing payment for user {user_id}: {e}")
            await message.reply_text("❌ 发货异常，请联系管理员核实订单。")
