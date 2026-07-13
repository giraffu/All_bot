from __future__ import annotations

import os
from urllib.parse import urlsplit

DEFAULT_PRIVATE_TELEGRAM_API_BASE_URL = "https://api.telegram.org"
DEFAULT_PRIVATE_TELEGRAM_FILE_BASE_URL = "https://api.telegram.org/file/bot"


class PrivateBotTelegramTransportError(ValueError):
    pass


def _trusted_hosts() -> set[str]:
    configured = os.getenv(
        "PRIVATE_QQCC_BOT_TELEGRAM_TRUSTED_HOSTS",
        "",
    )
    return {
        "api.telegram.org",
        *(value.strip().lower() for value in configured.split(",") if value.strip()),
    }


def _resolve_https_endpoint(*, env_name: str, default: str) -> str:
    raw = os.getenv(env_name, default).strip().rstrip("/") or default
    parsed = urlsplit(raw)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.hostname.lower() not in _trusted_hosts()
    ):
        raise PrivateBotTelegramTransportError(
            f"{env_name} must be an HTTPS endpoint on an explicitly trusted host"
        )
    return raw


def resolve_private_telegram_api_base_url() -> str:
    return _resolve_https_endpoint(
        env_name="PRIVATE_QQCC_BOT_TELEGRAM_API_BASE_URL",
        default=DEFAULT_PRIVATE_TELEGRAM_API_BASE_URL,
    )


def build_private_telegram_bot_base_url() -> str:
    return f"{resolve_private_telegram_api_base_url()}/bot"


def resolve_private_telegram_file_base_url() -> str:
    return _resolve_https_endpoint(
        env_name="PRIVATE_QQCC_BOT_TELEGRAM_FILE_BASE_URL",
        default=DEFAULT_PRIVATE_TELEGRAM_FILE_BASE_URL,
    )
