import asyncio
import logging
import os
import signal

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    TypeHandler,
    filters,
)

from qqcc_bot.callback_handler import handle_callback_query
from qqcc_bot.commands import cancel, setup_commands, start
from qqcc_bot.gallery_market import handle_qqcc_gallery_apply_media
from qqcc_bot.prompt_handlers import handle_prompt
from src.billing_core_provider_setup import ensure_billing_core_providers_registered
from src.database.core import init_db
from src.handlers.error_handlers import global_error_handler
from src.handlers.fsm.quick_image_fsm import get_quick_image_fsm_handler
from src.handlers.fsm.quick_video_fsm import get_quick_video_fsm_handler
from src.logger import setup_logging
from src.services.qqcc_runtime_context import QQCC_BOT_CLIENT_TYPE
from src.services.recovery_service import recover_active_tasks
from src.services.telegram_runtime_bootstrap import (
    build_telegram_bot_base_url,
    build_telegram_httpx_request,
    inject_bot_language_context,
    install_telegram_runtime_patches,
    resolve_telegram_file_base_url,
)
from src.task_core_provider_setup import ensure_task_core_service_providers_registered

logger = logging.getLogger("qqcc_bot.core")
install_telegram_runtime_patches(logger=logger)


async def global_middleware(update: Update, context):
    await inject_bot_language_context(
        update,
        context,
        logger=logger,
        callback_log_label="QQCC callback query",
    )


async def post_init(application):
    from src.handlers.prompt_router import build_global_menu_filter

    application.bot_data["bot_client_type"] = QQCC_BOT_CLIENT_TYPE
    build_global_menu_filter()
    ensure_task_core_service_providers_registered()
    ensure_billing_core_providers_registered()

    await init_db()
    await setup_commands(application)

    if "bg_tasks" not in application.bot_data:
        application.bot_data["bg_tasks"] = set()

    task_recover = asyncio.create_task(
        recover_active_tasks(
            application,
            client_type=QQCC_BOT_CLIENT_TYPE,
            include_legacy=False,
        )
    )
    application.bot_data["bg_tasks"].add(task_recover)
    task_recover.add_done_callback(application.bot_data["bg_tasks"].discard)


async def post_shutdown(application):
    logger.info("QQCC bot is shutting down. Tasks are persisted in Redis.")
    from src.services.redis_client import redis_client

    await redis_client.close()


def register_handlers(app):
    app.add_handler(TypeHandler(Update, global_middleware), group=-1)
    app.add_handler(get_quick_image_fsm_handler())
    app.add_handler(get_quick_video_fsm_handler())
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    app.add_handler(
        MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_qqcc_gallery_apply_media)
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prompt))
    app.add_error_handler(global_error_handler)


def _build_request():
    return build_telegram_httpx_request()


def build_application(token: str):
    request = _build_request()
    app = (
        ApplicationBuilder()
        .token(token)
        .base_url(build_telegram_bot_base_url())
        .base_file_url(resolve_telegram_file_base_url())
        .request(request)
        .get_updates_request(request)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    register_handlers(app)
    return app


def resolve_token(bot_type: str) -> str | None:
    if bot_type == "PROD":
        return os.getenv("QQCC_BOT_TOKEN")
    return os.getenv("QQCC_BOT_TOKEN_TEST")


def main():
    setup_logging()
    bot_type = os.getenv("BOT_TYPE", "TEST")
    token = resolve_token(bot_type)
    if not token:
        logger.error("Failed to start QQCC bot: %s token is not configured.", bot_type)
        return

    logger.info("Starting QQCC bot in %s mode...", bot_type)
    app = build_application(token)
    app.run_polling(
        poll_interval=2.0,
        timeout=30,
        stop_signals=(signal.SIGINT, signal.SIGTERM, signal.SIGABRT),
    )


if __name__ == "__main__":
    main()
