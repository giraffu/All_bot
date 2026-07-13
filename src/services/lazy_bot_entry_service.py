from __future__ import annotations

import os
import re
from urllib.parse import urlparse


_BOT_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{5,32}$")
_DISABLED_VALUES = frozenset({"0", "false", "no", "off"})


def is_lazy_bot_entry_enabled() -> bool:
    """Return whether the main Bot may expose the QQCC lazy Bot entry."""
    value = os.getenv("QQCC_LAZY_BOT_ENABLED")
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

    configured_url = (os.getenv("QQCC_LAZY_BOT_URL") or "").strip()
    if configured_url:
        return configured_url if _is_supported_telegram_url(configured_url) else None

    configured_username = (os.getenv("QQCC_LAZY_BOT_USERNAME") or "").strip()
    if not configured_username:
        return None

    username = configured_username.removeprefix("@")
    if not _BOT_USERNAME_PATTERN.fullmatch(username):
        return None
    return f"https://t.me/{username}"
