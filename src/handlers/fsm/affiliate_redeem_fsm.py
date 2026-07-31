import logging
import uuid
from decimal import Decimal, InvalidOperation

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.handlers.conversation_states import AffiliateRedeemState
from src.handlers.prompt_router import is_global_menu_command
from src.services.affiliate_redeem_service import (
    AFFILIATE_CREDITS_REDEEM_ALLOWED_AMOUNTS_TEXT,
    AffiliateRedeemConflictError,
    AffiliateRedeemInsufficientBalanceError,
)
from src.services.telegram_affiliate_service import (
    query_affiliate_available_balance_for_telegram_user,
    redeem_affiliate_credits_for_telegram_user,
    resolve_internal_user_id_for_telegram_user,
    request_affiliate_usdt_for_telegram_user,
)
from src.services.affiliate_redeem_rules import (
    normalize_usdt_payout_address,
    normalize_usdt_redeem_amount,
)
from src.services.affiliate_usdt_redeem_service import (
    AffiliateUsdtRedeemConflictError,
    AffiliateUsdtRedeemInsufficientBalanceError,
)
from src.utils import robust_edit_text, robust_reply_text, safe_answer_query

logger = logging.getLogger("fsm.affiliate_redeem")

AFFILIATE_REDEEM_FSM_KEY = "affiliate_redeem_data"
AFFILIATE_REDEEM_BUSY_KEY = "affiliate_redeem_busy"


def _build_followup_keyboard() -> InlineKeyboardMarkup:
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


def _build_input_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔙 返回快捷兑换", callback_data="affiliate_redeem_credits_menu")],
            [InlineKeyboardButton("🏠 返回分享面板", callback_data="affiliate_share_home")],
        ]
    )


