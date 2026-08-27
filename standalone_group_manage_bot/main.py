from __future__ import annotations

import logging
import signal
from pathlib import Path

from telegram.ext import ApplicationBuilder
from telegram.request import HTTPXRequest

from paid_group_guard_bot.moderation_handlers import build_message_moderation_handler
from standalone_group_manage_bot.config import GroupManageBotSettings
from standalone_group_manage_bot.moderation import GroupManageConfigProvider
from src.log_redaction import install_log_redaction

logger = logging.getLogger(__name__)


def setup_logging(log_file: str) -> None:
    install_log_redaction()
    path = Path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(path, encoding="utf-8"), logging.StreamHandler()],
        force=True,
    )


def build_application(settings: GroupManageBotSettings):
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
        .concurrent_updates(True)
    )
    if settings.base_url:
        builder = builder.base_url(settings.base_url)
    if settings.base_file_url:
        builder = builder.base_file_url(settings.base_file_url)
    application = builder.build()
    application.add_handler(
        build_message_moderation_handler(
            settings,
            config_provider=GroupManageConfigProvider(settings.moderation_config_file),
        )
    )
    return application


def main() -> None:
    settings = GroupManageBotSettings.from_env()
    setup_logging(settings.log_file)
    logger.info("Starting group manage bot target_chat_id=%s", settings.target_chat_id)
    build_application(settings).run_polling(
        allowed_updates=["message"],
        poll_interval=settings.poll_interval,
        timeout=settings.poll_timeout,
        stop_signals=(signal.SIGINT, signal.SIGTERM, signal.SIGABRT),
    )


if __name__ == "__main__":
    main()
