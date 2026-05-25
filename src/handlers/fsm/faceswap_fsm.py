import logging

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.constants import MODE_FACESWAP_STEP1, TASK_COSTS
from src.handlers.conversation_states import FaceSwapState
from src.handlers.prompt_router import is_global_menu_command
from src.services.permission_service import permission_service
from src.services.bot_task_service import TaskService
from src.services.fsm_temp_file_service import (
    cleanup_fsm_temp_files,
    download_telegram_file_to_fsm_temp,
)
from src.utils import (
    create_background_task,
    load_prompts,
    robust_edit_text,
    robust_reply_text,
)
import contextlib

from src.filters.i18n_filter import I18nFilter

logger = logging.getLogger("fsm.faceswap")


def _cleanup_context(context: ContextTypes.DEFAULT_TYPE, _user_id: int):
    context.user_data.pop("in_conversation", None)
    pending_files = context.user_data.pop("faceswap_data", {})
    cleanup_fsm_temp_files(
        [pending_files.get("face_image_path"), pending_files.get("body_image_path")]
    )


async def start_faceswap(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for Two-person Face Swap (快速换脸)."""
    query = update.callback_query
    if query:
        with contextlib.suppress(Exception):
            await query.answer(text="⏳ 任务初始化中...", cache_time=2)
    user_id = update.effective_user.id
    logger.info(
        f"User {user_id} triggered start_faceswap with text: {update.message.text if update.message else 'None'}"
    )

    from src.utils import is_maintenance_mode

    if is_maintenance_mode():
        msg = "⚠️ 🛠️ **系统正在维护升级中**\n\n为了提供更好的服务，当前生图/生视频节点正在维护，暂不接受新任务。\n\n您的灵石和会员权益不受影响，请稍后再试！"
        if update.callback_query:
            await robust_edit_text(
                update.callback_query.message, msg, parse_mode="Markdown"
            )
        else:
            await robust_reply_text(update.message, msg, parse_mode="Markdown")
        return ConversationHandler.END

    if context.user_data.get("in_conversation"):
        msg = "⚠️ 您当前有未完成的交互流程，请先发送 /cancel 退出当前流程后再试。"
        if update.callback_query:
            await robust_edit_text(update.callback_query.message, msg)
        else:
            await robust_reply_text(update.message, msg)
        return ConversationHandler.END

    context.user_data["in_conversation"] = "FACESWAP"
    context.user_data["faceswap_data"] = {}

    msg = "🎭 **欢迎使用双人换脸功能！**\n\n【第一步】请发送一张包含**清晰正脸**的图片（作为人脸提供者）。\n\n随时可以发送 /cancel 退出流程。"
    if update.callback_query:
        await robust_edit_text(
            update.callback_query.message, msg, parse_mode="Markdown"
        )
    else:
        await robust_reply_text(update.message, msg, parse_mode="Markdown")

    return FaceSwapState.WAIT_FACE_IMAGE


async def receive_face_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    message = update.message

    if message.document:
        if not message.document.mime_type.startswith("image/"):
            await robust_reply_text(message, "❌ 格式错误！请发送图片。")
            return FaceSwapState.WAIT_FACE_IMAGE
        file_id = message.document.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id
    else:
        await robust_reply_text(message, "❌ 无法识别。请发送图片！")
        return FaceSwapState.WAIT_FACE_IMAGE

    try:
        new_file = await context.bot.get_file(file_id)
        local_path = await download_telegram_file_to_fsm_temp(
            telegram_file=new_file,
            suffix=".png",
            name_hint="faceswap_face",
        )
        context.user_data["faceswap_data"]["face_image_path"] = local_path
    except Exception as e:
        logger.error(f"Error downloading face image for FSM user {user_id}: {e}")
        await robust_reply_text(message, "❌ 下载图片失败，请重试或发送 /cancel 退出。")
        return FaceSwapState.WAIT_FACE_IMAGE

    await robust_reply_text(
        message,
        "✅ **人脸图片已收到！**\n\n【第二步】请发送一张**目标身体图片**（即你想把脸换到哪张图上）。\n\n随时可以发送 /cancel 退出流程。",
        parse_mode="Markdown",
    )
    return FaceSwapState.WAIT_BODY_IMAGE


async def receive_body_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    message = update.message

    if message.document:
        if not message.document.mime_type.startswith("image/"):
            await robust_reply_text(message, "❌ 格式错误！请发送图片。")
            return FaceSwapState.WAIT_BODY_IMAGE
        file_id = message.document.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id
    else:
        await robust_reply_text(message, "❌ 无法识别。请发送图片！")
        return FaceSwapState.WAIT_BODY_IMAGE

    fsm_data = context.user_data.get("faceswap_data")
    face_path = fsm_data.get("face_image_path") if fsm_data else None
    if not face_path:
        logger.warning(
            f"user={user_id} face_path missing before quota check in faceswap"
        )
        await robust_reply_text(message, "⚠️ 任务状态已过期，请重新发送图片。")
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    cost = TASK_COSTS.get(MODE_FACESWAP_STEP1, 1)
    if not update.effective_user:
        return ConversationHandler.END
    user = update.effective_user
    try:
        await permission_service.check_quota(
            user.id, user.username, user.full_name, cost=cost
        )
    except Exception as e:
        from src.core.exceptions import InsufficientCreditsError

        if isinstance(e, InsufficientCreditsError):
            chat_id = update.effective_chat.id
            msg = f"🚫 **灵石不足**\n\n道友当前余额: `{e.current}` 灵石\n本次修炼需要: `{e.cost}` 灵石\n请联系管理员获取更多灵石。"
            from src.utils import robust_send_message

            await robust_send_message(context.bot, chat_id, msg, parse_mode="Markdown")
            _cleanup_context(context, user_id)
            return ConversationHandler.END
        raise e

    try:
        new_file = await context.bot.get_file(file_id)
        local_path = await download_telegram_file_to_fsm_temp(
            telegram_file=new_file,
            suffix=".png",
            name_hint="faceswap_body",
        )
        fsm_data["body_image_path"] = local_path
    except Exception as e:
        logger.error(f"Error downloading body image for FSM user {user_id}: {e}")
        await robust_reply_text(message, "❌ 下载图片失败，请重试或发送 /cancel 退出。")
        return FaceSwapState.WAIT_BODY_IMAGE

    face_path = fsm_data.pop("face_image_path", None)
    body_path = fsm_data.pop("body_image_path", None)

    if not face_path or not body_path:
        logger.warning(f"user={user_id} face_path or body_path missing before submit in faceswap")
        await robust_reply_text(message, "⚠️ 任务状态已过期，请重新发送图片。")
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    await robust_reply_text(
        message, f"🚀 正在提交双人换脸任务，预计消耗 {cost} 灵石，请耐心等待..."
    )

    prompts_config = load_prompts()
    prompt = prompts_config.get("face_swap", "face swap")
    swapped_images = [body_path, face_path]  # Body first, Face second

    create_background_task(
        context,
        TaskService.process_generation_task(
            context,
            message.chat_id,
            user_id,
            update.effective_user.username,
            prompt,
            swapped_images,
            task_type="face_swap",
            cleanup=True,
        ),
    )

    _cleanup_context(context, user_id)
    return ConversationHandler.END


async def cancel_conversation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    user_id = update.effective_user.id
    msg = "🚫 流程已取消。已清空历史上传内容。"
    if update.callback_query:
        await robust_edit_text(update.callback_query.message, msg)
    else:
        await robust_reply_text(update.message, msg)
    _cleanup_context(context, user_id)
    return ConversationHandler.END


async def timeout_conversation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    user_id = update.effective_user.id if update.effective_user else "Unknown"
    if update and update.message:
        await robust_reply_text(
            update.message,
            "⏰ 操作超时，为节省系统资源，本次流程已自动取消。您可以随时重新开始。",
        )
    _cleanup_context(context, user_id)
    return ConversationHandler.END


async def unexpected_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text if update.message else ""
    if text and is_global_menu_command(text):
        user_id = update.effective_user.id if update.effective_user else "Unknown"
        _cleanup_context(context, user_id)
        await robust_reply_text(update.message, context.t("system.fsm_exit_hint"))
        return ConversationHandler.END

    await robust_reply_text(update.message, context.t("system.fsm_in_progress_hint"))
    return None


def get_faceswap_fsm_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("faceswap", start_faceswap),
            MessageHandler(I18nFilter("menu.photo_edit_faceswap"), start_faceswap),
            CallbackQueryHandler(start_faceswap, pattern="^fsm_start_faceswap$"),
        ],
        states={
            FaceSwapState.WAIT_FACE_IMAGE: [
                MessageHandler(
                    filters.PHOTO | filters.Document.IMAGE, receive_face_image
                ),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
            ],
            FaceSwapState.WAIT_BODY_IMAGE: [
                MessageHandler(
                    filters.PHOTO | filters.Document.IMAGE, receive_body_image
                ),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, timeout_conversation)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        conversation_timeout=300,
        name="faceswap_fsm",
        persistent=False,
    )
