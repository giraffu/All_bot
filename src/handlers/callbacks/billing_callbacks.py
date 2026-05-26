import time
import urllib.parse
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ContextTypes

from config import WEBAPP_URL
from src.core.user_core import get_or_create_user_by_telegram
from src.database.core import AsyncSessionLocal
from src.database.models import Order
from src.handlers.callback_router import register_callback
from src.services.membership_plan_catalog import (
    build_visible_membership_plan_lookup_stmt,
    build_visible_membership_plans_stmt,
)
from src.services.order_v2_service import (
    build_legacy_order_payload,
    build_order_settlement_snapshot,
    build_order_v2_payload,
    generate_business_order_id,
    get_order_public_id,
    is_order_v2_enabled,
)
from src.services.rmb_payment_service import RMBPaymentService
from src.i18n.translator import get_text
from src.utils import safe_answer_query
import contextlib


async def _get_active_plans(session, is_rmb: bool, is_subscription: bool):
    result = await session.execute(
        build_visible_membership_plans_stmt(
            is_rmb=is_rmb, is_subscription=is_subscription
        )
    )
    return result.scalars().all()


def _t(context, key: str, **kwargs) -> str:
    translator = getattr(context, "t", None)
    if translator is None:
        return get_text(key, "zh", **kwargs)
    return translator(key, **kwargs)


@register_callback("recharge_stars_menu")
async def recharge_stars_menu_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await safe_answer_query(query)

    keyboard = []
    async with AsyncSessionLocal() as session:
        plans = await _get_active_plans(session, is_rmb=False, is_subscription=True)
        for plan in plans:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        _t(
                            context,
                            "billing.stars_membership_option",
                            price=plan.price_stars,
                            plan_name=plan.name,
                            identity_name=plan.identity_name,
                        ),
                        callback_data=f"buy_star_plan_{plan.id}",
                    )
                ]
            )

    keyboard.append(
        [
            InlineKeyboardButton(
                _t(context, "billing.back_payment_methods"),
                callback_data="recharge_back",
            )
        ]
    )
    reply_markup = InlineKeyboardMarkup(keyboard)
    with contextlib.suppress(Exception):
        await query.message.edit_reply_markup(reply_markup=reply_markup)


@register_callback("recharge_stars_credit_menu")
async def recharge_stars_credit_menu_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await safe_answer_query(query)

    keyboard = []
    async with AsyncSessionLocal() as session:
        plans = await _get_active_plans(session, is_rmb=False, is_subscription=False)
        for plan in plans:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        _t(
                            context,
                            "billing.stars_credit_option",
                            price=plan.price_stars,
                            credits=plan.reward_credits,
                        ),
                        callback_data=f"buy_star_plan_{plan.id}",
                    )
                ]
            )

    keyboard.append(
        [
            InlineKeyboardButton(
                _t(context, "billing.back_payment_methods"),
                callback_data="recharge_back",
            )
        ]
    )
    reply_markup = InlineKeyboardMarkup(keyboard)
    with contextlib.suppress(Exception):
        await query.message.edit_reply_markup(reply_markup=reply_markup)