def _cleanup_context(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("in_conversation", None)
    context.user_data.pop(AFFILIATE_REDEEM_FSM_KEY, None)
    context.user_data.pop(AFFILIATE_REDEEM_BUSY_KEY, None)


def _try_acquire_busy_lock(context: ContextTypes.DEFAULT_TYPE) -> bool:
    if context.user_data.get(AFFILIATE_REDEEM_BUSY_KEY):
        return False
    context.user_data[AFFILIATE_REDEEM_BUSY_KEY] = True
    return True


def _release_busy_lock(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(AFFILIATE_REDEEM_BUSY_KEY, None)


async def start_usdt_redeem(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await safe_answer_query(query)
    context.user_data[AFFILIATE_REDEEM_FSM_KEY] = {}
    context.user_data["in_conversation"] = True
    await robust_edit_text(
        query.message,
        (
            "💵 **返佣兑 USDT（TON 网络）**\n\n"
            "请输入兑换金额，最低 `5.0000 USDT`。\n"
            "提交后对应返佣会冻结，等待管理员人工打款。"
        ),
        parse_mode="Markdown",
    )
    return AffiliateRedeemState.WAIT_USDT_AMOUNT


async def receive_usdt_amount(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    text = (update.message.text or "").strip()
    if is_global_menu_command(text):
        _cleanup_context(context)
        await robust_reply_text(update.message, context.t("system.fsm_exit_hint"))
        return ConversationHandler.END
    try:
        amount = normalize_usdt_redeem_amount(Decimal(text))
    except (InvalidOperation, ValueError) as exc:
        await robust_reply_text(update.message, f"❌ {exc}")
        return AffiliateRedeemState.WAIT_USDT_AMOUNT
    context.user_data[AFFILIATE_REDEEM_FSM_KEY] = {"amount_usdt": amount}
    await robust_reply_text(
        update.message,
        "请输入接收 USDT 的 **TON 主网钱包地址**：",
        parse_mode="Markdown",
    )
    return AffiliateRedeemState.WAIT_USDT_ADDRESS


async def receive_usdt_address(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    text = (update.message.text or "").strip()
    if is_global_menu_command(text):
        _cleanup_context(context)
        await robust_reply_text(update.message, context.t("system.fsm_exit_hint"))
        return ConversationHandler.END
    try:
        address = normalize_usdt_payout_address(text)
    except ValueError as exc:
        await robust_reply_text(update.message, f"❌ {exc}")
        return AffiliateRedeemState.WAIT_USDT_ADDRESS
    data = context.user_data.setdefault(AFFILIATE_REDEEM_FSM_KEY, {})
    data["payout_address"] = address
    await robust_reply_text(
        update.message,
        (
            "请确认兑换申请：\n\n"
            f"金额：`{data['amount_usdt']:.4f} USDT`\n"
            "网络：`TON`\n"
            f"地址：`{address}`"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "确认提交", callback_data="affiliate_redeem_usdt_confirm"
                    ),
                    InlineKeyboardButton(
                        "取消", callback_data="affiliate_redeem_usdt_cancel"
                    ),
                ]
            ]
        ),
    )
    return AffiliateRedeemState.WAIT_USDT_CONFIRM


async def confirm_usdt_redeem(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await safe_answer_query(query)
    if query.data == "affiliate_redeem_usdt_cancel":
        _cleanup_context(context)
        await robust_edit_text(query.message, "🚫 USDT 兑换申请已取消。")
        return ConversationHandler.END
    if not _try_acquire_busy_lock(context):
        await robust_edit_text(query.message, "⚠️ 当前已有兑换请求正在处理中。")
        return AffiliateRedeemState.WAIT_USDT_CONFIRM
    try:
        data = context.user_data.get(AFFILIATE_REDEEM_FSM_KEY) or {}
        tg_user = update.effective_user
        internal_user_id = await _get_internal_user_id(update)
        result = await request_affiliate_usdt_for_telegram_user(
            telegram_user_id=tg_user.id,
            username=tg_user.username,
            full_name=tg_user.full_name,
            language_code=tg_user.language_code,
            amount_usdt=data["amount_usdt"],
            payout_address=data["payout_address"],
            idempotency_key=f"tg_affiliate_usdt:{internal_user_id}:{uuid.uuid4().hex}",
        )
        await robust_edit_text(
            query.message,
            (
                "✅ **USDT 兑换申请已提交**\n\n"
                f"申请编号：`{result.redeem_id}`\n"
                f"冻结返佣：`{result.amount_usdt:.4f} USDT`\n"
                f"剩余可用：`{result.balance.available_usdt:.4f} USDT`\n"
                "管理员处理后会通过 Bot 通知您。"
            ),
            parse_mode="Markdown",
            reply_markup=_build_followup_keyboard(),
        )
        _cleanup_context(context)
        return ConversationHandler.END
    except (
        AffiliateUsdtRedeemConflictError,
        AffiliateUsdtRedeemInsufficientBalanceError,
        ValueError,
    ) as exc:
        await robust_edit_text(query.message, f"❌ 申请失败：{exc}")
        _cleanup_context(context)
        return ConversationHandler.END
    except Exception:
        logger.exception("TG affiliate USDT redeem request failed")
        await robust_edit_text(query.message, "❌ 系统繁忙，请稍后重试。")
        _cleanup_context(context)
        return ConversationHandler.END
    finally:
        _release_busy_lock(context)


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


async def start_custom_credits_redeem(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await safe_answer_query(
        query,
        text="返佣兑灵石已改为固定六档套餐，请直接选择套餐",
        show_alert=True,
    )
    await robust_edit_text(
        query.message,
        (
            "💎 **返佣兑灵石**\n\n"
            f"仅支持固定套餐：`{AFFILIATE_CREDITS_REDEEM_ALLOWED_AMOUNTS_TEXT}`\n"
            "请点击下方按钮返回快捷兑换。"
        ),
        parse_mode="Markdown",
        reply_markup=_build_input_keyboard(),
    )
    return ConversationHandler.END


async def receive_custom_amount(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    message = update.message
    text = (message.text or "").strip()
    if is_global_menu_command(text):
        _cleanup_context(context)
        await robust_reply_text(message, context.t("system.fsm_exit_hint"))
        return ConversationHandler.END

    try:
        amount_usdt = Decimal(text).quantize(Decimal("0.0001"))
        if amount_usdt <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        await robust_reply_text(
            message,
            "❌ 金额格式不正确，请发送大于 0 的数字，例如 `2.5000`。",
            parse_mode="Markdown",
        )
        return AffiliateRedeemState.WAIT_CREDITS_AMOUNT

    if not _try_acquire_busy_lock(context):
        await robust_reply_text(message, "⚠️ 当前已有返佣兑换请求在处理中，请稍候再试。")
        return AffiliateRedeemState.WAIT_CREDITS_AMOUNT

    try:
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
            f"💰 当前灵石余额：`{result.current_credits}`\n"
            f"📦 本次套餐：`{result.amount_usdt:.4f} USDT -> {result.credits_granted} 灵石`"
        )
        await robust_reply_text(
            message,
            msg,
            parse_mode="Markdown",
            reply_markup=_build_followup_keyboard(),
        )
        _cleanup_context(context)
        return ConversationHandler.END
    except AffiliateRedeemInsufficientBalanceError as exc:
        await robust_reply_text(
            message,
            (
                "❌ **返佣可用余额不足**\n\n"
                f"🧾 当前可兑换余额：`{exc.available_balance_usdt:.4f} USDT`\n"
                f"💵 本次申请金额：`{exc.requested_amount_usdt:.4f} USDT`"
            ),
            parse_mode="Markdown",
            reply_markup=_build_followup_keyboard(),
        )
        _cleanup_context(context)
        return ConversationHandler.END
    except AffiliateRedeemConflictError:
        await robust_reply_text(
            message,
            "❌ **兑换失败**\n\n同一幂等键已被不同兑换参数占用，请重新发起一次兑换。",
            parse_mode="Markdown",
            reply_markup=_build_followup_keyboard(),
        )
        _cleanup_context(context)
        return ConversationHandler.END
    except ValueError as exc:
        await robust_reply_text(
            message,
            f"❌ **兑换失败**\n\n{str(exc)}",
            parse_mode="Markdown",
        )
        return AffiliateRedeemState.WAIT_CREDITS_AMOUNT
    except Exception:
        logger.exception("TG affiliate custom credits redeem failed")
        await robust_reply_text(
            message,
            "❌ **兑换失败**\n\n系统繁忙，请稍后重试。",
            parse_mode="Markdown",
            reply_markup=_build_followup_keyboard(),
        )
        _cleanup_context(context)
        return ConversationHandler.END
    finally:
        _release_busy_lock(context)


async def handle_input_navigation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    data = query.data
    _cleanup_context(context)
    if data == "affiliate_redeem_credits_menu":
        from src.handlers.callbacks.affiliate_callbacks import (
            affiliate_redeem_credits_menu_callback,
        )

        await affiliate_redeem_credits_menu_callback(update, context)
        return ConversationHandler.END

    from src.handlers.callbacks.affiliate_callbacks import affiliate_share_home_callback

    await affiliate_share_home_callback(update, context)
    return ConversationHandler.END


async def cancel_conversation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    msg = "🚫 流程已取消。"
    if update.callback_query:
        await robust_edit_text(update.callback_query.message, msg)
    else:
        await robust_reply_text(update.message, msg)
    _cleanup_context(context)
    return ConversationHandler.END


async def timeout_conversation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update and update.message:
        await robust_reply_text(
            update.message,
            "⏰ 操作超时，为节省系统资源，本次流程已自动取消。您可以随时重新开始。",
        )
    _cleanup_context(context)
    return ConversationHandler.END


async def unexpected_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text if update.message else ""
    if text and is_global_menu_command(text):
        _cleanup_context(context)
        await robust_reply_text(update.message, context.t("system.fsm_exit_hint"))
        return ConversationHandler.END

    await robust_reply_text(
        update.message,
        "⚠️ 当前正在等待您输入兑换金额，发送数字金额或使用 `/cancel` 退出。",
        parse_mode="Markdown",
    )
    return AffiliateRedeemState.WAIT_CREDITS_AMOUNT


def get_affiliate_redeem_fsm_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                start_custom_credits_redeem,
                pattern="^affiliate_redeem_credits_custom$",
            ),
            CallbackQueryHandler(
                start_usdt_redeem,
                pattern="^affiliate_redeem_usdt_start$",
            ),
        ],
        states={
            AffiliateRedeemState.WAIT_USDT_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_usdt_amount),
            ],
            AffiliateRedeemState.WAIT_USDT_ADDRESS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_usdt_address),
            ],
            AffiliateRedeemState.WAIT_USDT_CONFIRM: [
                CallbackQueryHandler(
                    confirm_usdt_redeem,
                    pattern="^affiliate_redeem_usdt_(confirm|cancel)$",
                ),
            ],
            AffiliateRedeemState.WAIT_CREDITS_AMOUNT: [
                CallbackQueryHandler(
                    handle_input_navigation,
                    pattern="^affiliate_redeem_credits_menu$|^affiliate_share_home$",
                ),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_custom_amount),
                MessageHandler(
                    filters.ALL & ~filters.Regex(r"^/cancel$"), unexpected_input
                ),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, timeout_conversation)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        conversation_timeout=300,
        name="affiliate_redeem_fsm",
        persistent=False,
    )
