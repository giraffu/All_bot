from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.filters.i18n_filter import I18nFilter
from src.handlers.conversation_states import ImageToVideoState
from src.handlers.fsm.image_to_video_fsm import (
    cancel_conversation,
    handle_lora_selection,
    process_settings,
    receive_image,
    receive_prompt,
    start_custom_video_compat,
    timeout_conversation,
    unexpected_input,
)


async def start_custom_video(update, context) -> int:
    """Legacy alias that now reuses the unified image-to-video flow."""
    return await start_custom_video_compat(update, context)


def get_custom_video_fsm_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("custom_video", start_custom_video),
            MessageHandler(I18nFilter("menu.custom_video"), start_custom_video),
            CallbackQueryHandler(
                start_custom_video, pattern="^fsm_start_custom_video$"
            ),
        ],
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
        name="custom_video_fsm",
        persistent=False,
    )
