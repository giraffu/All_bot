import asyncio
import logging
import os

from config import BOT_TYPE
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    TypeHandler,
    filters,
)

from src.billing_core_provider_setup import ensure_billing_core_providers_registered
from src.database.core import init_db
from src.handlers.callback_handler import handle_callback_query
from src.handlers.command_handler import (
    cancel,
    setup_commands,
    start,
    toggle_maintenance,
)
from src.handlers.message_handler import (
    handle_checkin,
    handle_document,
    handle_photo,
    handle_prompt,
    handle_queue_status,
    handle_video,
)
from src.logger import setup_logging
from src.services.payment_validator import build_ton_payment_validator_if_available
from src.services.usdt_ton_payment_validator import (
    build_usdt_ton_payment_validator_if_available,
)
from src.services.recovery_service import recover_active_tasks
from src.services.task_registry import TaskRegistry
from src.services.telegram_runtime_bootstrap import (
    build_telegram_bot_base_url,
    build_telegram_httpx_request,
    inject_bot_language_context,
    install_telegram_runtime_patches,
    resolve_telegram_api_base_url,
    resolve_telegram_file_base_url,
)
from src.services.telegram_update_processor import build_main_bot_update_processor
from src.task_core_provider_setup import ensure_task_core_service_providers_registered
from src.task_application_runtime import configure_task_application

logger = logging.getLogger(__name__)
install_telegram_runtime_patches(logger=logger)


def _env_enabled(name: str, *, default: bool) -> bool:
    fallback = "true" if default else "false"
    return os.getenv(name, fallback).strip().lower() in {"1", "true", "yes", "on"}


async def clean_zombies_loop(bot=None):
    from src.services.zombie_cleaner_service import clean_zombies

    core_logger = logging.getLogger("bot.core")
    while True:
        try:
            await clean_zombies(bot, client_type="bot", include_legacy=True)
        except Exception as e:
            core_logger.error(f"Error in clean_zombies_loop: {e}")
        await asyncio.sleep(600)  # Check every 10 minutes


async def global_middleware(update: Update, context):
    core_logger = logging.getLogger("bot.core")
    await inject_bot_language_context(
        update,
        context,
        logger=core_logger,
        callback_log_label="Received callback query",
    )


async def post_init(application):
    from src.handlers.prompt_router import build_global_menu_filter
    from src.services.alipay_direct_service import (
        validate_alipay_direct_startup_config,
    )

    build_global_menu_filter()
    validate_alipay_direct_startup_config()
    ensure_task_core_service_providers_registered()
    configure_task_application()
    ensure_billing_core_providers_registered()

    await init_db()
    await setup_commands(application)

    # Create a set to hold strong references to background tasks
    # The event loop only keeps weak references, so tasks can be garbage collected mid-execution if not stored.
    if "bg_tasks" not in application.bot_data:
        application.bot_data["bg_tasks"] = set()

    if _env_enabled("MAIN_BOT_PAYMENT_POLLING_ENABLED", default=True):
        payment_validator = build_ton_payment_validator_if_available(application)
        if payment_validator is not None:
            task_payment = asyncio.create_task(payment_validator.poll_transactions())
            application.bot_data["bg_tasks"].add(task_payment)
            task_payment.add_done_callback(application.bot_data["bg_tasks"].discard)

        usdt_payment_validator = build_usdt_ton_payment_validator_if_available(application)
        if usdt_payment_validator is not None:
            task_usdt_payment = asyncio.create_task(
                usdt_payment_validator.poll_transactions()
            )
            application.bot_data["bg_tasks"].add(task_usdt_payment)
            task_usdt_payment.add_done_callback(
                application.bot_data["bg_tasks"].discard
            )

    # Recover tasks from Redis
    task_recover = asyncio.create_task(
        recover_active_tasks(application, client_type="bot", include_legacy=True)
    )
    application.bot_data["bg_tasks"].add(task_recover)
    task_recover.add_done_callback(application.bot_data["bg_tasks"].discard)

    # Start automated zombie task cleaner
    if _env_enabled("MAIN_BOT_ZOMBIE_SWEEP_ENABLED", default=True):
        task_zombies = asyncio.create_task(clean_zombies_loop(application.bot))
        application.bot_data["bg_tasks"].add(task_zombies)
        task_zombies.add_done_callback(application.bot_data["bg_tasks"].discard)

    from src.services.advanced_video_prompt_task_service import (
        run_advanced_video_prompt_delivery_loop,
    )

    task_prompt_delivery = asyncio.create_task(
        run_advanced_video_prompt_delivery_loop(application)
    )
    application.bot_data["bg_tasks"].add(task_prompt_delivery)
    task_prompt_delivery.add_done_callback(application.bot_data["bg_tasks"].discard)


