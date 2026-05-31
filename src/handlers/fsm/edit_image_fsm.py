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

from src.constants import MODE_EDIT, MODE_I2I_PRO, MODE_IMG2IMG_LORA, TASK_COSTS
from src.handlers.conversation_states import EditImageState
from src.handlers.prompt_router import GLOBAL_REVERSE_MAP, is_global_menu_command
from src.lora_catalog import (
    IMAGE_LORA_MODELS,
    get_image_lora_display_name,
    get_lora_default_strength,
)
from src.services.task_service_entrypoints_generation import process_i2i_pro_task
from src.services.task_service_generation_image import process_standard_generation_task as process_generation_task
from src.services.permission_service import permission_service
from src.services.fsm_temp_file_service import (
    cleanup_fsm_temp_files,
    download_telegram_file_to_fsm_temp,
)
from src.utils import create_background_task, robust_edit_text, robust_reply_text

from src.filters.i18n_filter import I18nFilter
from src.i18n.translator import get_text

logger = logging.getLogger("fsm.edit_image")


def _t(context: ContextTypes.DEFAULT_TYPE, key: str, **kwargs) -> str:
    translator = getattr(context, "t", None)
    if callable(translator):
        return translator(key, **kwargs)
    lang = getattr(context, "lang", None)
    if not lang and getattr(context, "user_data", None):
        lang = context.user_data.get("language_code")
    return get_text(key, lang or "zh", **kwargs)


def _cleanup_context(context: ContextTypes.DEFAULT_TYPE, _user_id: int):
    context.user_data.pop("in_conversation", None)
    pending_files = context.user_data.pop("edit_image_data", {})
    images = pending_files.get("images", [])
    cleanup_fsm_temp_files(images)


def _resolve_edit_image_mode(text: str) -> str:
    from src.handlers.prompt_router import GLOBAL_REVERSE_MAP

    route_key = GLOBAL_REVERSE_MAP.get(text)
    return MODE_EDIT if route_key == "menu.free_edit" else MODE_I2I_PRO


def _build_edit_lora_keyboard(lang: str = "zh") -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            get_image_lora_display_name(backend_name, lang),
            callback_data=f"editlora_select_{backend_name}",
        )
        for backend_name in IMAGE_LORA_MODELS.keys()
    ]
    keyboard = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(keyboard)


def _initialize_edit_image_context(
    context: ContextTypes.DEFAULT_TYPE, *, mode: str, cost: int
) -> None:
    context.user_data["in_conversation"] = "EDIT_IMAGE"
    context.user_data["edit_image_data"] = {"mode": mode, "images": [], "cost": cost}


def _build_edit_image_start_message(
    mode: str, cost: int, *, lang: str = "zh"
) -> tuple[str, InlineKeyboardMarkup | None]:
    if mode == MODE_I2I_PRO:
        from src.i18n.translator import get_text

        return (get_text("fsm.edit_image.start_i2i_pro", lang, cost=cost), None)

    from src.i18n.translator import get_text

    return (
        get_text("fsm.edit_image.start_free_edit", lang),
        _build_edit_lora_keyboard(lang),
    )


def _apply_selected_lora(
    fsm_data: dict[str, object], lora_name: str, *, lang: str = "zh"
) -> str:
    display_name = get_image_lora_display_name(lora_name, lang)
    fsm_data["lora_name"] = lora_name
    fsm_data["mode"] = MODE_IMG2IMG_LORA if lora_name else MODE_EDIT
    fsm_data["cost"] = TASK_COSTS.get(MODE_EDIT, 2)
    return display_name


