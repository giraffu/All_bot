"""Canonical handler ordering for the main Telegram Bot application."""

from collections.abc import Iterable

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    TypeHandler,
    filters,
)


def register_main_bot_handlers(
    application,
    *,
    middleware,
    advanced_video_entry_handler,
    advanced_video_compatibility_handlers: Iterable,
) -> None:
    from src.handlers.callback_handler import handle_callback_query
    from src.handlers.command_handler import (
        cancel,
        start,
        toggle_maintenance,
    )
    from src.handlers.error_handlers import global_error_handler
    from src.handlers.fsm.affiliate_redeem_fsm import get_affiliate_redeem_fsm_handler
    from src.handlers.fsm.edit_image_fsm import get_edit_image_fsm_handler
    from src.handlers.fsm.faceswap_fsm import get_faceswap_fsm_handler
    from src.handlers.fsm.image_to_video_fsm import get_image_to_video_fsm_handler
    from src.handlers.fsm.ltx25_video_upscale_fsm import (
        get_ltx25_video_upscale_fsm_handler,
    )
    from src.handlers.fsm.quick_image_fsm import get_quick_image_fsm_handler
    from src.handlers.fsm.quick_video_fsm import get_quick_video_fsm_handler
    from src.handlers.fsm.scail2_video_fsm import get_scail2_video_fsm_handler
    from src.handlers.fsm.txt2img_fsm import get_txt2img_fsm_handler
    from src.handlers.fsm.wan22_video_v2_fsm import get_wan22_video_v2_fsm_handler
    from src.handlers.message_handler import (
        handle_checkin,
        handle_document,
        handle_photo,
        handle_prompt,
        handle_queue_status,
        handle_video,
    )
    from src.handlers.payment_handler import (
        precheckout_callback,
        successful_payment_callback,
    )

    application.add_handler(TypeHandler(Update, middleware), group=-1)
    for handler in (
        get_affiliate_redeem_fsm_handler(),
        get_scail2_video_fsm_handler(),
        get_ltx25_video_upscale_fsm_handler(),
        get_faceswap_fsm_handler(),
        get_txt2img_fsm_handler(),
        get_edit_image_fsm_handler(),
        advanced_video_entry_handler,
        *tuple(advanced_video_compatibility_handlers),
        get_image_to_video_fsm_handler(),
        get_wan22_video_v2_fsm_handler(),
        get_quick_image_fsm_handler(),
        get_quick_video_fsm_handler(),
    ):
        application.add_handler(handler)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CommandHandler("maintenance", toggle_maintenance))
    application.add_handler(CommandHandler("checkin", handle_checkin))
    application.add_handler(CommandHandler("queue", handle_queue_status))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    application.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    application.add_handler(
        MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback)
    )
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.VIDEO, handle_video))
    application.add_handler(
        MessageHandler(filters.Document.IMAGE | filters.Document.VIDEO, handle_document)
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prompt)
    )
    application.add_error_handler(global_error_handler)
