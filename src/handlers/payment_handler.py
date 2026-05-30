import logging
from telegram import Update
from telegram.ext import ContextTypes

from src.handlers.utils import with_db_logging_context
from src.services.telegram_payment_service import (
    TelegramStarsPaymentResult,
    process_successful_stars_payment,
    validate_stars_precheckout,
)
from src.utils import safe_answer_query

logger = logging.getLogger("bot.payment")


@with_db_logging_context
async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Answers the PreQecheckoutQuery"""
    query = update.pre_checkout_query
    if await validate_stars_precheckout(
        payload=query.invoice_payload,
        telegram_user_id=query.from_user.id,
        total_amount=query.total_amount,
    ):
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
    try:
        result = await process_successful_stars_payment(
            payload=payload,
            total_amount=successful_payment.total_amount,
            telegram_payment_charge_id=successful_payment.telegram_payment_charge_id,
        )
        if result is None or result.status == "noop":
            return
        if result.status == "amount_mismatch":
            await message.reply_text("❌ 支付金额与套餐价格不匹配，请联系管理员。")
            return

        success_msg = _build_stars_success_message(result)
        await message.reply_text(success_msg, parse_mode="Markdown")
    except Exception as e:
        logger.error("Error processing payment: %s", e)
        await message.reply_text("❌ 发货异常，请联系管理员核实订单。")


def _build_stars_success_message(result: TelegramStarsPaymentResult) -> str:
    success_msg = (
        f"🎉 **支付成功！**\n\n"
        f"感谢您的赞助，您已成功购买 **{result.plan_name}**。\n"
        f"💰 **获得永久灵石**：`{result.credits_granted}`\n"
    )
    if result.is_pure_credit_plan:
        success_msg += f"👑 **当前身份保持为**：`{result.final_identity}`\n"
    elif result.is_downgrade:
        success_msg += f"👑 **当前身份保持为**：`{result.final_identity}`\n"
        if result.converted_days > 0:
            success_msg += (
                f"⚖️ **新套餐价值已折算**：`{result.converted_days}` 天当前高级身份时长\n"
            )
    else:
        success_msg += f"👑 **当前身份晋升为**：`{result.final_identity}`\n"
        if result.converted_days > 0:
            success_msg += (
                f"⚖️ **老套餐残值已折算**：`{result.converted_days}` 天新套餐时长\n"
            )

    if result.final_expire_at:
        success_msg += f"⏳ **身份到期时间**：`{result.final_expire_at}`\n\n"
    success_msg += "祝您仙途坦荡，早日登峰造极！"
    return success_msg