def _build_reference_image_received_message(
    fsm_data: dict[str, object], *, lang: str = "zh"
) -> str:
    if fsm_data["mode"] == MODE_I2I_PRO:
        from src.i18n.translator import get_text

        return get_text("fsm.edit_image.reference_received_i2i", lang)

    num_images = len(fsm_data["images"])
    if num_images == 1:
        from src.i18n.translator import get_text

        return get_text("fsm.edit_image.reference_received_first", lang)

    fsm_data["cost"] = 6
    from src.i18n.translator import get_text

    return get_text("fsm.edit_image.reference_received_second", lang)


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
            process_i2i_pro_task(
                context=context,
                chat_id=chat_id,
                user_id=user_id,
                username=username,
                prompt=prompt,
                images=images,
            ),
        )
        return

    create_background_task(
        context,
        process_generation_task(
            context=context,
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            prompt=prompt,
            images=images,
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
        msg = _t(context, "fsm.common.maintenance")
        if update.callback_query:
            await robust_edit_text(
                update.callback_query.message, msg, parse_mode="Markdown"
            )
        else:
            await robust_reply_text(update.message, msg, parse_mode="Markdown")
        return ConversationHandler.END

    if context.user_data.get("in_conversation"):
        msg = _t(context, "fsm.common.conflict")
        await robust_reply_text(update.message, msg)
        return ConversationHandler.END

    mode = _resolve_edit_image_mode(text)
    cost = TASK_COSTS.get(mode, 2)
    _initialize_edit_image_context(context, mode=mode, cost=cost)
    msg, reply_markup = _build_edit_image_start_message(
        mode, cost, lang=getattr(context, "lang", "zh")
    )
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
    await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)
    data = query.data

    if not data.startswith("editlora_select_"):
        return EditImageState.WAIT_LORA_SELECTION

    lora_name = data.replace("editlora_select_", "")

    fsm_data = context.user_data.get("edit_image_data", {})
    if not fsm_data:
        await query.edit_message_text(_t(context, "fsm.face_video.expired_alert"))
        return ConversationHandler.END

    display_name = _apply_selected_lora(
        fsm_data, lora_name, lang=getattr(context, "lang", "zh")
    )

    msg = _t(context, "fsm.edit_image.selected_model", model_name=display_name)
    await robust_edit_text(query.message, msg, parse_mode="Markdown")
    return EditImageState.WAIT_REFERENCE_IMAGES


async def receive_reference_image(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    user_id = update.effective_user.id
    message = update.message
    fsm_data = context.user_data.get("edit_image_data")
    if not fsm_data:
        await robust_reply_text(message, _t(context, "fsm.common.expired_restart"))
        return ConversationHandler.END

    if message.document:
        if not message.document.mime_type.startswith("image/"):
            await robust_reply_text(message, _t(context, "fsm.common.invalid_image"))
            return EditImageState.WAIT_REFERENCE_IMAGES
        file_id = message.document.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id
    else:
        await robust_reply_text(message, _t(context, "fsm.common.invalid_image"))
        return EditImageState.WAIT_REFERENCE_IMAGES

    try:
        new_file = await context.bot.get_file(file_id)
        local_path = await download_telegram_file_to_fsm_temp(
            telegram_file=new_file,
            suffix=".png",
            name_hint="edit_image_ref",
        )
        fsm_data["images"].append(local_path)
    except Exception as e:
        logger.error(f"Error downloading image for FSM user {user_id}: {e}")
        await robust_reply_text(message, _t(context, "fsm.common.download_image_failed"))
        return EditImageState.WAIT_REFERENCE_IMAGES

    msg = _build_reference_image_received_message(
        fsm_data, lang=getattr(context, "lang", "zh")
    )
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
        await robust_reply_text(message, _t(context, "fsm.common.expired_restart"))
        return ConversationHandler.END

    if fsm_data["mode"] == MODE_I2I_PRO:
        await robust_reply_text(
            message, _t(context, "fsm.edit_image.single_image_only")
        )
        return EditImageState.WAIT_PROMPT

    if (
        fsm_data["mode"] in (MODE_EDIT, MODE_IMG2IMG_LORA)
        and len(fsm_data["images"]) >= 2
    ):
        await robust_reply_text(
            message,
            _t(context, "fsm.edit_image.max_two_images"),
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
        await robust_reply_text(message, _t(context, "fsm.common.already_submitted"))
        return ConversationHandler.END
    if fsm_data.get("submitting"):
        await robust_reply_text(message, _t(context, "fsm.common.already_submitted"))
        return ConversationHandler.END

    cost = fsm_data["cost"]
    mode = fsm_data["mode"]
    lora_name = fsm_data.get("lora_name", "")
    prompt = _normalize_edit_prompt(prompt, lora_name)

    images = list(fsm_data["images"])
    if not images:
        logger.warning(f"user={user_id} images empty before submit in edit_image")
        await robust_reply_text(message, _t(context, "fsm.common.missing_reference_resend"))
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    fsm_data["submitting"] = True
    if not update.effective_user:
        fsm_data.pop("submitting", None)
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
            msg = _t(
                context, "fsm.common.insufficient_credits", current=e.current, cost=e.cost
            )
            from src.utils import robust_send_message

            await robust_send_message(context.bot, chat_id, msg, parse_mode="Markdown")
            _cleanup_context(context, user_id)
            return ConversationHandler.END
        fsm_data.pop("submitting", None)
        raise e

    # 任务入口会接管这些临时文件的最终清理
    fsm_data["images"] = []

    await robust_reply_text(
        message, _t(context, "fsm.edit_image.submitting", cost=cost)
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
    msg = _t(context, "fsm.common.cancelled")
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
            _t(context, "fsm.common.timeout"),
        )
    _cleanup_context(context, user_id)
    return ConversationHandler.END


async def unexpected_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text if update.message else ""
    if text and is_global_menu_command(text):
        route_key = GLOBAL_REVERSE_MAP.get(text)
        user_id = update.effective_user.id if update.effective_user else "Unknown"
        _cleanup_context(context, user_id)
        if route_key == "menu.switch_lang" and update.effective_user:
            from src.handlers.message_handler_runtime import toggle_user_language

            reply_text, reply_markup = await toggle_user_language(
                context, update.effective_user
            )
            await robust_reply_text(
                update.message, reply_text, reply_markup=reply_markup
            )
            return ConversationHandler.END
        await robust_reply_text(update.message, _t(context, "system.fsm_exit_hint"))
        return ConversationHandler.END

    await robust_reply_text(update.message, _t(context, "system.fsm_in_progress_hint"))
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
