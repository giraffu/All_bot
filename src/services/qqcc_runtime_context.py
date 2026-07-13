from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from src.services.qqcc_config_service import (
    load_runtime_qqcc_config,
    normalize_qqcc_config,
)

QQCC_BOT_CLIENT_TYPE = "bot:qqcc"
QQCC_PRIVATE_BOT_CLIENT_TYPE_PREFIX = "bot:qqcc-private:"
LoadQQCCConfigFunc = Callable[[], Awaitable[dict[str, Any]]]


def get_qqcc_bot_data(context: Any) -> dict[str, Any]:
    bot_data = getattr(context, "bot_data", None)
    if bot_data is None:
        application = getattr(context, "application", None)
        bot_data = getattr(application, "bot_data", None)
    return bot_data or {}


def get_private_qqcc_bot_id(context: Any) -> int | None:
    bot_data = get_qqcc_bot_data(context)
    try:
        private_bot_id = int(bot_data.get("private_qqcc_bot_id") or 0)
    except (TypeError, ValueError):
        return None
    client_type = str(bot_data.get("bot_client_type") or "")
    if private_bot_id > 0 and client_type == (
        f"{QQCC_PRIVATE_BOT_CLIENT_TYPE_PREFIX}{private_bot_id}"
    ):
        return private_bot_id
    return None


def is_private_qqcc_bot_context(context: Any) -> bool:
    return get_private_qqcc_bot_id(context) is not None


def is_qqcc_bot_context(context: Any) -> bool:
    bot_data = get_qqcc_bot_data(context)
    return bool(
        bot_data.get("bot_client_type") == QQCC_BOT_CLIENT_TYPE
        or is_private_qqcc_bot_context(context)
    )


async def load_qqcc_config_for_context(
    context: Any,
    *,
    logger: logging.Logger | None = None,
    load_config_func: LoadQQCCConfigFunc = load_runtime_qqcc_config,
) -> dict[str, Any] | None:
    if not is_qqcc_bot_context(context):
        return None
    bot_data = get_qqcc_bot_data(context)
    context_loader = bot_data.get("qqcc_config_loader")
    if callable(context_loader):
        load_config_func = context_loader
    try:
        return await load_config_func()
    except Exception:
        if logger is not None:
            logger.exception("Failed to load QQCC lazy bot config; using defaults.")
        if is_private_qqcc_bot_context(context):
            raise
        return normalize_qqcc_config(None)
