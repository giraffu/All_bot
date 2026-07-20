import logging
import os
import uuid
from urllib.parse import urlparse

import httpx
from asgi_correlation_id import correlation_id
from telegram import File, Poll, Update
from telegram.ext import ContextTypes
from telegram.request import HTTPXRequest

_ORIGINAL_DOWNLOAD_TO_DRIVE = File.download_to_drive
_ORIGINAL_POLL_DE_JSON = Poll.de_json
_PATCHES_INSTALLED = False


def resolve_telegram_api_base_url() -> str:
    value = os.getenv("TELEGRAM_API_BASE_URL", "").strip().rstrip("/")
    if not value:
        raise RuntimeError("TELEGRAM_API_BASE_URL is required")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("TELEGRAM_API_BASE_URL must be a valid http/https URL")
    return value


def resolve_telegram_file_base_url() -> str:
    value = os.getenv("TELEGRAM_FILE_BASE_URL", "").strip().rstrip("/")
    if not value:
        raise RuntimeError("TELEGRAM_FILE_BASE_URL is required")
    return value


def build_telegram_bot_base_url() -> str:
    return f"{resolve_telegram_api_base_url()}/bot"


def build_telegram_httpx_request(
    *,
    connect_timeout: float = 60.0,
    read_timeout: float = 120.0,
    write_timeout: float = 120.0,
    connection_pool_size: int = 500,
) -> HTTPXRequest:
    return HTTPXRequest(
        proxy=None,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        write_timeout=write_timeout,
        connection_pool_size=connection_pool_size,
    )


def install_telegram_runtime_patches(
    *,
    logger: logging.Logger | None = None,
) -> None:
    global _PATCHES_INSTALLED
    if _PATCHES_INSTALLED:
        return

    patch_logger = logger or logging.getLogger(__name__)

    async def custom_download_to_drive(
        self,
        custom_path=None,
        read_timeout=None,
        write_timeout=None,
        connect_timeout=None,
        pool_timeout=None,
    ):
        bot = self.get_bot()
        file_base_url = resolve_telegram_file_base_url()
        bot_base_file_url = str(bot.base_file_url or "").rstrip("/")
        if bot_base_file_url.startswith(file_base_url):
            raw_path = self.file_path
            if raw_path.startswith("http"):
                raw_path = urlparse(raw_path).path
            if not raw_path.startswith("/"):
                raw_path = "/" + raw_path
            url = f"{file_base_url}{raw_path}"

            patch_logger.info("Custom downloading Telegram file from: %s", url)
            async with httpx.AsyncClient(proxy=None) as client:
                response = await client.get(url, timeout=120.0)
                response.raise_for_status()
                with open(custom_path, "wb") as fh:
                    fh.write(response.content)
            return self

        return await _ORIGINAL_DOWNLOAD_TO_DRIVE(
            self,
            custom_path,
            read_timeout,
            write_timeout,
            connect_timeout,
            pool_timeout,
        )

    @classmethod
    def de_json_with_members_only_default(cls, data, bot=None):
        if isinstance(data, dict) and "members_only" not in data:
            data = dict(data)
            data["members_only"] = False
        return _ORIGINAL_POLL_DE_JSON(data, bot)

    File.download_to_drive = custom_download_to_drive
    Poll.de_json = de_json_with_members_only_default
    _PATCHES_INSTALLED = True


async def inject_bot_language_context(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    logger: logging.Logger | None = None,
    callback_log_label: str | None = None,
) -> str:
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
                    if logger is not None:
                        logger.warning("Failed to get user lang from Redis: %s", exc)

        if not lang and tg_user.language_code:
            native_lang = tg_user.language_code[:2].lower()
            if native_lang in {"zh", "en"}:
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

    if update.callback_query and logger is not None and callback_log_label:
        logger.info(f"{callback_log_label}: %s", update.callback_query.data)

    return lang
