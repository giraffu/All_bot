import asyncio
import logging
import os
import signal
import uuid
from urllib.parse import urlparse

import httpx
from asgi_correlation_id import correlation_id
from telegram import File, Poll, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    TypeHandler,
    filters,
)
from telegram.request import HTTPXRequest

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
from src.services.recovery_service import recover_active_tasks
from src.services.qqcc_runtime_context import QQCC_BOT_CLIENT_TYPE
from src.task_core_provider_setup import ensure_task_core_service_providers_registered

logger = logging.getLogger("qqcc_bot.core")

_original_download_to_drive = File.download_to_drive
_original_poll_de_json = Poll.de_json


async def custom_download_to_drive(
    self,
    custom_path=None,
    read_timeout=None,
    write_timeout=None,
    connect_timeout=None,
    pool_timeout=None,
):
    bot = self.get_bot()
    if bot.base_file_url and "8082" in bot.base_file_url:
        raw_path = self.file_path
        if raw_path.startswith("http"):
            raw_path = urlparse(raw_path).path
        if not raw_path.startswith("/"):
            raw_path = "/" + raw_path
        file_base_url = os.getenv("TELEGRAM_FILE_BASE_URL", "http://69.63.220.115:8082")
        url = f"{file_base_url.rstrip('/')}{raw_path}"

        logger.info("QQCC custom downloading Telegram file from: %s", url)
        async with httpx.AsyncClient(proxy=None) as client:
            response = await client.get(url, timeout=120.0)
            response.raise_for_status()
            with open(custom_path, "wb") as f:
                f.write(response.content)
        return self
    return await _original_download_to_drive(
        self,
        custom_path,
        read_timeout,
        write_timeout,
        connect_timeout,
        pool_timeout,
    )


def patch_poll_members_only_default():
    @classmethod
    def de_json_with_members_only_default(cls, data, bot=None):
        if isinstance(data, dict) and "members_only" not in data:
            data = dict(data)
            data["members_only"] = False
        return _original_poll_de_json(data, bot)

    Poll.de_json = de_json_with_members_only_default


File.download_to_drive = custom_download_to_drive
patch_poll_members_only_default()


async def global_middleware(update: Update, context):
    trace_id = str(uuid.uuid4())
    correlation_id.set(trace_id)

    lang = None
    tg_user = update.effective_user
    if tg_user:
        lang = context.user_data.get("language_code") if context.user_data else None
        if not lang:
            from src.services.redis_client import redis_client

            if redis_client and redis_client.redis:
                try:
                    cached_lang = await redis_client.redis.get(
                        f"allbot:user_lang:tg:{tg_user.id}"
                    )
                    if cached_lang:
                        if isinstance(cached_lang, bytes):
                            cached_lang = cached_lang.decode("utf-8")
                        lang = cached_lang
                except Exception as exc:
                    logger.warning("Failed to get QQCC user lang from Redis: %s", exc)
        if not lang and tg_user.language_code:
            native_lang = tg_user.language_code[:2].lower()
            if native_lang in ["zh", "en"]:
                lang = native_lang
        if not lang:
            lang = "zh"
        if context.user_data is not None:
            context.user_data["language_code"] = lang
    else:
        lang = "zh"

    context.lang = lang
    from src.i18n.translator import I18nTranslator

    context.t = I18nTranslator(lang)

    if update.callback_query:
        logger.info("QQCC callback query: %s", update.callback_query.data)


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


def _build_request() -> HTTPXRequest:
    return HTTPXRequest(
        proxy=None,
        connect_timeout=60.0,
        read_timeout=120.0,
        write_timeout=120.0,
        connection_pool_size=500,
    )


def build_application(token: str):
    request = _build_request()
    api_base_url = os.getenv("TELEGRAM_API_BASE_URL", "http://69.63.220.115:8081")
    file_base_url = os.getenv("TELEGRAM_FILE_BASE_URL", "http://69.63.220.115:8082")
    app = (
        ApplicationBuilder()
        .token(token)
        .base_url(f"{api_base_url.rstrip('/')}/bot")
        .base_file_url(file_base_url.rstrip("/"))
        .request(request)
        .get_updates_request(request)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .concurrent_updates(True)
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
