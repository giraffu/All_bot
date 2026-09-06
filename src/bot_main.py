import asyncio
import logging
import os

from config import BOT_TYPE
from telegram import Update
from telegram.ext import ApplicationBuilder

from src.billing_core_provider_setup import ensure_billing_core_providers_registered
from src.database.core import init_db
from src.handlers.command_handler import setup_commands
from src.handlers.main_bot_handler_registry import register_main_bot_handlers
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
from src.services.main_bot_task_supervisor import (
    spawn_main_bot_task,
    stop_main_bot_tasks,
)
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

    if _env_enabled("MAIN_BOT_PAYMENT_POLLING_ENABLED", default=True):
        payment_validator = build_ton_payment_validator_if_available(application)
        if payment_validator is not None:
            spawn_main_bot_task(
                application,
                payment_validator.poll_transactions(),
                name="ton-payment-poller",
            )

        usdt_payment_validator = build_usdt_ton_payment_validator_if_available(
            application
        )
        if usdt_payment_validator is not None:
            spawn_main_bot_task(
                application,
                usdt_payment_validator.poll_transactions(),
                name="usdt-ton-payment-poller",
            )

    # Recover tasks from Redis
    spawn_main_bot_task(
        application,
        recover_active_tasks(application, client_type="bot", include_legacy=True),
        name="task-recovery",
    )

    # Start automated zombie task cleaner
    if _env_enabled("MAIN_BOT_ZOMBIE_SWEEP_ENABLED", default=True):
        spawn_main_bot_task(
            application,
            clean_zombies_loop(application.bot),
            name="zombie-sweeper",
        )

    from src.services.advanced_video_prompt_task_service import (
        run_advanced_video_prompt_delivery_loop,
    )

    spawn_main_bot_task(
        application,
        run_advanced_video_prompt_delivery_loop(application),
        name="advanced-video-prompt-delivery",
    )


async def post_shutdown(application):
    core_logger = logging.getLogger("bot.core")
    core_logger.info("Bot is shutting down. Tasks are persisted in Redis.")
    await stop_main_bot_tasks(application)
    await TaskRegistry.log_restart_recovery_policy(application.bot)
    from src.services.redis_client import redis_client

    await redis_client.close()


def build_advanced_video_entry_handler():
    from src.handlers.fsm.ltx_video_fsm import get_ltx_video_fsm_handler

    return get_ltx_video_fsm_handler()


def build_advanced_video_compatibility_handlers():
    from src.services.advanced_video_entry_policy import (
        minimax_h3_backend_enabled,
    )

    if not minimax_h3_backend_enabled():
        return []

    from src.handlers.fsm.advanced_video_pro_fsm import (
        get_advanced_video_pro_fsm_handler,
    )

    return [get_advanced_video_pro_fsm_handler(include_ltx_compatibility_routes=False)]


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

    register_main_bot_handlers(
        app,
        middleware=global_middleware,
        advanced_video_entry_handler=build_advanced_video_entry_handler(),
        advanced_video_compatibility_handlers=(
            build_advanced_video_compatibility_handlers()
        ),
    )

    core_logger.info(f"🧪 {bot_type} Telegram Bot started")
    import signal

    app.run_polling(
        poll_interval=0.0,
        timeout=30,
        stop_signals=(signal.SIGINT, signal.SIGTERM, signal.SIGABRT),
    )


if __name__ == "__main__":
    main()
