import logging
import random

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import ENABLE_PUBLIC_SHARE
from src.constants import (
    MODE_MASTURBATION,
    MODE_RANDOM_FACESWAP,
    MODE_UNDRESS,
    TASK_COSTS,
)
from src.handlers.conversation_states import QuickImageState
from src.handlers.prompt_router import is_global_menu_command
from src.services.bot_task_service import process_generation_task
from src.services.permission_service import permission_service
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

from src.filters.i18n_filter import I18nFilter

logger = logging.getLogger("fsm.quick_image")

# Map button text to mode
QUICK_MODES = {
    "menu.photo_edit_undress": MODE_UNDRESS,
    "menu.photo_edit_masturbation": MODE_MASTURBATION,
    "menu.photo_edit_random_faceswap": MODE_RANDOM_FACESWAP,
}


def _cleanup_context(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    context.user_data.pop("in_conversation", None)
    fsm_data = context.user_data.pop("quick_image_data", {})
    cleanup_fsm_temp_files([fsm_data.get("image_path")])


async def start_quick_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for 懒人P图 (单步图生图)"""
    user_id = update.effective_user.id
    message = update.message or update.edited_message
    text = message.text.strip() if message and message.text else ""
    logger.info(
        f"start_quick_image triggered by user {user_id}, text: {text.encode('utf-8')}"
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
        await robust_reply_text(update.message, msg)
        return ConversationHandler.END

    mode = None
    from src.handlers.prompt_router import GLOBAL_REVERSE_MAP

    route_key = GLOBAL_REVERSE_MAP.get(text)
    if route_key:
        mode = QUICK_MODES.get(route_key)

    if not mode:
        return ConversationHandler.END

    cost = TASK_COSTS.get(mode, 2)

    context.user_data["in_conversation"] = f"QUICK_IMAGE_{mode}"
    context.user_data["quick_image_data"] = {
        "mode": mode,
        "cost": cost,
        "image_path": None,
    }

    if mode == MODE_UNDRESS:
        msg = f"💃 **已切换到【快速脱衣】模式** (消耗 {cost} 灵石)。\n\n请发送一张包含人物的图片，我将自动处理。\n\n随时可以发送 /cancel 退出流程。"
    elif mode == MODE_MASTURBATION:
        msg = f"🥵 **已切换到【快速自慰】模式** (消耗 {cost} 灵石)。\n\n请发送一张包含人物的图片，我将自动处理。\n\n随时可以发送 /cancel 退出流程。"
    elif mode == MODE_RANDOM_FACESWAP:
        msg = f"🎭 **已切换到【随机换脸】模式** (消耗 {cost} 灵石)。\n\n请发送一张【正脸】图片，我将自动匹配模板处理。\n\n随时可以发送 /cancel 退出流程。"

    await robust_reply_text(update.message, msg, parse_mode="Markdown")
    return QuickImageState.WAIT_IMAGE


async def receive_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    message = update.message
    fsm_data = context.user_data["quick_image_data"]
    mode = fsm_data["mode"]
    cost = fsm_data["cost"]

    if message.document:
        if not message.document.mime_type.startswith("image/"):
            await robust_reply_text(message, "❌ 格式错误！请发送图片。")
            return QuickImageState.WAIT_IMAGE
        file_id = message.document.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id
    else:
        await robust_reply_text(message, "❌ 无法识别。请发送图片！")
        return QuickImageState.WAIT_IMAGE

    # Check Priority & Quota
    from src.core.user_core import get_or_create_user_by_telegram

    internal_user, _ = await get_or_create_user_by_telegram(user_id)
    priority = await permission_service.calculate_user_priority(internal_user.id)
    if priority <= 0:
        await robust_reply_text(
            message,
            "⚠️ 您的排队优先级已耗尽（或修为不足），今日已无法再凝聚灵力，请明日再来！",
        )
        _cleanup_context(context, user_id)
        return ConversationHandler.END

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
            name_hint="quick_image",
        )
        fsm_data["image_path"] = local_path
    except Exception as e:
        logger.error(f"Error downloading image for FSM user {user_id}: {e}")
        await robust_reply_text(message, "❌ 下载图片失败，请重试或发送 /cancel 退出。")
        return QuickImageState.WAIT_IMAGE

    image_path = fsm_data.pop("image_path", None)
    if not image_path:
        return ConversationHandler.END  # Prevent double submit

    await robust_reply_text(
        message, f"🚀 正在提交生成任务，预计消耗 {cost} 灵石，请耐心等待..."
    )

    prompts_config = load_prompts()

    if mode == MODE_RANDOM_FACESWAP:
        from config import MINIO_TEMPLATE_BUCKET
        from src.services.storage import storage

        try:
            template_files = storage.list_objects(
                "quick_face/", bucket=MINIO_TEMPLATE_BUCKET
            )
            template_files = [
                f
                for f in template_files
                if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
            ]
            if not template_files:
                await robust_reply_text(
                    message, "❌ 系统错误：未找到身体模板。请联系管理员添加图片。"
                )
                _cleanup_context(context, user_id)
                return ConversationHandler.END

            random_template = random.choice(template_files)
            template_path = f"template:{random_template}"
            prompt = prompts_config.get("face_swap", "face swap")
            swapped_images = [template_path, image_path]

            # Setup "Again" keyboard
            keyboard = [
                [
                    InlineKeyboardButton(
                        "🔄 再来一张", callback_data="random_faceswap_again"
                    )
                ],
                [
                    InlineKeyboardButton("👍", callback_data="rate_like"),
                    InlineKeyboardButton("👎", callback_data="rate_dislike"),
                ],
            ]
            if ENABLE_PUBLIC_SHARE:
                keyboard[0].insert(
                    0,
                    InlineKeyboardButton(
                        "🌐 公开", callback_data="public_share_request"
                    ),
                )
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Save face image path globally for "Again" button (outside FSM)
            context.user_data["last_face_image"] = image_path

            create_background_task(
                context,
                process_generation_task(
                    context,
                    message.chat_id,
                    user_id,
                    update.effective_user.username,
                    prompt,
                    swapped_images,
                    task_type="face_swap",
                    reply_markup=reply_markup,
                    cleanup=False,  # Kept for "Again"
                ),
            )
        except Exception as e:
            logger.error(f"Error in random faceswap FSM: {e}", exc_info=True)
            await robust_reply_text(message, f"❌ 系统错误：{str(e)}")

    else:
        # Undress or Masturbation
        prompt = prompts_config.get(mode, mode)
        create_background_task(
            context,
            process_generation_task(
                context,
                message.chat_id,
                user_id,
                update.effective_user.username,
                prompt,
                [image_path],
                task_type=mode,
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


def get_quick_image_fsm_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(
                I18nFilter(
                    [
                        "menu.photo_edit_undress",
                        "menu.photo_edit_masturbation",
                        "menu.photo_edit_random_faceswap",
                    ]
                ),
                start_quick_image,
            )
        ],
        states={
            QuickImageState.WAIT_IMAGE: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_image),
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
        name="quick_image_fsm",
        persistent=False,
    )
