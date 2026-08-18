import time
import urllib.parse

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ContextTypes

from config import (
    build_ton_payment_mini_app_url,
    build_usdt_ton_payment_mini_app_url,
)
from src.core.user_core import get_or_create_user_by_telegram
from src.handlers.callback_router import register_callback
from src.services.order_v2_service import (
    build_legacy_order_payload,
    build_order_v2_payload,
    is_order_v2_enabled,
)
from src.services.rmb_payment_provider_service import (
    create_rmb_payment_url,
    select_rmb_payment_provider,
)
from src.services.telegram_billing_service import (
    create_rmb_pending_order,
    create_stars_pending_order,
    fail_rmb_payment_creation,
    get_visible_membership_plan,
    list_visible_membership_plans,
)
from src.i18n.translator import get_text
from src.utils import safe_answer_query
import contextlib


def _t(context, key: str, **kwargs) -> str:
    translator = getattr(context, "t", None)
    if translator is None:
        return get_text(key, _get_lang(context), **kwargs)
    return translator(key, **kwargs)


def _get_lang(context) -> str:
    lang = getattr(context, "lang", None)
    if lang:
        return lang
    user_data = getattr(context, "user_data", None)
    if isinstance(user_data, dict):
        return user_data.get("language_code", "zh")
    return "zh"


def _translate_dynamic_label(context, raw_text: str | None) -> str:
    if not raw_text:
        return ""
    lang = _get_lang(context)
    translated = get_text(f"identity.{raw_text}", lang)
    if translated != f"identity.{raw_text}":
        return translated
    return get_text(raw_text, lang)


@register_callback("recharge_stars_menu")
async def recharge_stars_menu_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await safe_answer_query(query)

    keyboard = []
    plans = await list_visible_membership_plans(is_rmb=False, is_subscription=True)
    for plan in plans:
        translated_plan_name = _translate_dynamic_label(context, plan.name)
        translated_identity_name = _translate_dynamic_label(
            context, plan.identity_name
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    _t(
                        context,
                        "billing.stars_membership_option",
                        price=plan.price_stars,
                        plan_name=translated_plan_name,
                        identity_name=translated_identity_name,
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
    plans = await list_visible_membership_plans(is_rmb=False, is_subscription=False)
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

    ton_webapp_url = build_ton_payment_mini_app_url()
    keyboard = [
        [
            InlineKeyboardButton(
                _t(context, "billing.usdt_ton_monthly_plan_btn"),
                web_app=WebAppInfo(
                    url=build_usdt_ton_payment_mini_app_url(kind="membership")
                ),
            )
        ],
        [
            InlineKeyboardButton(
                _t(context, "billing.usdt_ton_credit_btn"),
                web_app=WebAppInfo(
                    url=build_usdt_ton_payment_mini_app_url(kind="credits")
                ),
            )
        ],
        [
            InlineKeyboardButton(
                _t(context, "billing.ton_monthly_plan_btn"),
                web_app=WebAppInfo(url=ton_webapp_url),
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
    plans = await list_visible_membership_plans(is_rmb=True, is_subscription=True)
    for plan in plans:
        translated_plan_name = _translate_dynamic_label(context, plan.name)
        translated_identity_name = _translate_dynamic_label(
            context, plan.identity_name
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    _t(
                        context,
                        "billing.rmb_membership_option",
                        price=plan.price_rmb,
                        plan_name=translated_plan_name,
                        identity_name=translated_identity_name,
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
    plans = await list_visible_membership_plans(is_rmb=True, is_subscription=False)
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

    plan = await get_visible_membership_plan(plan_id)

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

    payment_provider = select_rmb_payment_provider(
        user=internal_user,
        pay_type=pay_type,
    )

    new_order, public_order_id = await create_rmb_pending_order(
        internal_user_id=internal_user_id,
        plan=plan,
        out_trade_no=out_trade_no,
        payment_provider=payment_provider,
    )

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
            identity_name=_translate_dynamic_label(context, plan.identity_name),
            days=plan.duration_days,
        )

    try:
        pay_resp = await create_rmb_payment_url(
            provider=payment_provider,
            out_trade_no=out_trade_no,
            plan_name=display_name,
            amount=plan.price_rmb,
            pay_type=pay_type,
            client_type="mobile",
        )
    except Exception:
        await fail_rmb_payment_creation(order_id=new_order.id)
        pay_resp = {"code": 0, "msg": "Payment link creation failed. Please retry."}

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
        await fail_rmb_payment_creation(order_id=new_order.id)
        error_msg = pay_resp.get("msg", "未知错误") if pay_resp else "请求无响应"
        reply_markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        _t(context, "billing.back_recharge_menu"),
                        callback_data="recharge_back",
                    )
                ]
            ]
        )
        with contextlib.suppress(Exception):
            await query.message.edit_text(
                text=_t(context, "billing.link_failed", error_msg=error_msg),
                reply_markup=reply_markup,
            )


@register_callback("buy_star_plan_")
async def buy_star_plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from telegram import LabeledPrice

    query = update.callback_query

    plan_id = int(query.data.split("_")[-1])
    user_id = query.from_user.id

    plan = await get_visible_membership_plan(plan_id)

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
        business_order_id = await create_stars_pending_order(
            internal_user_id=internal_user.id,
            plan=plan,
            payload=payload,
        )
        payload = build_order_v2_payload(business_order_id)

    title = _t(
        context,
        "billing.invoice_title",
        plan_name=_translate_dynamic_label(context, plan.name),
        identity_name=_translate_dynamic_label(context, plan.identity_name),
    )
    description = _t(
        context,
        "billing.invoice_description",
        days=plan.duration_days,
        credits=plan.reward_credits,
        identity_name=_translate_dynamic_label(context, plan.identity_name),
    )
    currency = "XTR"
    prices = [LabeledPrice(_translate_dynamic_label(context, plan.name), plan.price_stars)]

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
