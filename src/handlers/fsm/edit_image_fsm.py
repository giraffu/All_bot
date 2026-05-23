import logging
import os
import uuid

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.constants import MODE_EDIT, MODE_I2I_PRO, MODE_IMG2IMG_LORA, TASK_COSTS
from src.handlers.conversation_states import EditImageState
from src.handlers.prompt_router import is_global_menu_command
from src.lora_catalog import IMAGE_LORA_MODELS, get_lora_default_strength
from src.services.permission_service import permission_service
from src.services.task_service import TaskService
from src.utils import create_background_task, robust_edit_text, robust_reply_text

from src.filters.i18n_filter import I18nFilter

logger = logging.getLogger("fsm.edit_image")


def _cleanup_context(context: ContextTypes.DEFAULT_TYPE, _user_id: int):
    context.user_data.pop("in_conversation", None)
    pending_files = context.user_data.pop("edit_image_data", {})
    images = pending_files.get("images", [])
    for path in images:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception as e:
                logger.error(f"Failed to remove {path}: {e}")


def _resolve_edit_image_mode(text: str) -> str:
    from src.handlers.prompt_router import GLOBAL_REVERSE_MAP

    route_key = GLOBAL_REVERSE_MAP.get(text)
    return MODE_EDIT if route_key == "menu.free_edit" else MODE_I2I_PRO


def _build_edit_lora_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(zh_name, callback_data=f"editlora_select_{backend_name}")
        for backend_name, zh_name in IMAGE_LORA_MODELS.items()
    ]
    keyboard = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(keyboard)


def _initialize_edit_image_context(
    context: ContextTypes.DEFAULT_TYPE, *, mode: str, cost: int
) -> None:
    context.user_data["in_conversation"] = "EDIT_IMAGE"
    context.user_data["edit_image_data"] = {"mode": mode, "images": [], "cost": cost}


def _build_edit_image_start_message(mode: str, cost: int) -> tuple[str, InlineKeyboardMarkup | None]:
    if mode == MODE_I2I_PRO:
        return (
            f"🌟 **已进入【幻想换脸】模式** (消耗 {cost} 灵石)。\n\n"
            "【第一步】请发送 1 张您的参考图片。\n\n"
            "随时可以发送 /cancel 退出流程。",
            None,
        )

    return (
        "🎨 **已进入【自由P图】模式**。\n\n"
        "【第一步】请选择您要附加的模型：\n\n"
        "随时可以发送 /cancel 退出流程。",
        _build_edit_lora_keyboard(),
    )


def _apply_selected_lora(fsm_data: dict[str, object], lora_name: str) -> str:
    zh_name = IMAGE_LORA_MODELS.get(lora_name, lora_name)
    fsm_data["lora_name"] = lora_name
    fsm_data["mode"] = MODE_IMG2IMG_LORA if lora_name else MODE_EDIT
    fsm_data["cost"] = TASK_COSTS.get(MODE_EDIT, 2)
    return zh_name if lora_name else "无"


def _build_reference_image_received_message(fsm_data: dict[str, object]) -> str:
    if fsm_data["mode"] == MODE_I2I_PRO:
        return (
            "✅ **已收到 1 张参考图。**\n\n"
            "【第二步】请直接发送**提示词 (Text)** 开始生成。\n\n"
            "💡 **提示词要求**：\n"
            "描述幻想的人物和场景，后续会将参考图中的人物换脸到幻想的场景人物中。"
        )

    num_images = len(fsm_data["images"])
    if num_images == 1:
        return (
            "✅ **已收到 1 张参考图。**\n\n"
            "【第三步】请直接发送**提示词 (Text)** 开始生成。\n"
            "（如果是双图融合，您可以继续发送第2张图片，双图融合将消耗 6 灵石）"
        )

    fsm_data["cost"] = 6
    return (
        "✅ **已收到 2 张参考图。**\n\n"
        "【第三步】请直接发送**提示词 (Text)** 开始生成。\n"
        "（双图融合将消耗 6 灵石，多余的图片将不生效）"
    )


def _normalize_edit_prompt(prompt: str, lora_name: str) -> str:
    if (
        lora_name == "qwen/adjust_pussy_anus.safetensors"
        and "adjust her pussy and anus" not in prompt.lower()
    ):
        return f"adjust her pussy and anus, {prompt}"
    return prompt


def _submit_edit_image_task(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    mode: str,
    chat_id: int,
    user_id: int,
    username: str | None,
    prompt: str,
    images: list[str],
    lora_name: str,
) -> None:
    if mode == MODE_I2I_PRO:
        create_background_task(
            context,
            TaskService.process_i2i_pro_task(
                context,
                chat_id,
                user_id,
                username,
                prompt,
                images,
            ),
        )
        return

    create_background_task(
        context,
        TaskService.process_generation_task(
            context,
            chat_id,
            user_id,
            username,
            prompt,
            images,
            is_video=False,
            task_type=mode,
            cleanup=True,
            lora_name=lora_name,
            lora_strength=get_lora_default_strength(lora_name),
        ),
    )


