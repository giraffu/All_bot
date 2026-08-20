from __future__ import annotations

import asyncio
import copy
import logging
from typing import Any, Awaitable, Callable, TypeVar

from src.services.qqcc_config_service import (
    load_runtime_qqcc_config,
    normalize_qqcc_config,
)

QQCC_BOT_CLIENT_TYPE = "bot:qqcc"
QQCC_PRIVATE_BOT_CLIENT_TYPE_PREFIX = "bot:qqcc-private:"
QQCC_INTERACTION_IO_TIMEOUT_SECONDS = 15.0
LoadQQCCConfigFunc = Callable[[], Awaitable[dict[str, Any]]]
InteractionResult = TypeVar("InteractionResult")


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


async def run_qqcc_interaction_io(
    awaitable: Awaitable[InteractionResult],
    *,
    operation: str,
    logger: logging.Logger,
) -> InteractionResult | None:
    """Bound non-critical QQCC Telegram I/O so one update cannot stall polling."""
    try:
        return await asyncio.wait_for(
            awaitable,
            timeout=QQCC_INTERACTION_IO_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "QQCC interaction I/O timed out operation=%s timeout_seconds=%.1f",
            operation,
            QQCC_INTERACTION_IO_TIMEOUT_SECONDS,
        )
        return None


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
        config = await load_config_func()
        if is_private_qqcc_bot_context(context):
            config = copy.deepcopy(config)
            if "ai_video_scenes" in config:
                config["ai_video_scenes"] = [
                    scene
                    for scene in config.get("ai_video_scenes", [])
                    if str(scene.get("mode") or "i2v") != "ref2v"
                ]
        return config
    except Exception:
        if logger is not None:
            logger.exception("Failed to load QQCC lazy bot config; using defaults.")
        if is_private_qqcc_bot_context(context):
            raise
        return normalize_qqcc_config(None)