@register_callback("recharge_back")
async def recharge_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer_query(query)

    webapp_url = (
        WEBAPP_URL
        if "WEBAPP_URL" in globals() and WEBAPP_URL
        else "https://pay.aivison.it.com/"
    )
    keyboard = [
        [
            InlineKeyboardButton(
                _t(context, "billing.ton_monthly_plan_btn"),
                web_app=WebAppInfo(url=webapp_url),
            )
        ],
        [
            InlineKeyboardButton(
                _t(context, "billing.stars_monthly_plan_btn"),
                callback_data="recharge_stars_menu",
            )
        ],
        [
            InlineKeyboardButton(
                _t(context, "billing.stars_credit_btn"),
                callback_data="recharge_stars_credit_menu",
            )
        ],
        [
            InlineKeyboardButton(
                _t(context, "billing.rmb_monthly_plan_btn"),
                callback_data="recharge_rmb_menu",
            )
        ],
        [
            InlineKeyboardButton(
                _t(context, "billing.rmb_credit_btn"),
                callback_data="recharge_rmb_credit_menu",
            )
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    with contextlib.suppress(Exception):
        await query.message.edit_reply_markup(reply_markup=reply_markup)


@register_callback("recharge_rmb_menu")
async def recharge_rmb_menu_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await safe_answer_query(query)

    keyboard = []
    async with AsyncSessionLocal() as session:
        plans = await _get_active_plans(session, is_rmb=True, is_subscription=True)
        for plan in plans:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        _t(
                            context,
                            "billing.rmb_membership_option",
                            price=plan.price_rmb,
                            plan_name=plan.name,
                            identity_name=plan.identity_name,
                        ),
                        callback_data=f"select_rmb_plan_{plan.id}",
                    )
                ]
            )

    keyboard.append(
        [
            InlineKeyboardButton(
                _t(context, "billing.back_payment_methods"),
                callback_data="recharge_back",
            )
        ]
    )
    reply_markup = InlineKeyboardMarkup(keyboard)
    with contextlib.suppress(Exception):
        await query.message.edit_reply_markup(reply_markup=reply_markup)


