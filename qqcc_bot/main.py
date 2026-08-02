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
from qqcc_bot.polling_liveness import (
    QqccPollingHeartbeatRequest,
    QqccPollingLivenessWatchdog,
)
from qqcc_bot.private_bot_fsm import get_private_bot_provisioning_handler
from qqcc_bot.prompt_handlers import handle_prompt
from src.billing_core_provider_setup import ensure_billing_core_providers_registered
from src.database.core import init_db
from src.handlers.error_handlers import global_error_handler
from src.handlers.fsm.quick_image_fsm import get_quick_image_fsm_handler
from src.handlers.fsm.quick_video_fsm import get_quick_video_fsm_handler
from src.logger import setup_logging
from src.services.qqcc_runtime_context import QQCC_BOT_CLIENT_TYPE
from src.services.qqcc_channel_membership_service import (
    QQCC_CHANNEL_MEMBERSHIP_CHECKER_KEY,
)
from src.services.recovery_service import recover_active_tasks
from src.services.zombie_cleaner_service import clean_zombies
from src.services.telegram_runtime_bootstrap import (
    build_telegram_bot_base_url,
    build_telegram_httpx_request,
    inject_bot_language_context,
    install_telegram_runtime_patches,
    resolve_telegram_file_base_url,
)
from src.services.telegram_update_processor import build_qqcc_bot_update_processor
from src.task_core_provider_setup import ensure_task_core_service_providers_registered

logger = logging.getLogger("qqcc_bot.core")
install_telegram_runtime_patches(logger=logger)
_shared_bootstrap_lock = asyncio.Lock()
_shared_bootstrap_complete = False


async def _clean_official_qqcc_zombies(application) -> None:
    while True:
        try:
            await clean_zombies(
                application.bot,
                client_type=QQCC_BOT_CLIENT_TYPE,
                include_legacy=False,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "QQCC zombie cleanup failed error_type=%s",
                type(exc).__name__,
            )
        await asyncio.sleep(600)


async def global_middleware(update: Update, context):
    await inject_bot_language_context(
        update,
        context,
        logger=logger,
        callback_log_label="QQCC callback query",
    )


async def mark_update_completed(update: Update, context):
    watchdog = context.application.bot_data.get("polling_liveness_watchdog")
    if watchdog is not None and update.update_id is not None:
        watchdog.mark_update_completed(update.update_id)


async def post_init(application):
    application.bot_data.setdefault("bot_client_type", QQCC_BOT_CLIENT_TYPE)
    await ensure_shared_qqcc_runtime_bootstrap()
    if application.bot_data.get("setup_bot_commands", True):
        await setup_commands(application)

    if "bg_tasks" not in application.bot_data:
        application.bot_data["bg_tasks"] = set()

    if application.bot_data.get("recover_tasks", True):
        task_recover = asyncio.create_task(
            recover_active_tasks(
                application,
                client_type=application.bot_data["bot_client_type"],
                include_legacy=False,
            )
        )
        application.bot_data["bg_tasks"].add(task_recover)
        task_recover.add_done_callback(application.bot_data["bg_tasks"].discard)
        if application.bot_data["bot_client_type"] == QQCC_BOT_CLIENT_TYPE:
            task_zombies = asyncio.create_task(
                _clean_official_qqcc_zombies(application),
                name="qqcc-zombie-cleaner",
            )
            application.bot_data["bg_tasks"].add(task_zombies)
            task_zombies.add_done_callback(application.bot_data["bg_tasks"].discard)


async def ensure_shared_qqcc_runtime_bootstrap() -> None:
    global _shared_bootstrap_complete

    if _shared_bootstrap_complete:
        return
    async with _shared_bootstrap_lock:
        if _shared_bootstrap_complete:
            return
        from src.handlers.prompt_router import build_global_menu_filter

        build_global_menu_filter()
        ensure_task_core_service_providers_registered()
        ensure_billing_core_providers_registered()
        await init_db()
        _shared_bootstrap_complete = True


async def post_shutdown(application):
    logger.info("QQCC bot is shutting down. Tasks are persisted in Redis.")
    if application.bot_data.get("close_shared_redis_on_shutdown", True):
        from src.services.redis_client import redis_client

        await redis_client.close()