async def start_edit_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for 自由P图 and 幻想换脸"""
    message = update.message or update.edited_message
    text = message.text.strip() if message and message.text else ""

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

    mode = _resolve_edit_image_mode(text)
    cost = TASK_COSTS.get(mode, 2)
    _initialize_edit_image_context(context, mode=mode, cost=cost)
    msg, reply_markup = _build_edit_image_start_message(mode, cost)
    await robust_reply_text(
        update.message, msg, reply_markup=reply_markup, parse_mode="Markdown"
    )
    return (
        EditImageState.WAIT_REFERENCE_IMAGES
        if mode == MODE_I2I_PRO
        else EditImageState.WAIT_LORA_SELECTION
    )


async def handle_lora_selection(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer(text="⏳ 任务初始化中...", cache_time=2)
    data = query.data

    if not data.startswith("editlora_select_"):
        return EditImageState.WAIT_LORA_SELECTION

    lora_name = data.replace("editlora_select_", "")

    fsm_data = context.user_data.get("edit_image_data", {})
    if not fsm_data:
        await query.edit_message_text("交互已失效，请重新开始。")
        return ConversationHandler.END

    zh_name = _apply_selected_lora(fsm_data, lora_name)

    msg = f"✅ 已选择模型：**{zh_name}**\n\n【第二步】请发送【参考图片】。\n\n随时可以发送 /cancel 退出流程。"
    await robust_edit_text(query.message, msg, parse_mode="Markdown")
    return EditImageState.WAIT_REFERENCE_IMAGES


async def receive_reference_image(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    user_id = update.effective_user.id
    message = update.message
    fsm_data = context.user_data.get("edit_image_data")
    if not fsm_data:
        await robust_reply_text(message, "⚠️ 状态已过期，请重新点击菜单开始任务。")
        return ConversationHandler.END

    if message.document:
        if not message.document.mime_type.startswith("image/"):
            await robust_reply_text(message, "❌ 格式错误！请发送图片。")
            return EditImageState.WAIT_REFERENCE_IMAGES
        file_id = message.document.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id
    else:
        await robust_reply_text(message, "❌ 无法识别。请发送图片！")
        return EditImageState.WAIT_REFERENCE_IMAGES

    try:
        new_file = await context.bot.get_file(file_id)
        os.makedirs("/tmp/bot_fsm_tmp", exist_ok=True)
        local_path = f"/tmp/bot_fsm_tmp/{uuid.uuid4()}_ref.png"
        await new_file.download_to_drive(local_path)
        fsm_data["images"].append(local_path)
    except Exception as e:
        logger.error(f"Error downloading image for FSM user {user_id}: {e}")
        await robust_reply_text(message, "❌ 下载图片失败，请重试或发送 /cancel 退出。")
        return EditImageState.WAIT_REFERENCE_IMAGES

    msg = _build_reference_image_received_message(fsm_data)
    await robust_reply_text(message, msg, parse_mode="Markdown")

    # 允许接收多个图片（对于自由P图），但也允许接收文字进入下一步
    return EditImageState.WAIT_PROMPT


async def receive_additional_image(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """如果在 WAIT_PROMPT 状态下继续发图，就把图追加进去（仅自由P图）"""
    message = update.message
    fsm_data = context.user_data.get("edit_image_data")
    if not fsm_data:
        await robust_reply_text(message, "⚠️ 状态已过期，请重新点击菜单开始任务。")
        return ConversationHandler.END

    if fsm_data["mode"] == MODE_I2I_PRO:
        await robust_reply_text(
            message, "⚠️ 幻想换脸模式只需要 1 张图片，请直接发送文字提示词。"
        )
        return EditImageState.WAIT_PROMPT

    if (
        fsm_data["mode"] in (MODE_EDIT, MODE_IMG2IMG_LORA)
        and len(fsm_data["images"]) >= 2
    ):
        await robust_reply_text(
            message,
            "⚠️ 自由P图最多只支持 2 张图片融合，多余的图片将不生效，请直接发送文字提示词开始生成。",
        )
        return EditImageState.WAIT_PROMPT

    return await receive_reference_image(update, context)


async def receive_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    message = update.message
    prompt = message.text.strip()

    if is_global_menu_command(prompt):
        return await unexpected_input(update, context)

    fsm_data = context.user_data.get("edit_image_data")
    if not fsm_data:
        await robust_reply_text(message, "⚠️ 任务已提交或已过期，请勿重复操作。")
        return ConversationHandler.END

    cost = fsm_data["cost"]
    mode = fsm_data["mode"]
    lora_name = fsm_data.get("lora_name", "")
    prompt = _normalize_edit_prompt(prompt, lora_name)

    images = list(fsm_data["images"])
    if not images:
        logger.warning(f"user={user_id} images empty before submit in edit_image")
        await robust_reply_text(message, "⚠️ 任务已提交或状态已失效，请重新发送图片。")
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

    # 转移文件所有权给 TaskService
    fsm_data["images"] = []

    await robust_reply_text(
        message, f"🚀 正在提交生成任务，预计消耗 {cost} 灵石，请耐心等待..."
    )

    _submit_edit_image_task(
        context,
        mode=mode,
        chat_id=message.chat_id,
        user_id=user_id,
        username=update.effective_user.username,
        prompt=prompt,
        images=images,
        lora_name=lora_name,
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


def get_edit_image_fsm_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(
                I18nFilter(["menu.free_edit", "menu.i2i_pro"]), start_edit_image
            )
        ],
        states={
            EditImageState.WAIT_LORA_SELECTION: [
                CallbackQueryHandler(
                    handle_lora_selection, pattern="^editlora_select_"
                ),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
            ],
            EditImageState.WAIT_REFERENCE_IMAGES: [
                MessageHandler(
                    filters.PHOTO | filters.Document.IMAGE, receive_reference_image
                ),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
            ],
            EditImageState.WAIT_PROMPT: [
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    receive_prompt,
                ),
                MessageHandler(
                    filters.PHOTO | filters.Document.IMAGE, receive_additional_image
                ),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, timeout_conversation)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        conversation_timeout=300,
        name="edit_image_fsm",
        persistent=False,
    )
