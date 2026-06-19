import contextlib
import logging
import uuid
from datetime import datetime
from decimal import Decimal

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.handlers.callback_router import register_callback
from src.core.user_facade import get_user_dashboard_info
from src.services.affiliate_redeem_service import (
    AFFILIATE_MEMBERSHIP_REDEEM_OPTIONS,
    AFFILIATE_CREDITS_REDEEM_ALLOWED_AMOUNTS_TEXT,
    AffiliateRedeemConflictError,
    AffiliateRedeemInsufficientBalanceError,
    is_affiliate_membership_redeem_enabled,
    is_membership_settlement_v2_enabled,
    list_affiliate_credits_redeem_packages,
)
from src.services.telegram_affiliate_service import (
    query_affiliate_available_balance_for_telegram_user,
    redeem_affiliate_credits_for_telegram_user,
    redeem_affiliate_membership_for_telegram_user,
    resolve_internal_user_id_for_telegram_user,
)
from src.utils import robust_edit_text, safe_answer_query

logger = logging.getLogger(__name__)

AFFILIATE_REDEEM_BUSY_KEY = "affiliate_redeem_busy"


def _build_affiliate_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "返佣兑灵石", callback_data="affiliate_redeem_credits_menu"
                ),
                InlineKeyboardButton(
                    "返佣兑身份", callback_data="affiliate_redeem_membership_menu"
                ),
            ]
        ]
    )


def _build_credits_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                f"{package['amount_usdt']:.0f} USDT -> {package['credits']} 灵石",
                callback_data=(
                    f"affiliate_redeem_credits_amount_{package['amount_usdt']:.4f}"
                ),
            )
        ]
        for package in list_affiliate_credits_redeem_packages()
    ]
    rows.append(
        [InlineKeyboardButton("🔙 返回分享面板", callback_data="affiliate_share_home")]
    )
    return InlineKeyboardMarkup(rows)


def _build_membership_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for option_key, option in AFFILIATE_MEMBERSHIP_REDEEM_OPTIONS.items():
        if not option.get("is_enabled", False):
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    (
                        f"{option['display_name']} | "
                        f"{Decimal(str(option['redeem_amount_usdt'])):.4f} USDT | "
                        f"+{int(option['reward_credits'])} 灵石"
                    ),
                    callback_data=f"affiliate_redeem_membership_option_{option_key}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton("🔙 返回分享面板", callback_data="affiliate_share_home")]
    )
    return InlineKeyboardMarkup(rows)


def _build_post_redeem_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "继续兑灵石", callback_data="affiliate_redeem_credits_menu"
                ),
                InlineKeyboardButton(
                    "返佣兑身份", callback_data="affiliate_redeem_membership_menu"
                ),
            ],
            [InlineKeyboardButton("🔙 返回分享面板", callback_data="affiliate_share_home")],
        ]
    )


def _format_expire_at(value: str | None) -> str:
    if not value:
        return "未设置"
    with contextlib.suppress(ValueError):
        parsed = datetime.fromisoformat(value)
        return parsed.strftime("%Y-%m-%d %H:%M")
    return value.replace("T", " ")


def _format_invitation_stats(invitation_recharge: dict, available_balance: Decimal) -> str:
    total_commission = invitation_recharge.get(
        "total_commission_usdt", invitation_recharge.get("commission_usdt", 0.0)
    )
    return (
        "🤝 **邀请数据**：\n"
        f"  - 邀请充值：已有 `{invitation_recharge['recharged_invitees_count']}` 位道友完成 `{invitation_recharge['total_recharge_count']}` 次充值\n"
        f"  - 累积充值：`{invitation_recharge['total_ton']:.2f}` TON\n"
        f"  - 累积充值：`¥ {invitation_recharge['total_rmb']:.2f}`\n"
        f"  - 累积贡献：`{invitation_recharge['total_stars']}` Stars\n"
        f"  - 历史累计返佣：`{float(total_commission):.2f} USDT`\n"
        f"  - 已兑换返佣：`{float(invitation_recharge.get('spent_commission_usdt', 0.0)):.2f} USDT`\n"
        f"  - 当前可兑换余额：`{available_balance:.4f} USDT`\n"
        "  - 返佣说明：历史累计返佣用于展示成绩；当前可兑换余额才会随兑换减少"
    )


