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
from src.handlers.prompt_router import GLOBAL_REVERSE_MAP, is_global_menu_command
from src.services.task_service_generation_image import process_standard_generation_task as process_generation_task
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
from src.i18n.translator import get_text

logger = logging.getLogger("fsm.quick_image")

# Map button text to mode
QUICK_MODES = {
    "menu.photo_edit_undress": MODE_UNDRESS,
    "menu.photo_edit_masturbation": MODE_MASTURBATION,
    "menu.photo_edit_random_faceswap": MODE_RANDOM_FACESWAP,
}


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
    fsm_data = context.user_data.pop("quick_image_data", {})
    cleanup_fsm_temp_files([fsm_data.get("image_path")])


def _resolve_image_file_id(message) -> str | None:
    if message.document:
        if not message.document.mime_type.startswith("image/"):
            return None
        return message.document.file_id
    if message.photo:
        return message.photo[-1].file_id
    return None


async def _validate_quick_image_submission(
    *,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    cost: int,
) -> bool:
    from src.core.user_core import get_or_create_user_by_telegram
    from src.core.exceptions import InsufficientCreditsError
    from src.utils import robust_send_message

    message = update.message
    internal_user, _ = await get_or_create_user_by_telegram(user_id)
    priority = await permission_service.calculate_user_priority(internal_user.id)
    if priority <= 0:
        await robust_reply_text(
            message,
            _t(context, "fsm.quick_image.priority_exhausted"),
        )
        _cleanup_context(context, user_id)
        return False

    user = update.effective_user
    if not user:
        return False

    try:
        await permission_service.check_quota(
            user.id, user.username, user.full_name, cost=cost
        )
    except Exception as exc:
        if not isinstance(exc, InsufficientCreditsError):
            raise
        await robust_send_message(
            context.bot,
            update.effective_chat.id,
            _t(
                context,
                "fsm.common.insufficient_credits",
                current=exc.current,
                cost=exc.cost,
            ),
            parse_mode="Markdown",
        )
        _cleanup_context(context, user_id)
        return False
    return True


async def _download_quick_image_input(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    file_id: str,
    user_id: int,
) -> str | None:
    try:
        new_file = await context.bot.get_file(file_id)
        return await download_telegram_file_to_fsm_temp(
            telegram_file=new_file,
            suffix=".png",
            name_hint="quick_image",
        )
    except Exception as exc:
        logger.error("Error downloading image for FSM user %s: %s", user_id, exc)
        return None


def _build_random_faceswap_reply_markup(context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton(
                _t(context, "fsm.quick_image.again_button"),
                callback_data="random_faceswap_again",
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
                _t(context, "fsm.quick_image.public_button"),
                callback_data="public_share_request",
            ),
        )
    return InlineKeyboardMarkup(keyboard)


def _resolve_random_faceswap_submission(
    *,
    prompts_config: dict,
    template_files: list[str],
    image_path: str,
) -> tuple[str, list[str], InlineKeyboardMarkup]:
    random_template = random.choice(template_files)
    template_path = f"template:{random_template}"
    prompt = prompts_config.get("face_swap", "face swap")
    return (
        prompt,
        [template_path, image_path],
        _build_random_faceswap_reply_markup,
    )


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

    mode = None
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
        msg = _t(context, "fsm.quick_image.undress_start", cost=cost)
    elif mode == MODE_MASTURBATION:
        msg = _t(context, "fsm.quick_image.masturbation_start", cost=cost)
    elif mode == MODE_RANDOM_FACESWAP:
        msg = _t(context, "fsm.quick_image.random_faceswap_start", cost=cost)

    await robust_reply_text(update.message, msg, parse_mode="Markdown")
    return QuickImageState.WAIT_IMAGE


async def receive_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    message = update.message
    fsm_data = context.user_data["quick_image_data"]
    mode = fsm_data["mode"]
    cost = fsm_data["cost"]

    file_id = _resolve_image_file_id(message)
    if not file_id:
        await robust_reply_text(message, _t(context, "fsm.common.invalid_image"))
        return QuickImageState.WAIT_IMAGE

    if not await _validate_quick_image_submission(
        update=update,
        context=context,
        user_id=user_id,
        cost=cost,
    ):
        return ConversationHandler.END

    fsm_data["image_path"] = await _download_quick_image_input(
        context=context,
        file_id=file_id,
        user_id=user_id,
    )
    if not fsm_data["image_path"]:
        await robust_reply_text(message, _t(context, "fsm.common.download_image_failed"))
        return QuickImageState.WAIT_IMAGE

    image_path = fsm_data.pop("image_path", None)
    if not image_path:
        return ConversationHandler.END  # Prevent double submit

    await robust_reply_text(
        message, _t(context, "fsm.quick_image.submit", cost=cost)
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
                    message, _t(context, "fsm.quick_image.no_template")
                )
                _cleanup_context(context, user_id)
                return ConversationHandler.END

            prompt, swapped_images, reply_markup_builder = (
                _resolve_random_faceswap_submission(
                    prompts_config=prompts_config,
                    template_files=template_files,
                    image_path=image_path,
                )
            )
            reply_markup = reply_markup_builder(context)

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
            await robust_reply_text(
                message, _t(context, "fsm.quick_image.system_error", error_msg=str(e))
            )

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
