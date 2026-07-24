from __future__ import annotations

import os
import re
from urllib.parse import urlparse


_BOT_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{5,32}$")
_DISABLED_VALUES = frozenset({"0", "false", "no", "off"})
_MAIN_BOT_PREFIX = "MAIN_BOT_LAZY_BOT_"
_LEGACY_PREFIX = "QQCC_LAZY_BOT_"


def _config_prefix() -> str:
    if any(
        key in os.environ
        for key in (
            f"{_MAIN_BOT_PREFIX}ENABLED",
            f"{_MAIN_BOT_PREFIX}URL",
            f"{_MAIN_BOT_PREFIX}USERNAME",
        )
    ):
        return _MAIN_BOT_PREFIX
    return _LEGACY_PREFIX


def _entry_value(name: str) -> str:
    return (os.getenv(f"{_config_prefix()}{name}") or "").strip()


def is_lazy_bot_entry_enabled() -> bool:
    """Return whether the main Bot may expose the QQCC lazy Bot entry."""
    key = f"{_config_prefix()}ENABLED"
    value = os.getenv(key)
    return value is None or value.strip().lower() not in _DISABLED_VALUES


def _is_supported_telegram_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"}:
        return parsed.netloc.lower() in {"t.me", "telegram.me"} and bool(
            parsed.path.strip("/")
        )
    if parsed.scheme == "tg":
        return parsed.netloc == "resolve" and bool(parsed.query)
    return False


def resolve_lazy_bot_url() -> str | None:
    if not is_lazy_bot_entry_enabled():
        return None

    configured_url = _entry_value("URL")
    if configured_url:
        return configured_url if _is_supported_telegram_url(configured_url) else None

    configured_username = _entry_value("USERNAME")
    if not configured_username:
        return None

    username = configured_username.removeprefix("@")
    if not _BOT_USERNAME_PATTERN.fullmatch(username):
        return None
    return f"https://t.me/{username}"
