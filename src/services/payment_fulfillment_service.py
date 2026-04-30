import logging
import math
import os
from datetime import datetime, timedelta

import aiohttp
from sqlalchemy import select

from src.database.core import AsyncSessionLocal
from src.database.models import MembershipPlan, Order, User
from src.services.log_service import LogService
from config import TELEGRAM_API_BASE_URL

logger = logging.getLogger("payment_fulfillment")

async def fulfill_order(out_trade_no: str, external_trade_no: str, paid_amount: float) -> bool:
    """
    统一发货逻辑，目前供 RMB 支付网关回调使用。
    """
    async with AsyncSessionLocal() as session:
        try:
            # 1. 查找订单
            order_res = await session.execute(select(Order).where(Order.order_id == out_trade_no))
            order = order_res.scalar_one_or_none()
            if not order:
                logger.error(f"Order not found: {out_trade_no}")
                return False
                
            if order.status == "SUCCESS":
                logger.info(f"Order {out_trade_no} is already SUCCESS. Idempotent return.")
                return True # 幂等返回
                
            # 金额校验
            if float(order.final_price) != float(paid_amount):
                logger.error(f"Amount mismatch for {out_trade_no}: paid {paid_amount}, expected {order.final_price}")
                return False

            # 2. 查找套餐
            plan_res = await session.execute(select(MembershipPlan).where(MembershipPlan.id == order.plan_id))
            plan = plan_res.scalar_one_or_none()
            if not plan:
                logger.error(f"Plan not found: {order.plan_id}")
                return False
                
            # 3. 查找用户
            user_res = await session.execute(select(User).where(User.id == order.telegram_id))
            user = user_res.scalar_one_or_none()
            if not user:
                logger.error(f"User not found: {order.telegram_id}")
                return False
                
            # 4. 计算身份和时长折算逻辑
            now = datetime.now()
            new_expire_at = user.identity_expire_at
            converted_days = 0
            final_identity = plan.identity_name
            is_downgrade = False
            is_pure_credit = (plan.duration_days == 0)
            
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
                final_identity = user.current_identity
                new_expire_at = user.identity_expire_at
            elif new_expire_at and new_expire_at > now:
                if user.current_identity == plan.identity_name:
                    # 同套餐续费
                    new_expire_at += timedelta(days=plan.duration_days)
                elif new_priority > current_priority:
                    # 升级：用原套餐剩余的价值折算成新套餐的天数，再加上新套餐本身的天数
                    remaining_days = (new_expire_at - now).total_seconds() / 86400.0
                    old_ratio = identity_ratio.get(user.current_identity, 1)
                    new_ratio = identity_ratio.get(plan.identity_name, 1)
                    # converted_days 代表从老套餐折算过来的额外天数
                    converted_days = math.ceil((remaining_days * old_ratio) / new_ratio)
                    # 新的到期时间 = 现在 + 折算天数 + 新买的天数
                    new_expire_at = now + timedelta(days=plan.duration_days + converted_days)
                else:
                    # 降级或同级
                    is_downgrade = True
                    final_identity = user.current_identity
                    old_ratio = identity_ratio.get(user.current_identity, 1)
                    new_ratio = identity_ratio.get(plan.identity_name, 1)
                    # converted_days 代表新买的低级套餐折算成老套餐增加的天数
                    extra_days = math.ceil((plan.duration_days * new_ratio) / old_ratio)
                    converted_days = extra_days
                    new_expire_at += timedelta(days=extra_days)
            else:
                # 过期或首次充值
                new_expire_at = now + timedelta(days=plan.duration_days)
                
            # 5. 更新订单、用户与插入日志
            order.status = "SUCCESS"
            order.tx_hash = external_trade_no
            
            user.credits += plan.reward_credits
            user.current_identity = final_identity
            user.identity_expire_at = new_expire_at
            
            await session.commit()
            
            # 使用统一的 LogService 记录流水（自带重试机制，防止丢日志）
            await LogService.log_action(
                user_id=user.id,
                username=user.username,
                operation_type="recharge",
                credit_change=plan.reward_credits,
                current_balance=user.credits,
                extra_info={
                    "order_id": out_trade_no,
                    "plan": plan.name,
                    "external_trade_no": external_trade_no,
                    "via": "rmb_payment",
                    "converted_days": converted_days,
                    "identity": final_identity
                }
            )
            
            logger.info(f"Order {out_trade_no} fulfilled for user {user.id}")
            
            # 6. 通知用户
            bot_token = os.getenv("BOT_TOKEN")
            if bot_token:
                success_msg = (
                    f"🎉 <b>支付成功！</b>\n\n"
                    f"感谢您的赞助，您已成功购买 <b>{plan.name}</b>。\n"
                    f"💎 <b>获得永久灵石</b>：<code>{plan.reward_credits}</code>\n"
                )
                if is_pure_credit or is_downgrade:
                    success_msg += f"👑 <b>当前身份保持为</b>：<code>{final_identity}</code>\n"
                    if converted_days > 0:
                        success_msg += f"⚖️ <b>新套餐价值已折算</b>：<code>{converted_days}</code> 天当前高级身份时长\n"
                else:
                    success_msg += f"👑 <b>当前身份晋升为</b>：<code>{final_identity}</code>\n"
                    if converted_days > 0:
                        success_msg += f"⚖️ <b>老套餐残值已折算</b>：<code>{converted_days}</code> 天新套餐时长\n"
                        
                if new_expire_at:
                    success_msg += f"⏳ <b>身份到期时间</b>：<code>{new_expire_at.strftime('%Y-%m-%d %H:%M:%S')}</code> (UTC)\n\n"
                success_msg += f"祝您仙途坦荡，早日登峰造极！"
                
                telegram_api_url = f"{TELEGRAM_API_BASE_URL}/bot{bot_token}/sendMessage"
                payload = {
                    "chat_id": user.telegram_id or user.id, # Fallback to id if telegram_id is empty (for old users)
                    "text": success_msg,
                    "parse_mode": "HTML"
                }
                try:
                    async with aiohttp.ClientSession() as http_session:
                        async with http_session.post(telegram_api_url, json=payload, timeout=10) as resp:
                            if resp.status != 200:
                                logger.error(f"Failed to send TG message, status: {resp.status}, response: {await resp.text()}")
                except Exception as e:
                    logger.error(f"Exception while sending TG message: {e}")
                    
            return True
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to fulfill order {out_trade_no}: {e}")
            return False
