from __future__ import annotations

import logging
import signal

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from observer_bot.config import ObserverSettings
from observer_bot.handlers import collect_authorized_group_message
from observer_bot.lmstudio_client import LMStudioClient
from observer_bot.notifier import TelegramAdminNotifier
from observer_bot.queue_monitor import CentralQueueClient, QueueMonitor
from observer_bot.report_service import ReportService
from observer_bot.repository import ObserverRepository
from observer_bot.runtime import (
    handle_report,
    handle_start,
    handle_status,
    queue_monitor_job,
    report_tick_job,
    retention_job,
)
from observer_bot.runtime_config import ObserverRuntimeConfigProvider
from src.log_redaction import install_log_redaction

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    install_log_redaction()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        force=True,
    )


def build_application(
    settings: ObserverSettings,
    *,
    repository=None,
    queue_client=None,
    lm_client=None,
):
    repository = repository or ObserverRepository(settings.database_url)
    queue_client = queue_client or CentralQueueClient(settings.central_api_url)
    lm_client = lm_client or LMStudioClient(
        base_url=settings.lm_studio_base_url,
        api_key=settings.lm_studio_api_key,
        preferred_model=settings.lm_studio_model,
        timeout_seconds=settings.lm_studio_timeout_seconds,
    )
    request = HTTPXRequest(
        proxy=None,
        connect_timeout=settings.telegram_connect_timeout,
        read_timeout=settings.telegram_read_timeout,
        write_timeout=settings.telegram_write_timeout,
        connection_pool_size=settings.telegram_pool_size,
    )

    async def post_init(application) -> None:
        await repository.open()
        await repository.bootstrap_runtime_config(
            admin_chat_ids=settings.admin_chat_ids,
            authorized_group_ids=settings.authorized_group_ids,
        )
        runtime_config_provider = ObserverRuntimeConfigProvider(repository)
        notifier = TelegramAdminNotifier(
            application.bot,
            runtime_config_provider=runtime_config_provider,
            repository=repository,
        )
        queue_monitor = QueueMonitor(
            client=queue_client,
            state_repository=repository,
            notifier=notifier,
            queue_size_threshold=settings.queue_size_threshold,
            wait_threshold_seconds=settings.queue_wait_threshold_seconds,
            cooldown_seconds=settings.queue_alert_cooldown_seconds,
            failure_threshold=settings.queue_failure_threshold,
        )
        report_service = ReportService(
            repository=repository,
            lm_client=lm_client,
            notifier=notifier,
            chunk_chars=settings.report_chunk_chars,
            max_input_chars=settings.report_max_input_chars,
        )
        application.bot_data.update(
            notifier=notifier,
            queue_monitor=queue_monitor,
            report_service=report_service,
            runtime_config_provider=runtime_config_provider,
        )
        if application.job_queue is None:
            raise RuntimeError("python-telegram-bot job queue dependency is unavailable")
        application.job_queue.run_repeating(
            queue_monitor_job,
            interval=settings.queue_poll_seconds,
            first=5,
            name="observer-queue-monitor",
        )
        application.job_queue.run_repeating(
            report_tick_job,
            interval=settings.report_tick_seconds,
            first=15,
            name="observer-report-tick",
        )
        application.job_queue.run_repeating(
            retention_job,
            interval=24 * 60 * 60,
            first=60,
            name="observer-message-retention",
        )

    async def post_shutdown(_application) -> None:
        await lm_client.close()
        await queue_client.close()
        await repository.close()

    builder = (
        ApplicationBuilder()
        .token(settings.token)
        .request(request)
        .get_updates_request(request)
        .concurrent_updates(True)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
    )
    if settings.telegram_base_url:
        builder = builder.base_url(settings.telegram_base_url)
    if settings.telegram_file_base_url:
        builder = builder.base_file_url(settings.telegram_file_base_url)
    application = builder.build()
    application.bot_data.update(
        settings=settings,
        repository=repository,
        queue_client=queue_client,
        lm_client=lm_client,
    )
    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CommandHandler("status", handle_status))
    application.add_handler(CommandHandler("report", handle_report))
    application.add_handler(
        MessageHandler(
            filters.UpdateType.MESSAGE & filters.ChatType.GROUPS,
            collect_authorized_group_message,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.UpdateType.EDITED_MESSAGE & filters.ChatType.GROUPS,
            collect_authorized_group_message,
        )
    )
    return application


def main() -> None:
    settings = ObserverSettings.from_env()
    setup_logging()
    logger.info(
        "Starting observer bot authorized_groups=%s admin_destinations=%s",
        len(settings.authorized_group_ids),
        len(settings.admin_chat_ids),
    )
    build_application(settings).run_polling(
        allowed_updates=["message", "edited_message"],
        poll_interval=settings.telegram_poll_interval,
        timeout=settings.telegram_poll_timeout,
        stop_signals=(signal.SIGINT, signal.SIGTERM, signal.SIGABRT),
    )


if __name__ == "__main__":
    main()
