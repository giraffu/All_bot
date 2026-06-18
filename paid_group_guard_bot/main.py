from __future__ import annotations

import logging
import signal

from sqlalchemy import text
from telegram.ext import ApplicationBuilder
from telegram.request import HTTPXRequest

from paid_group_guard_bot.config import PaidGroupBotSettings
from paid_group_guard_bot.handlers import build_chat_join_request_handler
from src.database.core import engine
from src.logger import setup_logging

logger = logging.getLogger(__name__)


async def _post_init(_application) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("Paid group guard bot database connectivity verified")


async def _post_shutdown(_application) -> None:
    await engine.dispose()
    logger.info("Paid group guard bot database engine disposed")


def build_application(settings: PaidGroupBotSettings):
    request = HTTPXRequest(
        proxy=None,
        connect_timeout=settings.connect_timeout,
        read_timeout=settings.read_timeout,
        write_timeout=settings.write_timeout,
        connection_pool_size=settings.pool_size,
    )

    builder = (
        ApplicationBuilder()
        .token(settings.token)
        .request(request)
        .get_updates_request(request)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .concurrent_updates(True)
    )

    if settings.base_url:
        builder = builder.base_url(settings.base_url)
    if settings.base_file_url:
        builder = builder.base_file_url(settings.base_file_url)

    application = builder.build()
    application.add_handler(build_chat_join_request_handler(settings))
    return application


def main() -> None:
    settings = PaidGroupBotSettings.from_env()
    setup_logging(settings.log_file)
    logger.info(
        "Starting paid group guard bot target_chat_id=%s decline_unqualified=%s "
        "dry_run=%s",
        settings.target_chat_id,
        settings.decline_unqualified,
        settings.dry_run,
    )

    application = build_application(settings)
    application.run_polling(
        allowed_updates=["chat_join_request"],
        poll_interval=settings.poll_interval,
        timeout=settings.poll_timeout,
        stop_signals=(signal.SIGINT, signal.SIGTERM, signal.SIGABRT),
    )


if __name__ == "__main__":
    main()