def _try_acquire_busy_lock(context: ContextTypes.DEFAULT_TYPE) -> bool:
    if context.user_data.get(AFFILIATE_REDEEM_BUSY_KEY):
        return False
    context.user_data[AFFILIATE_REDEEM_BUSY_KEY] = True
    return True


def _release_busy_lock(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(AFFILIATE_REDEEM_BUSY_KEY, None)


async def _ensure_no_active_conversation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    query = update.callback_query
    if context.user_data.get("in_conversation"):
        await safe_answer_query(
            query,
            text="您当前有未完成的交互流程，请先发送 /cancel 退出后再试",
            show_alert=True,
        )
        return False
    return True


async def _get_internal_user_id(update: Update) -> int:
    tg_user = update.effective_user
    return await resolve_internal_user_id_for_telegram_user(
        telegram_user_id=tg_user.id,
        username=tg_user.username,
        full_name=tg_user.full_name,
        language_code=tg_user.language_code,
    )


async def _query_available_balance(update: Update) -> Decimal:
    tg_user = update.effective_user
    return await query_affiliate_available_balance_for_telegram_user(
        telegram_user_id=tg_user.id,
        username=tg_user.username,
        full_name=tg_user.full_name,
        language_code=tg_user.language_code,
    )


async def _build_affiliate_home_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    tg_user = update.effective_user
    dto = await get_user_dashboard_info(tg_user.id, tg_user.first_name or "道友")
    available_balance = await _query_available_balance(update)
    bot_username = context.bot.username or (await context.bot.get_me()).username
    invite_link = f"https://t.me/{bot_username}?start={tg_user.id}"
    invitation_recharge = dto.invitation_recharge or {}

    return (
        "🤝 **分享赚灵石**\n\n"
        f"👤 **当前等级**：`{dto.current_group}`\n"
        f"🪪 **当前身份**：`{dto.current_identity}`\n"
        f"🔗 **您的专属链接**：\n`{invite_link}`\n\n"
        "📈 **邀请统计**：\n"
        f"👥 已邀请人数：`{dto.invitations}` 人\n\n"
        f"{_format_invitation_stats(invitation_recharge, available_balance)}\n\n"
        "💡 **规则**：\n"
        "- 只邀请注册：您暂不获得灵石；新道友仍获得 `6` 欢迎灵石。\n"
        "- 新道友拜入宗门：您的邀请奖励累计至 `5` 灵石。\n"
        "- 新道友首次成功生成内容：您的邀请奖励累计至 `10` 灵石。\n\n"
        "👇 请选择您要进行的返佣兑换操作："
    )


@register_callback("affiliate_share_home")
async def affiliate_share_home_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await safe_answer_query(query)
    msg = await _build_affiliate_home_text(update, context)
    await robust_edit_text(
        query.message,
        msg,
        parse_mode="Markdown",
        reply_markup=_build_affiliate_home_keyboard(),
    )


@register_callback("affiliate_redeem_credits_menu")
async def affiliate_redeem_credits_menu_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    if not await _ensure_no_active_conversation(update, context):
        return
    await safe_answer_query(query)

    available_balance = await _query_available_balance(update)
    msg = (
        "💎 **返佣兑灵石**\n\n"
        f"🧾 当前可兑换余额：`{available_balance:.4f} USDT`\n"
        f"🎁 固定套餐：`{AFFILIATE_CREDITS_REDEEM_ALLOWED_AMOUNTS_TEXT}`\n"
        "请选择您要兑换的固定套餐。"
    )
    await robust_edit_text(
        query.message,
        msg,
        parse_mode="Markdown",
        reply_markup=_build_credits_keyboard(),
    )


@register_callback("affiliate_redeem_credits_amount_")
async def affiliate_redeem_credits_amount_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    if not await _ensure_no_active_conversation(update, context):
        return
    if not _try_acquire_busy_lock(context):
        await safe_answer_query(
            query,
            text="当前已有返佣兑换请求在处理中，请稍候再试",
            show_alert=True,
        )
        return

    try:
        amount_usdt = Decimal(query.data.removeprefix("affiliate_redeem_credits_amount_"))
        await safe_answer_query(query, text="⏳ 正在处理返佣兑换...")
        await robust_edit_text(
            query.message,
            f"⏳ **正在为您兑换灵石**\n\n本次申请：`{amount_usdt:.4f} USDT`",
            parse_mode="Markdown",
        )

        tg_user = update.effective_user
        internal_user_id = await _get_internal_user_id(update)
        result = await redeem_affiliate_credits_for_telegram_user(
            telegram_user_id=tg_user.id,
            username=tg_user.username,
            full_name=tg_user.full_name,
            language_code=tg_user.language_code,
            amount_usdt=amount_usdt,
            idempotency_key=f"tg_affiliate_credits:{internal_user_id}:{uuid.uuid4().hex}",
        )

        msg = (
            "✅ **返佣兑灵石成功**\n\n"
            f"💵 扣减返佣：`{result.amount_usdt:.4f} USDT`\n"
            f"💎 获得灵石：`{result.credits_granted}`\n"
            f"🧾 剩余可兑换返佣：`{result.available_balance_usdt:.4f} USDT`\n"
            f"💰 当前灵石余额：`{result.current_credits}`"
        )
        await robust_edit_text(
            query.message,
            msg,
            parse_mode="Markdown",
            reply_markup=_build_post_redeem_keyboard(),
        )
    except AffiliateRedeemInsufficientBalanceError as exc:
        msg = (
            "❌ **返佣可用余额不足**\n\n"
            f"🧾 当前可兑换余额：`{exc.available_balance_usdt:.4f} USDT`\n"
            f"💵 本次申请金额：`{exc.requested_amount_usdt:.4f} USDT`"
        )
        await robust_edit_text(
            query.message,
            msg,
            parse_mode="Markdown",
            reply_markup=_build_credits_keyboard(),
        )
    except AffiliateRedeemConflictError:
        await robust_edit_text(
            query.message,
            "❌ **兑换失败**\n\n同一幂等键已被不同兑换参数占用，请重新发起一次兑换。",
            parse_mode="Markdown",
            reply_markup=_build_credits_keyboard(),
        )
    except ValueError as exc:
        await robust_edit_text(
            query.message,
            f"❌ **兑换失败**\n\n{str(exc)}",
            parse_mode="Markdown",
            reply_markup=_build_credits_keyboard(),
        )
    except Exception:
        logger.exception("TG affiliate credits redeem failed")
        await robust_edit_text(
            query.message,
            "❌ **兑换失败**\n\n系统繁忙，请稍后重试。",
            parse_mode="Markdown",
            reply_markup=_build_credits_keyboard(),
        )
    finally:
        _release_busy_lock(context)


@register_callback("affiliate_redeem_membership_menu")
async def affiliate_redeem_membership_menu_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    if not await _ensure_no_active_conversation(update, context):
        return

    if not (
        is_membership_settlement_v2_enabled()
        and is_affiliate_membership_redeem_enabled()
    ):
        await safe_answer_query(query, text="返佣兑身份功能当前未开启", show_alert=True)
        return

    await safe_answer_query(query)
    available_balance = await _query_available_balance(update)
    msg = (
        "🪪 **返佣兑身份**\n\n"
        f"🧾 当前可兑换余额：`{available_balance:.4f} USDT`\n"
        "请选择要兑换的身份档位。兑换成功后会立即更新当前身份、到期时间，并附加对应灵石奖励。"
    )
    await robust_edit_text(
        query.message,
        msg,
        parse_mode="Markdown",
        reply_markup=_build_membership_keyboard(),
    )


@register_callback("affiliate_redeem_membership_option_")
async def affiliate_redeem_membership_option_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    if not await _ensure_no_active_conversation(update, context):
        return
    if not _try_acquire_busy_lock(context):
        await safe_answer_query(
            query,
            text="当前已有返佣兑换请求在处理中，请稍候再试",
            show_alert=True,
        )
        return

    option_key = query.data.removeprefix("affiliate_redeem_membership_option_")
    option = AFFILIATE_MEMBERSHIP_REDEEM_OPTIONS.get(option_key)
    if option is None:
        _release_busy_lock(context)
        await safe_answer_query(query, text="找不到该身份档位", show_alert=True)
        return

    try:
        await safe_answer_query(query, text="⏳ 正在处理返佣兑换...")
        await robust_edit_text(
            query.message,
            (
                "⏳ **正在为您兑换身份**\n\n"
                f"本次申请：`{option['display_name']}`\n"
                f"消耗返佣：`{Decimal(str(option['redeem_amount_usdt'])):.4f} USDT`\n"
                f"附加灵石：`{int(option['reward_credits'])}`"
            ),
            parse_mode="Markdown",
        )

        tg_user = update.effective_user
        internal_user_id = await _get_internal_user_id(update)
        result = await redeem_affiliate_membership_for_telegram_user(
            telegram_user_id=tg_user.id,
            username=tg_user.username,
            full_name=tg_user.full_name,
            language_code=tg_user.language_code,
            option_key=option_key,
            idempotency_key=(
                f"tg_affiliate_membership:{internal_user_id}:{uuid.uuid4().hex}"
            ),
        )

        msg = (
            "✅ **返佣兑身份成功**\n\n"
            f"🪪 当前身份：`{result.current_identity}`\n"
            f"📅 到期时间：`{_format_expire_at(result.identity_expire_at)}`\n"
            f"💵 扣减返佣：`{result.amount_usdt:.4f} USDT`\n"
            f"💎 附加灵石：`{result.credits_granted}`\n"
            f"🧾 剩余可兑换返佣：`{result.available_balance_usdt:.4f} USDT`\n"
            f"💰 当前灵石余额：`{result.current_credits}`"
        )
        await robust_edit_text(
            query.message,
            msg,
            parse_mode="Markdown",
            reply_markup=_build_post_redeem_keyboard(),
        )
    except AffiliateRedeemInsufficientBalanceError as exc:
        msg = (
            "❌ **返佣可用余额不足**\n\n"
            f"🧾 当前可兑换余额：`{exc.available_balance_usdt:.4f} USDT`\n"
            f"💵 本次申请金额：`{exc.requested_amount_usdt:.4f} USDT`"
        )
        await robust_edit_text(
            query.message,
            msg,
            parse_mode="Markdown",
            reply_markup=_build_membership_keyboard(),
        )
    except AffiliateRedeemConflictError:
        await robust_edit_text(
            query.message,
            "❌ **兑换失败**\n\n同一幂等键已被不同兑换参数占用，请重新发起一次兑换。",
            parse_mode="Markdown",
            reply_markup=_build_membership_keyboard(),
        )
    except ValueError as exc:
        await robust_edit_text(
            query.message,
            f"❌ **兑换失败**\n\n{str(exc)}",
            parse_mode="Markdown",
            reply_markup=_build_membership_keyboard(),
        )
    except Exception:
        logger.exception("TG affiliate membership redeem failed")
        await robust_edit_text(
            query.message,
            "❌ **兑换失败**\n\n系统繁忙，请稍后重试。",
            parse_mode="Markdown",
            reply_markup=_build_membership_keyboard(),
        )
    finally:
        _release_busy_lock(context)
