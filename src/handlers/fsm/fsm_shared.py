from collections.abc import Callable

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from src.handlers.prompt_router import GLOBAL_REVERSE_MAP, is_global_menu_command
from src.i18n.translator import get_text
from src.utils import robust_edit_text, robust_reply_text


def translate_fsm_text(
    context: ContextTypes.DEFAULT_TYPE, key: str, **kwargs
) -> str:
    translator = getattr(context, "t", None)
    if callable(translator):
        return translator(key, **kwargs)
    lang = getattr(context, "lang", None)
    if not lang and getattr(context, "user_data", None):
        lang = context.user_data.get("language_code")
    return get_text(key, lang or "zh", **kwargs)


async def handle_standard_fsm_cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    cleanup_func: Callable[[], None],
    translate_func: Callable[..., str] = translate_fsm_text,
    prefer_edit_callback: bool = False,
    reply_text_func=robust_reply_text,
    edit_text_func=robust_edit_text,
) -> int:
    message = translate_func(context, "fsm.common.cancelled")
    if prefer_edit_callback and update.callback_query:
        await edit_text_func(update.callback_query.message, message)
    else:
        await reply_text_func(update.message, message)
    cleanup_func()
    return ConversationHandler.END


async def handle_standard_fsm_timeout(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    cleanup_func: Callable[[], None],
    translate_func: Callable[..., str] = translate_fsm_text,
    reply_text_func=robust_reply_text,
) -> int:
    if update and update.message:
        await reply_text_func(
            update.message,
            translate_func(context, "fsm.common.timeout"),
        )
    cleanup_func()
    return ConversationHandler.END


async def handle_standard_fsm_unexpected_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    cleanup_func: Callable[[], None],
    translate_func: Callable[..., str] = translate_fsm_text,
    reply_text_func=robust_reply_text,
) -> int | None:
    text = update.message.text if update.message else ""
    if text and is_global_menu_command(text):
        route_key = GLOBAL_REVERSE_MAP.get(text)
        cleanup_func()
        if route_key == "menu.switch_lang" and update.effective_user:
            from src.handlers.message_handler_runtime import toggle_user_language

            reply_text, reply_markup = await toggle_user_language(
                context, update.effective_user
            )
            await reply_text_func(
                update.message, reply_text, reply_markup=reply_markup
            )
            return ConversationHandler.END
        await reply_text_func(update.message, translate_func(context, "system.fsm_exit_hint"))
        return ConversationHandler.END

    await reply_text_func(
        update.message,
        translate_func(context, "system.fsm_in_progress_hint"),
    )
    return None
