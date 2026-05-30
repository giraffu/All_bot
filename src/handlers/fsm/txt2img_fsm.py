import logging

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.constants import MODE_TXT2IMG, TASK_COSTS
from src.handlers.conversation_states import Txt2ImgState
from src.handlers.fsm.fsm_shared import (
    handle_standard_fsm_cancel,
    handle_standard_fsm_timeout,
    handle_standard_fsm_unexpected_input,
    translate_fsm_text,
)
from src.handlers.prompt_router import is_global_menu_command
from src.services.task_service_entrypoints_generation import process_generation_task
from src.services.permission_service import permission_service
from src.utils import create_background_task, robust_reply_text

from src.filters.i18n_filter import I18nFilter

logger = logging.getLogger("fsm.txt2img")

_t = translate_fsm_text


def _cleanup_context(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("in_conversation", None)
    context.user_data.pop("txt2img_data", None)


async def start_txt2img(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from src.utils import is_maintenance_mode

    if is_maintenance_mode():
        await robust_reply_text(
            update.message, _t(context, "fsm.common.maintenance"), parse_mode="Markdown"
        )
        return ConversationHandler.END

    if context.user_data.get("in_conversation"):
        await robust_reply_text(update.message, _t(context, "fsm.common.conflict"))
        return ConversationHandler.END

    cost = TASK_COSTS.get(MODE_TXT2IMG, 2)
    context.user_data["in_conversation"] = "TXT2IMG"
    context.user_data["txt2img_data"] = {"cost": cost}
    await robust_reply_text(
        update.message,
        _t(context, "fsm.txt2img.start", cost=cost),
        parse_mode="Markdown",
    )
    return Txt2ImgState.WAIT_PROMPT


async def receive_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message
    prompt = (message.text or "").strip()

    if is_global_menu_command(prompt):
        return await unexpected_input(update, context)

    if not prompt:
        await robust_reply_text(message, _t(context, "fsm.txt2img.empty_prompt"))
        return Txt2ImgState.WAIT_PROMPT

    fsm_data = context.user_data.get("txt2img_data")
    if not fsm_data:
        await robust_reply_text(message, _t(context, "fsm.common.already_submitted"))
        return ConversationHandler.END

    cost = fsm_data.get("cost", TASK_COSTS.get(MODE_TXT2IMG, 2))

    if not update.effective_user:
        _cleanup_context(context)
        return ConversationHandler.END

    user = update.effective_user
    try:
        await permission_service.check_quota(
            user.id,
            user.username,
            user.full_name,
            cost=cost,
        )
    except Exception as e:
        from src.core.exceptions import InsufficientCreditsError
        from src.utils import robust_send_message

        if isinstance(e, InsufficientCreditsError):
            msg = _t(
                context,
                "fsm.common.insufficient_credits",
                current=e.current,
                cost=e.cost,
            )
            await robust_send_message(
                context.bot,
                update.effective_chat.id,
                msg,
                parse_mode="Markdown",
            )
            _cleanup_context(context)
            return ConversationHandler.END
        raise

    await robust_reply_text(message, _t(context, "fsm.txt2img.submitting", cost=cost))

    create_background_task(
        context,
        process_generation_task(
            context,
            message.chat_id,
            user.id,
            user.username,
            prompt,
            [],
            is_video=False,
            task_type=MODE_TXT2IMG,
            cleanup=False,
        ),
    )

    _cleanup_context(context)
    return ConversationHandler.END


async def receive_non_text_input(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    await robust_reply_text(update.message, _t(context, "fsm.txt2img.prompt_only"))
    return Txt2ImgState.WAIT_PROMPT


async def cancel_conversation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    return await handle_standard_fsm_cancel(
        update,
        context,
        cleanup_func=lambda: _cleanup_context(context),
        translate_func=_t,
        reply_text_func=robust_reply_text,
    )


async def timeout_conversation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    return await handle_standard_fsm_timeout(
        update,
        context,
        cleanup_func=lambda: _cleanup_context(context),
        translate_func=_t,
        reply_text_func=robust_reply_text,
    )


async def unexpected_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    result = await handle_standard_fsm_unexpected_input(
        update,
        context,
        cleanup_func=lambda: _cleanup_context(context),
        translate_func=_t,
        reply_text_func=robust_reply_text,
    )
    return Txt2ImgState.WAIT_PROMPT if result is None else result


def get_txt2img_fsm_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(I18nFilter("menu.txt2img"), start_txt2img),
        ],
        states={
            Txt2ImgState.WAIT_PROMPT: [
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    receive_prompt,
                ),
                MessageHandler(
                    filters.PHOTO | filters.Document.ALL,
                    receive_non_text_input,
                ),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, timeout_conversation)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        conversation_timeout=300,
        name="txt2img_fsm",
        persistent=False,
    )
