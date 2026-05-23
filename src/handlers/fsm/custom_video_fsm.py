from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler

from src.filters.i18n_filter import I18nFilter
from src.handlers.fsm.image_to_video_fsm import (
    _build_image_to_video_fsm_handler,
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


def get_custom_video_fsm_handler():
    return _build_image_to_video_fsm_handler(
        entry_points=[
            CommandHandler("custom_video", start_custom_video),
            MessageHandler(I18nFilter("menu.custom_video"), start_custom_video),
            CallbackQueryHandler(
                start_custom_video, pattern="^fsm_start_custom_video$"
            ),
        ],
        handler_name="custom_video_fsm",
    )


__all__ = [
    "cancel_conversation",
    "get_custom_video_fsm_handler",
    "handle_lora_selection",
    "process_settings",
    "receive_image",
    "receive_prompt",
    "start_custom_video",
    "start_custom_video_compat",
    "timeout_conversation",
    "unexpected_input",
]
