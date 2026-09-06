from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


GetOrCreateTelegramUser = Callable[..., Awaitable[tuple[Any, bool]]]


async def resolve_internal_user_id_for_telegram(
    telegram_user_id: int,
    username: str | None = None,
    full_name: str | None = None,
    language_code: str | None = None,
    *,
    get_or_create_user_func: GetOrCreateTelegramUser | None = None,
) -> int:
    """Resolve an external Telegram identity to the canonical internal user ID."""

    if get_or_create_user_func is None:
        from src.core.user_core import get_or_create_user_by_telegram

        get_or_create_user_func = get_or_create_user_by_telegram

    internal_user, _ = await get_or_create_user_func(
        telegram_user_id,
        username,
        full_name,
        language_code,
    )
    return int(internal_user.id)
