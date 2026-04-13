from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes
from config import ENABLE_PUBLIC_SHARE, MINIO_TEMPLATE_BUCKET, REQUIRED_CHANNEL_ID, WEBAPP_URL
from src.utils import (
    robust_send_message, robust_edit_text, load_prompts, 
    robust_edit_reply_markup, robust_edit_caption, safe_answer_query,
    is_maintenance_mode, create_background_task
)
from src.handlers.utils import with_db_logging_context
from src.services.task_service import TaskService
from src.services.permission_service import permission_service
from src.services.storage import storage
from src.constants import (
    MODE_UNDRESS, MODE_MASTURBATION, 
    MODE_NAME_MAP, MODE_RANDOM_FACESWAP,
    FORBIDDEN_WORDS, TASK_COSTS,
    get_video_settings_keyboard, RESOLUTION_COST, 
    RESOLUTION_PERMISSIONS, DURATION_PERMISSIONS, 
    DEFAULT_RESOLUTION, DEFAULT_DURATION, DURATION_MULTIPLIER,
    MODE_FACE_VIDEO_STEP1
)
import os
import random
import asyncio
import logging

logger = logging.getLogger(__name__)

@with_db_logging_context
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle callback queries from inline keyboards.
    """
    query = update.callback_query
    
    data = query.data
    
    # Do not answer immediately for public_share_request so we can show alert if needed
    if data != "public_share_request":
        await safe_answer_query(query) # Always answer to stop loading animation
    
    # Ensure user info is up to date
    await permission_service.ensure_user(update)

    if not ENABLE_PUBLIC_SHARE and data in ["public_share_request", "public_share", "public_share_cancel"]:
        await safe_answer_query(query, text="⚠️ 公开功能已关闭", show_alert=True)
        return
    
    if data == "public_share_request":
        # Check forbidden words
        msg_meta = context.bot_data.get(f"msg_meta_{query.message.message_id}", {})
        prompt = msg_meta.get("prompt", "")
        if prompt:
            prompt_lower = prompt.lower()
            for word in FORBIDDEN_WORDS:
                if word.lower() in prompt_lower:
                    await safe_answer_query(
                        query,
                        text=f"⚠️ 您的内容包含违禁词「{word}」，无法公开！",
                        show_alert=True
                    )
                    return
        
        await safe_answer_query(query) # Answer if no forbidden words

        # Show confirmation menu
        # Check if already in confirmation state
        if query.message.caption and "⚠️ 公开确认" in query.message.caption:
            return
        
        # Check if markup is already the confirmation markup
        # If no caption, we check the first button text
        if not query.message.caption and query.message.reply_markup:
            first_btn = query.message.reply_markup.inline_keyboard[0][0]
            if first_btn.callback_data == "public_share":
                return

        keyboard = [
            [
                InlineKeyboardButton("✅ 确认公开", callback_data="public_share"),
                InlineKeyboardButton("❌ 取消", callback_data="public_share_cancel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Explain what happens
        confirmation_text = (
            "⚠️ **公开确认**\n\n"
            "您确定要公开此内容吗？\n"
            "确认后，该内容将被转发到 **宗门公告栏**，供所有道友瞻仰。"
        )
        
        # We use robust_edit_reply_markup but also need to change text if possible
        # However, for images/videos, we can only edit the caption.
        if query.message.caption:
            # Check for rendered text (no **)
            if "⚠️ 公开确认" in query.message.caption:
                return # Already showing confirmation
                
            try:
                await robust_edit_caption(
                    query.message,
                    caption=f"{query.message.caption}\n\n{confirmation_text}",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            except Exception:
                # Fallback if editing caption fails
                await robust_edit_reply_markup(query.message, reply_markup=reply_markup)
        else:
            await robust_edit_reply_markup(query.message, reply_markup=reply_markup)
        return

    elif data == "public_share_cancel":
        # Check if already in cancelled state (original keyboard)
        # If the first button is "public_share_request", it's already in original state.
        if query.message.reply_markup:
            first_btn = query.message.reply_markup.inline_keyboard[0][0]
            if first_btn.callback_data == "public_share_request":
                return
        
        # Restore original caption (remove confirmation text)
        if query.message.caption:
            if "⚠️ 公开确认" not in query.message.caption:
                # Caption doesn't have confirmation, maybe already restored
                pass
            else:
                original_caption = query.message.caption.split("\n\n⚠️ 公开确认")[0].strip()
                try:
                    await robust_edit_caption(
                        query.message,
                        caption=original_caption,
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass

        # Restore original keyboard
        keyboard = [
            [
                InlineKeyboardButton("公开", callback_data="public_share_request")
            ],
            [
                InlineKeyboardButton("👍", callback_data="rate_like"),
                InlineKeyboardButton("👎", callback_data="rate_dislike")
            ]
        ]
        # Some modes might have "🔄 再来一张"
        msg_id = query.message.message_id
        meta = context.bot_data.get(f"msg_meta_{msg_id}")
        if meta and meta.get('mode_name') == MODE_NAME_MAP.get(MODE_RANDOM_FACESWAP):
            keyboard[0].append(InlineKeyboardButton("🔄 再来一张", callback_data="random_faceswap_again"))

        await robust_edit_reply_markup(query.message, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    elif data == "public_share":
        # Check if already shared
        if query.message.caption and "📢 **已同步至宗门公告**" in query.message.caption:
            return
        
        # Check if markup is already None
        if query.message.reply_markup is None:
            return

        # Forward to channel
        if not REQUIRED_CHANNEL_ID:
            await robust_send_message(context.bot, query.message.chat_id, "❌ 未加入宗门，无法转发。")
            return

        try:
            msg_id = query.message.message_id
            meta = context.bot_data.get(f"msg_meta_{msg_id}")
            
            # Extract clean caption (remove confirmation text if exists)
            # Use split without ** because Telegram rendered text doesn't have it
            original_caption = ""
            if query.message.caption:
                original_caption = query.message.caption.split("\n\n⚠️ 公开确认")[0].strip()
            
            # Reconstruct caption from meta if available, else use original_caption
            final_caption = original_caption
            if meta:
                mode_name = meta.get('mode_name', '未知模式')
                prompt = meta.get('prompt', '无提示词')
                final_caption = f"✨ 模式：{mode_name}\n📝 提示词：{prompt}"
            
            sent = False
            try:
                # Use copy_message with clean caption
                await context.bot.copy_message(
                    chat_id=REQUIRED_CHANNEL_ID,
                    from_chat_id=query.message.chat_id,
                    message_id=msg_id,
                    caption=final_caption,
                    parse_mode="Markdown"
                )
                sent = True
            except Exception:
                # Fallback to forward_message if copy fails, but we should try to edit it after?
                # No, better to just use forward_message as absolute last resort
                pass
            
            if not sent:
                # Last resort fallback
                await context.bot.forward_message(
                    chat_id=REQUIRED_CHANNEL_ID,
                    from_chat_id=query.message.chat_id,
                    message_id=query.message.message_id
                )
                sent = True
            
            if sent:
                if meta and "task_id" in meta:
                    task_id = meta["task_id"]
                    try:
                        from sqlalchemy import update
                        from src.database.core import AsyncSessionLocal
                        from src.database.models import History
                        async with AsyncSessionLocal() as session:
                            await session.execute(
                                update(History).where(History.task_id == task_id).values(is_public=True)
                            )
                            await session.commit()
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).error(f"Error updating is_public: {e}")

            # Feedback to user
            await safe_answer_query(query, text="✅ 已公开并转发至宗门公告栏！", show_alert=True)
            
            # Update the original message to remove buttons and show status
            try:
                await robust_edit_caption(
                    query.message,
                    caption=f"{original_caption}\n\n📢 **已同步至宗门公告**",
                    reply_markup=None,
                    parse_mode="Markdown"
                )
            except Exception:
                await robust_edit_reply_markup(query.message, reply_markup=None)
            
        except Exception as e:
            await robust_send_message(context.bot, query.message.chat_id, f"❌ 转发失败: {e}")
            
    elif data in ["rate_like", "rate_dislike"]:
        msg_id = query.message.message_id
        meta = context.bot_data.get(f"msg_meta_{msg_id}")
        if not meta or "task_id" not in meta:
            await safe_answer_query(query, text="❌ 无法找到对应任务记录", show_alert=True)
            return
            
        task_id = meta["task_id"]
        rating_value = 1 if data == "rate_like" else -1
        
        try:
            from sqlalchemy import update
            from src.database.core import AsyncSessionLocal
            from src.database.models import History
            
            async with AsyncSessionLocal() as session:
                await session.execute(
                    update(History).where(History.task_id == task_id).values(rating=rating_value)
                )
                await session.commit()
                
            # Update buttons to reflect choice
            keyboard = []
            for row in query.message.reply_markup.inline_keyboard:
                new_row = []
                for btn in row:
                    if btn.callback_data == "rate_like":
                        text = "✅ 已赞" if rating_value == 1 else "👍"
                        new_row.append(InlineKeyboardButton(text, callback_data="rate_like"))
                    elif btn.callback_data == "rate_dislike":
                        text = "✅ 已踩" if rating_value == -1 else "👎"
                        new_row.append(InlineKeyboardButton(text, callback_data="rate_dislike"))
                    else:
                        new_row.append(btn)
                keyboard.append(new_row)
                
            await robust_edit_reply_markup(query.message, reply_markup=InlineKeyboardMarkup(keyboard))
            
            await safe_answer_query(query, text="感谢您的评价，祝道友修为精进！", show_alert=False)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error updating rating: {e}")
            await safe_answer_query(query, text="❌ 评价失败，请稍后再试", show_alert=True)
    
    elif data == "random_faceswap_again":
        # Check maintenance mode for generation tasks
        if is_maintenance_mode():
            await robust_send_message(context.bot, query.message.chat_id, "⚠️ 服务器即将运维，暂停生成服务中")
            return

        # Check priority
        priority = await permission_service.calculate_user_priority(query.from_user.id)
        if priority <= 0:
            await robust_send_message(context.bot, query.message.chat_id, "⚠️ 道友，您的排队优先级已耗尽（或修为不足），今日已无法再凝聚灵力，请明日再来或提升修为！")
            return

        # "再来一张" (Random FaceSwap Again)
        face_image_path = context.user_data.get('last_face_image')
        if not face_image_path:
            await robust_send_message(context.bot, query.message.chat_id, "❌ 找不到原始人脸图片，请重新发送。")
            return
        
        # Permission check
        cost = TASK_COSTS.get(MODE_RANDOM_FACESWAP, 1)
        if not await permission_service.check_quota(update, context, cost=cost):
            return

        chat_id = query.message.chat_id
        user_id = query.from_user.id
        username = query.from_user.username or query.from_user.full_name
        prompts_config = load_prompts()

        try:
            template_files = storage.list_objects("quick_face/", bucket=MINIO_TEMPLATE_BUCKET)
            template_files = [f for f in template_files if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
            
            if not template_files:
                await robust_send_message(context.bot, chat_id, "❌ 系统错误：未找到身体模板。")
                return

            random_template = random.choice(template_files)
            template_path = f"template:{random_template}"
            
            prompt = prompts_config.get("face_swap", "face swap")
            swapped_images = [template_path, face_image_path] 
            
            reply_markup = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🔄 再来一张", callback_data="random_faceswap_again")
                ],
                [
                    InlineKeyboardButton("👍", callback_data="rate_like"),
                    InlineKeyboardButton("👎", callback_data="rate_dislike")
                ]
            ])
            
            # Use create_background_task to prevent blocking the callback handler and avoid GC
            create_background_task(
                context,
                TaskService.process_generation_task(
                    context, chat_id, user_id, username, 
                    prompt, swapped_images, task_type="face_swap",
                    reply_markup=reply_markup,
                    cleanup=False # Do not cleanup because we might need the face image again
                )
            )
        except Exception as e:
            await robust_send_message(context.bot, chat_id, f"❌ 任务执行出错：{str(e)}")
    
    elif data == "recharge_stars_menu":
        from src.database.core import AsyncSessionLocal
        from src.database.models import MembershipPlan
        from sqlalchemy import select
        
        keyboard = []
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(MembershipPlan).where(MembershipPlan.is_active == True, MembershipPlan.duration_days > 0).order_by(MembershipPlan.price_stars.asc()))
            plans = result.scalars().all()
            for plan in plans:
                if getattr(plan, 'price_stars', 0) > 0:
                    keyboard.append([InlineKeyboardButton(f"⭐️ {plan.price_stars} - {plan.name} ({plan.identity_name})", callback_data=f"buy_star_plan_{plan.id}")])
                    
        keyboard.append([InlineKeyboardButton("🔙 返回支付方式", callback_data="recharge_back")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.message.edit_reply_markup(reply_markup=reply_markup)
        except Exception:
            pass

    elif data == "recharge_stars_credit_menu":
        from src.database.core import AsyncSessionLocal
        from src.database.models import MembershipPlan
        from sqlalchemy import select
        
        keyboard = []
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(MembershipPlan).where(MembershipPlan.is_active == True, MembershipPlan.duration_days == 0).order_by(MembershipPlan.price_stars.asc()))
            plans = result.scalars().all()
            for plan in plans:
                if getattr(plan, 'price_stars', 0) > 0:
                    keyboard.append([InlineKeyboardButton(f"⭐️ {plan.price_stars} Star 直购 {plan.reward_credits} 灵石", callback_data=f"buy_star_plan_{plan.id}")])
                    
        keyboard.append([InlineKeyboardButton("🔙 返回支付方式", callback_data="recharge_back")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.message.edit_reply_markup(reply_markup=reply_markup)
        except Exception:
            pass

    elif data == "recharge_back":
        webapp_url = WEBAPP_URL if 'WEBAPP_URL' in globals() and WEBAPP_URL else "https://pay.aivison.it.com/"
        keyboard = [
            [InlineKeyboardButton("💎 TON月卡套餐", web_app=WebAppInfo(url=webapp_url))],
            [InlineKeyboardButton("⭐️ Star月卡套餐", callback_data="recharge_stars_menu")],
            [InlineKeyboardButton("⭐️ Star直充灵石", callback_data="recharge_stars_credit_menu")],
            [InlineKeyboardButton("¥ 人民币充值月卡", callback_data="recharge_rmb_menu")],
            [InlineKeyboardButton("¥ 人民币直充灵石", callback_data="recharge_rmb_credit_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.message.edit_reply_markup(reply_markup=reply_markup)
        except Exception:
            pass

    elif data == "recharge_rmb_menu":
        from src.database.core import AsyncSessionLocal
        from src.database.models import MembershipPlan
        from sqlalchemy import select
        
        keyboard = []
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(MembershipPlan).where(MembershipPlan.is_active == True, MembershipPlan.duration_days > 0).order_by(MembershipPlan.price_rmb.asc()))
            plans = result.scalars().all()
            for plan in plans:
                if getattr(plan, 'price_rmb', 0) > 0:
                    keyboard.append([InlineKeyboardButton(f"¥ {plan.price_rmb} - {plan.name} ({plan.identity_name})", callback_data=f"select_rmb_plan_{plan.id}")])
                    
        keyboard.append([InlineKeyboardButton("🔙 返回支付方式", callback_data="recharge_back")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.message.edit_reply_markup(reply_markup=reply_markup)
        except Exception:
            pass

    elif data == "recharge_rmb_credit_menu":
        from src.database.core import AsyncSessionLocal
        from src.database.models import MembershipPlan
        from sqlalchemy import select
        
        keyboard = []
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(MembershipPlan).where(MembershipPlan.is_active == True, MembershipPlan.duration_days == 0).order_by(MembershipPlan.price_rmb.asc()))
            plans = result.scalars().all()
            for plan in plans:
                if getattr(plan, 'price_rmb', 0) > 0:
                    keyboard.append([InlineKeyboardButton(f"¥ {plan.price_rmb} 直购 {plan.reward_credits} 灵石", callback_data=f"select_rmb_plan_{plan.id}")])
                    
        keyboard.append([InlineKeyboardButton("🔙 返回支付方式", callback_data="recharge_back")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.message.edit_reply_markup(reply_markup=reply_markup)
        except Exception:
            pass

    elif data.startswith("select_rmb_plan_"):
        plan_id = int(data.split("_")[-1])
        keyboard = [
            [
                InlineKeyboardButton("🟦 支付宝付款 (便利)", callback_data=f"buy_rmb_plan_{plan_id}_alipay"),
                InlineKeyboardButton("🟩 微信付款", callback_data=f"buy_rmb_plan_{plan_id}_wxpay")
            ],
            [InlineKeyboardButton("🔙 返回套餐列表", callback_data="recharge_rmb_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.message.edit_reply_markup(reply_markup=reply_markup)
        except Exception:
            pass

    elif data.startswith("buy_rmb_plan_"):
        import time
        from src.database.core import AsyncSessionLocal
        from src.database.models import MembershipPlan, Order
        from sqlalchemy import select
        from src.services.rmb_payment_service import RMBPaymentService
        
        parts = data.split("_")
        pay_type = parts[-1]
        plan_id = int(parts[-2])
        tg_id = query.from_user.id
        
        from src.core.user_core import get_or_create_user_by_telegram
        internal_user, _ = await get_or_create_user_by_telegram(tg_id)
        internal_user_id = internal_user.id
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(MembershipPlan).where(MembershipPlan.id == plan_id))
            plan = result.scalar_one_or_none()
            
            if not plan or getattr(plan, 'price_rmb', 0) <= 0:
                await safe_answer_query(query, text="❌ 找不到该套餐", show_alert=True)
                return
                
            # 尽早响应回调，清除按钮上的 loading，并修改文本提示正在生成订单
            await safe_answer_query(query, text="⏳ 正在为您生成支付链接...")
            
            try:
                await query.message.edit_text(
                    text="⏳ **正在与支付网关建立安全连接，获取专属收银台链接，请稍候...**\n"
                         "_(这通常需要 1~3 秒)_",
                    parse_mode="Markdown",
                    reply_markup=None
                )
            except Exception:
                pass
                
            # 先落库 PENDING 订单
            timestamp = int(time.time())
            out_trade_no = f"RMB_{tg_id}_{plan_id}_{timestamp}"
            
            new_order = Order(
                order_id=out_trade_no,
                telegram_id=internal_user_id,
                plan_id=plan_id,
                original_price=plan.price_rmb,
                final_price=plan.price_rmb,
                status="PENDING",
                tx_hash=out_trade_no
            )
            session.add(new_order)
            await session.commit()
            
            # 动态调整展示名称，避免出现“Star 直购”这种奇怪的名字
            if plan.duration_days == 0:
                # 直充灵石
                display_name = f"{plan.reward_credits} 灵石直充"
            else:
                # 月卡套餐
                display_name = f"{plan.identity_name} ({plan.duration_days}天)"
            
            # 向第三方发起请求
            pay_resp = await RMBPaymentService.create_payment_url(
                out_trade_no=out_trade_no,
                plan_name=display_name,
                amount=float(plan.price_rmb),
                pay_type=pay_type
            )
            
            if pay_resp and pay_resp.get("code") == 1 and pay_resp.get("data") and pay_resp["data"].get("payurl"):
                raw_pay_url = pay_resp["data"]["payurl"]
                
                # 修复易支付网关返回的链接中未进行 URL Encode 的问题
                import urllib.parse
                parsed = urllib.parse.urlparse(raw_pay_url)
                query_dict = urllib.parse.parse_qs(parsed.query)
                # 重新将参数进行标准的 urlencode
                encoded_query = urllib.parse.urlencode(query_dict, doseq=True)
                pay_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, encoded_query, parsed.fragment))
                
                keyboard = [
                    [InlineKeyboardButton("👉 点击前往付款", url=pay_url)],
                    [InlineKeyboardButton("🔙 返回充值菜单", callback_data="recharge_back")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                try:
                    pay_method_text = "🟦 支付宝 (Alipay)" if pay_type == "alipay" else "🟩 微信支付 (WeChat Pay)"
                    await query.message.edit_text(
                        text=f"💎 **合欢宗账房 - {display_name}**\n\n"
                             f"📝 **订单号**：`{out_trade_no}`\n"
                             f"💰 **支付金额**：`¥{plan.price_rmb}`\n"
                             f"💳 **支付方式**：{pay_method_text}\n\n"
                             f"⚠️ **注意事项**：\n"
                             f"• 请点击下方按钮前往安全收银台付款。\n"
                             f"• 支付完成后，大约需要 10-30 秒处理，系统会自动发送到账通知，无需刷新本页面。",
                        parse_mode="Markdown",
                        reply_markup=reply_markup
                    )
                except Exception:
                    pass
            else:
                error_msg = pay_resp.get("msg", "未知错误") if pay_resp else "请求无响应"
                await safe_answer_query(query, text=f"❌ 获取支付链接失败：{error_msg}", show_alert=True)
                
    elif data.startswith("buy_star_plan_"):
        from telegram import LabeledPrice
        import time
        from src.database.core import AsyncSessionLocal
        from src.database.models import MembershipPlan
        from sqlalchemy import select
        
        plan_id = int(data.split("_")[-1])
        user_id = query.from_user.id
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(MembershipPlan).where(MembershipPlan.id == plan_id))
            plan = result.scalar_one_or_none()
            
        if not plan or getattr(plan, 'price_stars', 0) <= 0:
            await safe_answer_query(query, text="❌ 找不到该套餐", show_alert=True)
            return
            
        # Payload 格式保持和 TON 一致，方便防重放。ORDER:{user_id}:{plan_id}:{timestamp}
        timestamp = int(time.time())
        payload = f"ORDER:{user_id}:{plan_id}:{timestamp}"
        
        title = f"💎 合欢宗账房 - {plan.name} ({plan.identity_name})"
        description = f"{plan.duration_days}天 | 赠 {plan.reward_credits} 永久灵石 | 身份：{plan.identity_name}"
        currency = "XTR"
        prices = [LabeledPrice(f"{plan.name}", plan.price_stars)]
        
        try:
            await context.bot.send_invoice(
                chat_id=query.message.chat_id,
                title=title,
                description=description,
                payload=payload,
                provider_token="",  # Telegram Stars 必须为空
                currency=currency,
                prices=prices
            )
        except Exception as e:
            await safe_answer_query(query, text=f"❌ 发送账单失败：{e}", show_alert=True)
