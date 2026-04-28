import time
import urllib.parse

from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ContextTypes

from config import WEBAPP_URL
from src.core.user_core import get_or_create_user_by_telegram
from src.database.core import AsyncSessionLocal
from src.database.models import MembershipPlan, Order
from src.handlers.callback_router import register_callback
from src.services.rmb_payment_service import RMBPaymentService
from src.utils import safe_answer_query
import contextlib


@register_callback("recharge_stars_menu")
async def recharge_stars_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer_query(query)
    
    keyboard = []
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(MembershipPlan).where(MembershipPlan.is_active == True, MembershipPlan.duration_days > 0).order_by(MembershipPlan.price_stars.asc()))
        plans = result.scalars().all()
        for plan in plans:
            if getattr(plan, 'price_stars', 0) > 0:
                keyboard.append([InlineKeyboardButton(f"⭐️ {plan.price_stars} - {plan.name} ({plan.identity_name})", callback_data=f"buy_star_plan_{plan.id}")])
                
    keyboard.append([InlineKeyboardButton("🔙 返回支付方式", callback_data="recharge_back")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    with contextlib.suppress(Exception):
        await query.message.edit_reply_markup(reply_markup=reply_markup)

@register_callback("recharge_stars_credit_menu")
async def recharge_stars_credit_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer_query(query)
    
    keyboard = []
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(MembershipPlan).where(MembershipPlan.is_active == True, MembershipPlan.duration_days == 0).order_by(MembershipPlan.price_stars.asc()))
        plans = result.scalars().all()
        for plan in plans:
            if getattr(plan, 'price_stars', 0) > 0:
                keyboard.append([InlineKeyboardButton(f"⭐️ {plan.price_stars} Star 直购 {plan.reward_credits} 灵石", callback_data=f"buy_star_plan_{plan.id}")])
                
    keyboard.append([InlineKeyboardButton("🔙 返回支付方式", callback_data="recharge_back")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    with contextlib.suppress(Exception):
        await query.message.edit_reply_markup(reply_markup=reply_markup)

@register_callback("recharge_back")
async def recharge_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer_query(query)
    
    webapp_url = WEBAPP_URL if 'WEBAPP_URL' in globals() and WEBAPP_URL else "https://pay.aivison.it.com/"
    keyboard = [
        [InlineKeyboardButton("💎 TON月卡套餐", web_app=WebAppInfo(url=webapp_url))],
        [InlineKeyboardButton("⭐️ Star月卡套餐", callback_data="recharge_stars_menu")],
        [InlineKeyboardButton("⭐️ Star直充灵石", callback_data="recharge_stars_credit_menu")],
        [InlineKeyboardButton("¥ 人民币充值月卡", callback_data="recharge_rmb_menu")],
        [InlineKeyboardButton("¥ 人民币直充灵石", callback_data="recharge_rmb_credit_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    with contextlib.suppress(Exception):
        await query.message.edit_reply_markup(reply_markup=reply_markup)

@register_callback("recharge_rmb_menu")
async def recharge_rmb_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer_query(query)
    
    keyboard = []
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(MembershipPlan).where(MembershipPlan.is_active == True, MembershipPlan.duration_days > 0).order_by(MembershipPlan.price_rmb.asc()))
        plans = result.scalars().all()
        for plan in plans:
            if getattr(plan, 'price_rmb', 0) > 0:
                keyboard.append([InlineKeyboardButton(f"¥ {plan.price_rmb} - {plan.name} ({plan.identity_name})", callback_data=f"select_rmb_plan_{plan.id}")])
                
    keyboard.append([InlineKeyboardButton("🔙 返回支付方式", callback_data="recharge_back")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    with contextlib.suppress(Exception):
        await query.message.edit_reply_markup(reply_markup=reply_markup)

@register_callback("recharge_rmb_credit_menu")
async def recharge_rmb_credit_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer_query(query)
    
    keyboard = []
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(MembershipPlan).where(MembershipPlan.is_active == True, MembershipPlan.duration_days == 0).order_by(MembershipPlan.price_rmb.asc()))
        plans = result.scalars().all()
        for plan in plans:
            if getattr(plan, 'price_rmb', 0) > 0:
                keyboard.append([InlineKeyboardButton(f"¥ {plan.price_rmb} 直购 {plan.reward_credits} 灵石", callback_data=f"select_rmb_plan_{plan.id}")])
                
    keyboard.append([InlineKeyboardButton("🔙 返回支付方式", callback_data="recharge_back")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    with contextlib.suppress(Exception):
        await query.message.edit_reply_markup(reply_markup=reply_markup)

@register_callback("select_rmb_plan_")
async def select_rmb_plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer_query(query)
    
    plan_id = int(query.data.split("_")[-1])
    keyboard = [
        [
            InlineKeyboardButton("🟦 支付宝付款 (便利)", callback_data=f"buy_rmb_plan_{plan_id}_alipay"),
            InlineKeyboardButton("🟩 微信付款", callback_data=f"buy_rmb_plan_{plan_id}_wxpay")
        ],
        [InlineKeyboardButton("🔙 返回套餐列表", callback_data="recharge_rmb_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    with contextlib.suppress(Exception):
        await query.message.edit_reply_markup(reply_markup=reply_markup)

@register_callback("buy_rmb_plan_")
async def buy_rmb_plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    parts = data.split("_")
    pay_type = parts[-1]
    plan_id = int(parts[-2])
    tg_id = query.from_user.id
    
    internal_user, _ = await get_or_create_user_by_telegram(tg_id)
    internal_user_id = internal_user.id
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(MembershipPlan).where(MembershipPlan.id == plan_id))
        plan = result.scalar_one_or_none()
        
        if not plan or getattr(plan, 'price_rmb', 0) <= 0:
            await safe_answer_query(query, text="❌ 找不到该套餐", show_alert=True)
            return
            
        await safe_answer_query(query, text="⏳ 正在为您生成支付链接...")
        
        with contextlib.suppress(Exception):
            await query.message.edit_text(
                text="⏳ **正在与支付网关建立安全连接，获取专属收银台链接，请稍候...**\n"
                     "_(这通常需要 1~3 秒)_",
                parse_mode="Markdown",
                reply_markup=None
            )
            
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
        
        if plan.duration_days == 0:
            display_name = f"{plan.reward_credits} 灵石直充"
        else:
            display_name = f"{plan.identity_name} ({plan.duration_days}天)"
        
        pay_resp = await RMBPaymentService.create_payment_url(
            out_trade_no=out_trade_no,
            plan_name=display_name,
            amount=float(plan.price_rmb),
            pay_type=pay_type
        )
        
        if pay_resp and pay_resp.get("code") == 1 and pay_resp.get("data") and pay_resp["data"].get("payurl"):
            raw_pay_url = pay_resp["data"]["payurl"]
            parsed = urllib.parse.urlparse(raw_pay_url)
            query_dict = urllib.parse.parse_qs(parsed.query)
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

@register_callback("buy_star_plan_")
async def buy_star_plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from telegram import LabeledPrice
    query = update.callback_query
    
    plan_id = int(query.data.split("_")[-1])
    user_id = query.from_user.id
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(MembershipPlan).where(MembershipPlan.id == plan_id))
        plan = result.scalar_one_or_none()
        
    if not plan or getattr(plan, 'price_stars', 0) <= 0:
        await safe_answer_query(query, text="❌ 找不到该套餐", show_alert=True)
        return
        
    await safe_answer_query(query) # Acknowledge
    
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
            provider_token="",  
            currency=currency,
            prices=prices
        )
    except Exception as e:
        await safe_answer_query(query, text=f"❌ 发送账单失败：{e}", show_alert=True)
