import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.constants import (
    DEFAULT_DURATION,
    DEFAULT_RESOLUTION,
    DURATION_MULTIPLIER,
    MODE_CUSTOM_VIDEO,
    MODE_IMAGE_TO_VIDEO,
    RESOLUTION_COST,
    get_video_settings_keyboard,
)
from src.handlers.conversation_states import ImageToVideoState
from src.handlers.prompt_router import is_global_menu_command
from src.lora_catalog import VIDEO_LORA_MODELS
from src.services.permission_service import permission_service
from src.services.bot_task_service import TaskService
from src.services.fsm_temp_file_service import (
    cleanup_fsm_temp_files,
    download_telegram_file_to_fsm_temp,
)
from src.utils import create_background_task, robust_edit_text, robust_reply_text
import contextlib

from src.filters.i18n_filter import I18nFilter

logger = logging.getLogger("fsm.image_to_video")

IMAGE_TO_VIDEO_DATA_KEY = "image_to_video_data"
IMAGE_TO_VIDEO_CONVERSATION_TAG = "IMAGE_TO_VIDEO"


def _get_image_to_video_data(context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    """Return unified image-to-video FSM state."""
    return context.user_data.get(IMAGE_TO_VIDEO_DATA_KEY)


def _set_image_to_video_data(
    context: ContextTypes.DEFAULT_TYPE, data: dict[str, object]
) -> None:
    context.user_data[IMAGE_TO_VIDEO_DATA_KEY] = data


def _pop_image_to_video_data(context: ContextTypes.DEFAULT_TYPE) -> dict:
    """Pop unified image-to-video FSM state."""
    return context.user_data.pop(IMAGE_TO_VIDEO_DATA_KEY, {}) or {}


def _cleanup_context(context: ContextTypes.DEFAULT_TYPE, _user_id: int):
    context.user_data.pop("in_conversation", None)
    pending_files = _pop_image_to_video_data(context)
    cleanup_fsm_temp_files([pending_files.get("image_path")])


def _get_lora_display_name(lora_name: str | None) -> str:
    normalized_name = lora_name or ""
    return VIDEO_LORA_MODELS.get(normalized_name, normalized_name or "无")


def _build_lora_selection_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(zh_name, callback_data=f"lora_select_{backend_name}")
        for backend_name, zh_name in VIDEO_LORA_MODELS.items()
    ]
    keyboard = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(keyboard)


def _build_image_request_text(lora_name: str | None, *, from_compat_alias: bool) -> str:
    lora_display_name = _get_lora_display_name(lora_name)
    header = "🎬 **已切换到【图生视频】模式。**"
    if from_compat_alias:
        header = "🎬 **已通过兼容入口切换到【图生视频】模式。**"

    return (
        f"{header}\n\n"
        f"当前附加模型：**{lora_display_name}**\n\n"
        "【下一步】请发送一张【起始图片】。\n"
        "(注意：该模式生成视频，请确保后续提示词动作逻辑合理)\n\n"
        "随时可以发送 /cancel 退出流程。"
    )


def _build_settings_message(fsm_data: dict[str, object], cost: int) -> str:
    resolution = fsm_data["resolution"]
    duration = fsm_data["duration"]
    lora_display_name = _get_lora_display_name(fsm_data.get("lora_name"))

    return (
        f"⚙️ 当前画质：{resolution} | 时长：{duration} | 消耗灵石：{cost}\n"
        f"附加模型：**{lora_display_name}**\n\n"
        "请在下方选择您需要的画质和时长（部分画质和时长需要高境界或VIP身份解锁）：\n\n"
        "*提示：画质越高、时长越长，消耗灵石越多。注意：1024p 和 10s 无法同时选择。*\n\n"
        "【下一步】**请直接发送提示词 (Text)** 开始生成。"
    )


def _build_submit_message(lora_name: str | None, cost: int) -> str:
    task_name = "图生视频任务" if not lora_name else "附加模型视频任务"
    return f"🚀 正在提交{task_name}，预计消耗 {cost} 灵石，请耐心等待..."


def _resolve_image_to_video_task_type(context: ContextTypes.DEFAULT_TYPE) -> str:
    return (
        MODE_CUSTOM_VIDEO
        if context.user_data.get("in_conversation") == "CUSTOM_VIDEO"
        else MODE_IMAGE_TO_VIDEO
    )