@register_callback("recharge_rmb_credit_menu")
async def recharge_rmb_credit_menu_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await safe_answer_query(query)

    keyboard = []
    async with AsyncSessionLocal() as session:
        plans = await _get_active_plans(session, is_rmb=True, is_subscription=False)
        for plan in plans:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        _t(
                            context,
                            "billing.rmb_credit_option",
                            price=plan.price_rmb,
                            credits=plan.reward_credits,
                        ),
                        callback_data=f"select_rmb_plan_{plan.id}",
                    )
                ]
            )

    keyboard.append(
        [
            InlineKeyboardButton(
                _t(context, "billing.back_payment_methods"),
                callback_data="recharge_back",
            )
        ]
    )
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
            InlineKeyboardButton(
                _t(context, "billing.alipay"),
                callback_data=f"buy_rmb_plan_{plan_id}_alipay",
            ),
            InlineKeyboardButton(
                _t(context, "billing.wxpay"), callback_data=f"buy_rmb_plan_{plan_id}_wxpay"
            ),
        ],
        [
            InlineKeyboardButton(
                _t(context, "billing.back_plan_list"),
                callback_data="recharge_rmb_menu",
            )
        ],
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
        result = await session.execute(
            build_visible_membership_plan_lookup_stmt(plan_id)
        )
        plan = result.scalar_one_or_none()

        if not plan or getattr(plan, "price_rmb", 0) <= 0:
            await safe_answer_query(
                query, text=_t(context, "billing.plan_not_found"), show_alert=True
            )
            return

        await safe_answer_query(query, text=_t(context, "billing.generating_payment_link"))

        with contextlib.suppress(Exception):
            await query.message.edit_text(
                text=_t(context, "billing.gateway_connecting"),
                parse_mode="Markdown",
                reply_markup=None,
            )

        timestamp = int(time.time())
        out_trade_no = f"RMB_{tg_id}_{plan_id}_{timestamp}"

        new_order = Order(
            order_id=out_trade_no,
            business_order_id=generate_business_order_id(),
            internal_user_id=internal_user_id,
            plan_id=plan_id,
            original_price=plan.price_rmb,
            final_price=plan.price_rmb,
            settlement_schema_version="order_plan_v1",
            settlement_snapshot=build_order_settlement_snapshot(plan),
            status="PENDING",
            payment_channel="RMB",
            tx_hash=out_trade_no,
        )
        session.add(new_order)
        await session.commit()

        public_order_id = get_order_public_id(new_order)

        if plan.duration_days == 0:
            display_name = _t(
                context,
                "billing.display_name_direct_credits",
                credits=plan.reward_credits,
            )
        else:
            display_name = _t(
                context,
                "billing.display_name_membership",
                identity_name=plan.identity_name,
                days=plan.duration_days,
            )

        pay_resp = await RMBPaymentService.create_payment_url(
            out_trade_no=out_trade_no,
            plan_name=display_name,
            amount=plan.price_rmb,
            pay_type=pay_type,
        )

        if (
            pay_resp
            and pay_resp.get("code") == 1
            and pay_resp.get("data")
            and pay_resp["data"].get("payurl")
        ):
            raw_pay_url = pay_resp["data"]["payurl"]
            parsed = urllib.parse.urlparse(raw_pay_url)
            query_dict = urllib.parse.parse_qs(parsed.query)
            encoded_query = urllib.parse.urlencode(query_dict, doseq=True)
            pay_url = urllib.parse.urlunparse(
                (
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path,
                    parsed.params,
                    encoded_query,
                    parsed.fragment,
                )
            )

            keyboard = [
                [InlineKeyboardButton(_t(context, "billing.pay_button"), url=pay_url)],
                [
                    InlineKeyboardButton(
                        _t(context, "billing.back_recharge_menu"),
                        callback_data="recharge_back",
                    )
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            try:
                pay_method_text = (
                    _t(context, "billing.pay_method_alipay")
                    if pay_type == "alipay"
                    else _t(context, "billing.pay_method_wxpay")
                )
                await query.message.edit_text(
                    text=_t(
                        context,
                        "billing.payment_summary",
                        display_name=display_name,
                        order_id=public_order_id,
                        amount=plan.price_rmb,
                        pay_method=pay_method_text,
                    ),
                    parse_mode="Markdown",
                    reply_markup=reply_markup,
                )
            except Exception:
                pass
        else:
            error_msg = pay_resp.get("msg", "未知错误") if pay_resp else "请求无响应"
            await safe_answer_query(
                query,
                text=_t(context, "billing.link_failed", error_msg=error_msg),
                show_alert=True,
            )


@register_callback("buy_star_plan_")
async def buy_star_plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from telegram import LabeledPrice

    query = update.callback_query

    plan_id = int(query.data.split("_")[-1])
    user_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            build_visible_membership_plan_lookup_stmt(plan_id)
        )
        plan = result.scalar_one_or_none()

    if not plan or getattr(plan, "price_stars", 0) <= 0:
        await safe_answer_query(
            query, text=_t(context, "billing.plan_not_found"), show_alert=True
        )
        return

    await safe_answer_query(query)  # Acknowledge

    timestamp = int(time.time())
    payload = build_legacy_order_payload(
        telegram_user_id=user_id,
        plan_id=plan_id,
        timestamp=timestamp,
    )

    if is_order_v2_enabled():
        internal_user, _ = await get_or_create_user_by_telegram(user_id)
        async with AsyncSessionLocal() as session:
            business_order_id = generate_business_order_id()
            pending_order = Order(
                order_id=payload[:64],
                business_order_id=business_order_id,
                internal_user_id=internal_user.id,
                plan_id=plan.id,
                original_price=plan.price_stars,
                final_price=plan.price_stars,
                settlement_schema_version="order_plan_v1",
                settlement_snapshot=build_order_settlement_snapshot(plan),
                status="PENDING",
                payment_channel="XTR",
                created_at=datetime.now(),
            )
            session.add(pending_order)
            await session.commit()
        payload = build_order_v2_payload(business_order_id)

    title = _t(
        context,
        "billing.invoice_title",
        plan_name=plan.name,
        identity_name=plan.identity_name,
    )
    description = _t(
        context,
        "billing.invoice_description",
        days=plan.duration_days,
        credits=plan.reward_credits,
        identity_name=plan.identity_name,
    )
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
            prices=prices,
        )
    except Exception as e:
        await safe_answer_query(
            query,
            text=_t(context, "billing.invoice_failed", error_msg=e),
            show_alert=True,
        )
