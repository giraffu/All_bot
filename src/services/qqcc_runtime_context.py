from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from src.services.qqcc_config_service import (
    load_runtime_qqcc_config,
    normalize_qqcc_config,
)

QQCC_BOT_CLIENT_TYPE = "bot:qqcc"
LoadQQCCConfigFunc = Callable[[], Awaitable[dict[str, Any]]]


def is_qqcc_bot_context(context: Any) -> bool:
    bot_data = getattr(context, "bot_data", None)
    if bot_data is None:
        application = getattr(context, "application", None)
        bot_data = getattr(application, "bot_data", None)
    return bool(bot_data and bot_data.get("bot_client_type") == QQCC_BOT_CLIENT_TYPE)


async def load_qqcc_config_for_context(
    context: Any,
    *,
    logger: logging.Logger | None = None,
    load_config_func: LoadQQCCConfigFunc = load_runtime_qqcc_config,
) -> dict[str, Any] | None:
    if not is_qqcc_bot_context(context):
        return None
    try:
        return await load_config_func()
    except Exception:
        if logger is not None:
            logger.exception("Failed to load QQCC lazy bot config; using defaults.")
        return normalize_qqcc_config(None)