async def _send_start_message(
    update: Update,
    message_text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    query = update.callback_query
    if query:
        await robust_edit_text(
            query.message,
            message_text,
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )
        return

    if update.message:
        await robust_reply_text(
            update.message,
            message_text,
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )


def _initialize_image_to_video_context(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    conversation_tag: str,
    preset_lora_name: str | None = None,
) -> None:
    context.user_data["in_conversation"] = conversation_tag
    data = {
        "resolution": DEFAULT_RESOLUTION,
        "duration": DEFAULT_DURATION,
        "image_path": None,
        "lora_name": preset_lora_name,
    }
    _set_image_to_video_data(context, data)


async def _start_image_to_video_flow(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    conversation_tag: str = IMAGE_TO_VIDEO_CONVERSATION_TAG,
    preset_lora_name: str | None = None,
    skip_lora_selection: bool = False,
) -> int:
    query = update.callback_query
    if query:
        with contextlib.suppress(Exception):
            await query.answer(text="⏳ 任务初始化中...", cache_time=2)

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
        if update.message:
            await robust_reply_text(update.message, msg)
        elif update.callback_query:
            await robust_edit_text(update.callback_query.message, msg)
        return ConversationHandler.END

    _initialize_image_to_video_context(
        context,
        conversation_tag=conversation_tag,
        preset_lora_name=preset_lora_name,
    )

    if skip_lora_selection:
        await _send_start_message(
            update,
            _build_image_request_text(
                preset_lora_name, from_compat_alias=conversation_tag == "CUSTOM_VIDEO"
            ),
        )
        return ImageToVideoState.WAIT_IMAGE

    msg = (
        "🎬 **已切换到【图生视频】模式。**\n\n"
        "【第一步】请选择附加模型（可选）：\n"
        "选择“无”时将退化为普通图生视频。\n\n"
        "随时可以发送 /cancel 退出流程。"
    )
    await _send_start_message(
        update,
        msg,
        reply_markup=_build_lora_selection_keyboard(),
    )
    return ImageToVideoState.WAIT_LORA_SELECTION


async def start_image_to_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Preferred entry point for the unified image-to-video flow."""
    return await _start_image_to_video_flow(
        update,
        context,
        conversation_tag=IMAGE_TO_VIDEO_CONVERSATION_TAG,
    )


async def start_custom_video(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Legacy /custom_video entry point backed by the unified image-to-video flow."""
    return await _start_image_to_video_flow(
        update,
        context,
        conversation_tag="CUSTOM_VIDEO",
        preset_lora_name="",
        skip_lora_selection=True,
    )


async def handle_lora_selection(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer(text="⏳ 任务初始化中...", cache_time=2)
    data = query.data

    if not data.startswith("lora_select_"):
        return ImageToVideoState.WAIT_LORA_SELECTION

    lora_name = data.replace("lora_select_", "")
    fsm_data = _get_image_to_video_data(context) or {}
    if not fsm_data:
        await query.edit_message_text("交互已失效，请重新开始。")
        return ConversationHandler.END

    fsm_data["lora_name"] = lora_name

    msg = _build_image_request_text(lora_name, from_compat_alias=False)
    await robust_edit_text(query.message, msg, parse_mode="Markdown")
    return ImageToVideoState.WAIT_IMAGE


async def receive_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    message = update.message
    fsm_data = _get_image_to_video_data(context)
    if not fsm_data:
        await robust_reply_text(
            message, "⚠️ 状态已失效或清理，请发送 /cancel 退出并重新发起任务。"
        )
        return ConversationHandler.END

    if message.document:
        if not message.document.mime_type.startswith("image/"):
            await robust_reply_text(message, "❌ 格式错误！请发送图片。")
            return ImageToVideoState.WAIT_IMAGE
        file_id = message.document.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id
    else:
        await robust_reply_text(message, "❌ 无法识别。请发送图片！")
        return ImageToVideoState.WAIT_IMAGE

    try:
        new_file = await context.bot.get_file(file_id)
        local_path = await download_telegram_file_to_fsm_temp(
            telegram_file=new_file,
            suffix=".png",
            name_hint="image_to_video",
        )
        fsm_data["image_path"] = local_path
    except Exception as e:
        logger.error(f"Error downloading image for FSM user {user_id}: {e}")
        await robust_reply_text(message, "❌ 下载图片失败，请重试或发送 /cancel 退出。")
        return ImageToVideoState.WAIT_IMAGE

    # Send settings keyboard
    from src.core.user_core import get_or_create_user_by_telegram

    internal_user, _ = await get_or_create_user_by_telegram(user_id)
    internal_user_id = internal_user.id

    user_group = await permission_service.get_user_group(internal_user_id)
    user_identity = await permission_service.get_user_identity(internal_user_id)

    res = fsm_data["resolution"]
    dur = fsm_data["duration"]
    reply_markup = get_video_settings_keyboard(
        user_group, user_identity, res, dur, context.lang
    )

    base_cost = RESOLUTION_COST.get(res, 6)
    multiplier = DURATION_MULTIPLIER.get(dur, 1.0)
    cost = int(base_cost * multiplier)

    msg_text = _build_settings_message(fsm_data, cost)

    await robust_reply_text(
        message, msg_text, reply_markup=reply_markup, parse_mode="Markdown"
    )
    return ImageToVideoState.WAIT_SETTINGS_AND_PROMPT


async def process_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle settings change via inline keyboard"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    fsm_data = _get_image_to_video_data(context) or {}
    if not fsm_data:
        with contextlib.suppress(Exception):
            await query.answer("交互已失效或任务已提交，请重新开始", show_alert=True)
        return ConversationHandler.END

    if data.startswith("set_res_"):
        new_res = data.split("_")[2]
        if new_res == "1024p" and fsm_data.get("duration") == "10s":
            fsm_data["duration"] = "8s"
            with contextlib.suppress(Exception):
                await query.answer(
                    "1024p和10s无法同时选择，已自动将时长调为8s", show_alert=True
                )
        fsm_data["resolution"] = new_res
    elif data.startswith("set_dur_"):
        new_dur = data.split("_")[2]
        if new_dur == "10s" and fsm_data.get("resolution") == "1024p":
            fsm_data["resolution"] = "720p"
            with contextlib.suppress(Exception):
                await query.answer(
                    "1024p和10s无法同时选择，已自动将画质调为720p", show_alert=True
                )
        fsm_data["duration"] = new_dur

    res = fsm_data["resolution"]
    dur = fsm_data["duration"]

    from src.core.user_core import get_or_create_user_by_telegram

    internal_user, _ = await get_or_create_user_by_telegram(user_id)
    internal_user_id = internal_user.id

    user_group = await permission_service.get_user_group(internal_user_id)
    user_identity = await permission_service.get_user_identity(internal_user_id)
    reply_markup = get_video_settings_keyboard(
        user_group, user_identity, res, dur, context.lang
    )

    base_cost = RESOLUTION_COST.get(res, 6)
    multiplier = DURATION_MULTIPLIER.get(dur, 1.0)
    cost = int(base_cost * multiplier)

    msg_text = _build_settings_message(fsm_data, cost)

    with contextlib.suppress(Exception):
        await robust_edit_text(
            query.message, msg_text, reply_markup=reply_markup, parse_mode="Markdown"
        )

    await query.answer(text="⏳ 任务初始化中...", cache_time=2)
    return ImageToVideoState.WAIT_SETTINGS_AND_PROMPT


async def receive_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    message = update.message
    prompt = message.text.strip()

    if is_global_menu_command(prompt):
        return await unexpected_input(update, context)

    fsm_data = _get_image_to_video_data(context)
    if not fsm_data:
        await robust_reply_text(message, "⚠️ 任务已提交或已过期，请勿重复操作。")
        return ConversationHandler.END

    res = fsm_data["resolution"]
    dur = fsm_data["duration"]
    lora_name = fsm_data["lora_name"]

    if res == "1024p" and dur == "10s":
        res = "720p"
        fsm_data["resolution"] = "720p"

    base_cost = RESOLUTION_COST.get(res, 6)
    multiplier = DURATION_MULTIPLIER.get(dur, 1.0)
    cost = int(base_cost * multiplier)

    image_path = fsm_data.get("image_path")
    if not image_path:
        logger.warning(
            f"user={user_id} image_path missing before submit in image_to_video"
        )
        await robust_reply_text(message, "⚠️ 任务状态已过期，请重新发送图片和提示词。")
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

    image_path = fsm_data.pop("image_path", None)
    if not image_path:
        logger.warning(
            f"user={user_id} image_path consumed by another request before submit in image_to_video"
        )
        await robust_reply_text(message, "⚠️ 任务已提交或状态已失效，请勿重复操作。")
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    await robust_reply_text(
        message, _build_submit_message(lora_name, cost)
    )

    task_type = _resolve_image_to_video_task_type(context)
    create_background_task(
        context,
        TaskService.process_image_to_video_task(
            context=context,
            chat_id=message.chat_id,
            user_id=user_id,
            username=update.effective_user.username,
            prompt=prompt,
            images=[image_path],
            resolution=res,
            duration=dur,
            task_type=task_type,
            cleanup=True,
            lora_name=lora_name,
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


def _build_image_to_video_fsm_handler(
    *,
    entry_points: list,
    handler_name: str,
) -> ConversationHandler:
    return ConversationHandler(
        entry_points=entry_points,
        states={
            ImageToVideoState.WAIT_LORA_SELECTION: [
                CallbackQueryHandler(handle_lora_selection, pattern="^lora_select_"),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
            ],
            ImageToVideoState.WAIT_IMAGE: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_image),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
            ],
            ImageToVideoState.WAIT_SETTINGS_AND_PROMPT: [
                CallbackQueryHandler(process_settings, pattern="^set_(res|dur)_"),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    receive_prompt,
                ),
                MessageHandler(
                    filters.PHOTO | filters.Document.IMAGE, unexpected_input
                ),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, timeout_conversation)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        conversation_timeout=300,
        name=handler_name,
        persistent=False,
    )


def get_image_to_video_fsm_handler() -> ConversationHandler:
    return _build_image_to_video_fsm_handler(
        entry_points=[
            CommandHandler("image_to_video", start_image_to_video),
            CommandHandler("video_lora", start_image_to_video),
            CommandHandler("custom_video", start_custom_video),
            MessageHandler(I18nFilter("menu.video_lora"), start_image_to_video),
            MessageHandler(I18nFilter("menu.custom_video"), start_custom_video),
            CallbackQueryHandler(
                start_image_to_video, pattern="^fsm_start_image_to_video$"
            ),
            CallbackQueryHandler(
                start_image_to_video, pattern="^fsm_start_video_lora$"
            ),
            CallbackQueryHandler(
                start_custom_video, pattern="^fsm_start_custom_video$"
            ),
        ],
        handler_name="image_to_video_fsm",
    )