async def post_shutdown(application):
    core_logger = logging.getLogger("bot.core")
    core_logger.info("Bot is shutting down. Tasks are persisted in Redis.")
    await TaskRegistry.log_restart_recovery_policy(application.bot)
    from src.services.redis_client import redis_client

    await redis_client.close()


def build_advanced_video_entry_handler():
    from src.services.advanced_video_entry_policy import (
        minimax_h3_backend_enabled,
    )

    if minimax_h3_backend_enabled():
        from src.handlers.fsm.advanced_video_pro_fsm import (
            get_advanced_video_pro_fsm_handler,
        )

        return get_advanced_video_pro_fsm_handler()

    from src.handlers.fsm.ltx_video_fsm import get_ltx_video_fsm_handler

    return get_ltx_video_fsm_handler()


def main():
    setup_logging()
    core_logger = logging.getLogger("bot.core")

    # NOTE:
    # `src/bot_main.py` is the shared Telegram bot entrypoint for both PROD and TEST.
    # The name is historical. Runtime mode is selected by `BOT_TYPE`, not by filename.
    # See also: `docs/测试与入口命名约定.md`.
    #
    # Current deployment mapping:
    # - prod container `tg-bot` also starts this file
    # - test container `tg-bot-test` also starts this file
    #
    # ALLBOT_ENV is validated by config at import time. Both environments use the
    # canonical BOT_TOKEN key from their own host-side service projection.
    bot_type = BOT_TYPE
    token = os.getenv("BOT_TOKEN")

    if not token:
        core_logger.error(f"Failed to start: {bot_type} token is not configured.")
        return

    core_logger.info(f"Starting bot in {bot_type} mode...")

    api_base_url = resolve_telegram_api_base_url()
    file_base_url = resolve_telegram_file_base_url()
    mode_label = "🧪 TEST模式" if bot_type == "TEST" else "🚀 PROD模式"
    core_logger.info("%s：已启用 Local Bot API 直连 (%s)", mode_label, api_base_url)

    request = build_telegram_httpx_request()
    app = (
        ApplicationBuilder()
        .token(token)
        .base_url(build_telegram_bot_base_url())
        .base_file_url(file_base_url)
        .request(request)
        .get_updates_request(request)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .concurrent_updates(build_main_bot_update_processor())
        .build()
    )

    from src.handlers.error_handlers import global_error_handler
    from src.handlers.fsm.affiliate_redeem_fsm import get_affiliate_redeem_fsm_handler
    from src.handlers.fsm.edit_image_fsm import get_edit_image_fsm_handler
    from src.handlers.fsm.faceswap_fsm import get_faceswap_fsm_handler
    from src.handlers.fsm.image_to_video_fsm import get_image_to_video_fsm_handler
    from src.handlers.fsm.quick_image_fsm import get_quick_image_fsm_handler
    from src.handlers.fsm.quick_video_fsm import get_quick_video_fsm_handler
    from src.handlers.fsm.scail2_video_fsm import get_scail2_video_fsm_handler
    from src.handlers.fsm.txt2img_fsm import get_txt2img_fsm_handler
    from src.handlers.fsm.wan22_video_v2_fsm import get_wan22_video_v2_fsm_handler
    from src.handlers.payment_handler import (
        precheckout_callback,
        successful_payment_callback,
    )

    # Register FSM Handlers first (they must intercept text/callbacks before fallback handlers)
    app.add_handler(TypeHandler(Update, global_middleware), group=-1)
    app.add_handler(get_affiliate_redeem_fsm_handler())
    app.add_handler(get_scail2_video_fsm_handler())
    app.add_handler(get_faceswap_fsm_handler())
    app.add_handler(get_txt2img_fsm_handler())
    app.add_handler(get_edit_image_fsm_handler())
    app.add_handler(build_advanced_video_entry_handler())
    app.add_handler(get_image_to_video_fsm_handler())
    app.add_handler(get_wan22_video_v2_fsm_handler())
    app.add_handler(get_quick_image_fsm_handler())
    app.add_handler(get_quick_video_fsm_handler())

    # Register Fallback Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("maintenance", toggle_maintenance))
    app.add_handler(CommandHandler("checkin", handle_checkin))
    app.add_handler(CommandHandler("queue", handle_queue_status))
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(
        MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback)
    )
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    app.add_handler(
        MessageHandler(filters.Document.IMAGE | filters.Document.VIDEO, handle_document)
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prompt))

    # Register Global Error Handler
    app.add_error_handler(global_error_handler)

    core_logger.info(f"🧪 {bot_type} Telegram Bot started")
    import signal

    app.run_polling(
        poll_interval=0.0,
        timeout=30,
        stop_signals=(signal.SIGINT, signal.SIGTERM, signal.SIGABRT),
    )


if __name__ == "__main__":
    main()