def register_handlers(app, *, include_private_bot_provisioning: bool = True):
    app.add_handler(TypeHandler(Update, global_middleware), group=-1)
    if include_private_bot_provisioning:
        app.add_handler(get_private_bot_provisioning_handler())
    app.add_handler(get_quick_image_fsm_handler())
    app.add_handler(get_quick_video_fsm_handler())
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    app.add_handler(
        MessageHandler(
            filters.PHOTO | filters.Document.IMAGE, handle_qqcc_gallery_apply_media
        )
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prompt))
    app.add_handler(TypeHandler(Update, mark_update_completed), group=1000)
    app.add_error_handler(global_error_handler)


def _build_request(*, connection_pool_size: int = 500):
    return build_telegram_httpx_request(
        connection_pool_size=connection_pool_size,
        connect_timeout=10.0,
        read_timeout=30.0,
        write_timeout=30.0,
    )


def build_application(
    token: str,
    *,
    bot_client_type: str = QQCC_BOT_CLIENT_TYPE,
    private_bot_id: int | None = None,
    config_loader=None,
    include_private_bot_provisioning: bool = True,
    recover_tasks: bool = True,
    close_shared_redis_on_shutdown: bool = True,
    telegram_base_url: str | None = None,
    telegram_file_base_url: str | None = None,
    setup_bot_commands: bool = True,
    request_connection_pool_size: int = 500,
    channel_membership_checker=None,
    polling_liveness_watchdog: QqccPollingLivenessWatchdog | None = None,
):
    request = _build_request(connection_pool_size=request_connection_pool_size)
    get_updates_request = request
    if polling_liveness_watchdog is not None:
        get_updates_request = QqccPollingHeartbeatRequest(
            polling_liveness_watchdog,
            connection_pool_size=request_connection_pool_size,
            connect_timeout=60.0,
            read_timeout=120.0,
            write_timeout=120.0,
        )
    builder = (
        ApplicationBuilder()
        .token(token)
        .base_url(telegram_base_url or build_telegram_bot_base_url())
        .base_file_url(telegram_file_base_url or resolve_telegram_file_base_url())
        .request(request)
        .get_updates_request(get_updates_request)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
    )
    if bot_client_type == QQCC_BOT_CLIENT_TYPE:
        builder = builder.concurrent_updates(build_qqcc_bot_update_processor())
    app = builder.build()
    app.bot_data["bot_client_type"] = bot_client_type
    app.bot_data["recover_tasks"] = recover_tasks
    app.bot_data["close_shared_redis_on_shutdown"] = close_shared_redis_on_shutdown
    app.bot_data["setup_bot_commands"] = setup_bot_commands
    if polling_liveness_watchdog is not None:
        app.bot_data["polling_liveness_watchdog"] = polling_liveness_watchdog
    app.bot_data["private_bot_provisioning_enabled"] = bool(
        include_private_bot_provisioning
    )
    if private_bot_id is not None:
        app.bot_data["private_qqcc_bot_id"] = int(private_bot_id)
    if config_loader is not None:
        app.bot_data["qqcc_config_loader"] = config_loader
    if callable(channel_membership_checker):
        app.bot_data[QQCC_CHANNEL_MEMBERSHIP_CHECKER_KEY] = channel_membership_checker
    register_handlers(
        app,
        include_private_bot_provisioning=include_private_bot_provisioning,
    )
    return app


def resolve_token(bot_type: str) -> str | None:
    return os.getenv("QQCC_BOT_TOKEN")


def main():
    setup_logging()
    from src.runtime_environment import resolve_runtime_environment

    _, bot_type = resolve_runtime_environment()
    token = resolve_token(bot_type)
    if not token:
        logger.error("Failed to start QQCC bot: %s token is not configured.", bot_type)
        return

    logger.info("Starting QQCC bot in %s mode...", bot_type)
    private_bot_enabled = os.getenv(
        "PRIVATE_QQCC_BOT_ENABLED",
        "false",
    ).strip().lower() in {"1", "true", "yes", "on"}
    polling_watchdog = QqccPollingLivenessWatchdog()
    app = build_application(
        token,
        include_private_bot_provisioning=private_bot_enabled,
        polling_liveness_watchdog=polling_watchdog,
    )
    polling_watchdog.start()
    try:
        app.run_polling(
            poll_interval=2.0,
            timeout=30,
            stop_signals=(signal.SIGINT, signal.SIGTERM, signal.SIGABRT),
        )
    finally:
        polling_watchdog.stop()


if __name__ == "__main__":
    main()
