from __future__ import annotations

from typing import TYPE_CHECKING, Tuple

from src.services.user_persistence_service import (
    get_or_create_user_by_google as _get_or_create_user_by_google_impl,
    get_or_create_user_by_telegram as _get_or_create_user_by_telegram_impl,
)

if TYPE_CHECKING:
    from src.database.models import User


async def get_or_create_user_by_telegram(
    tg_id: int, username: str = None, full_name: str = None, language_code: str = None
) -> Tuple[User, bool]:
    """稳定 facade：core 不直接处理数据库细节。"""
    return await _get_or_create_user_by_telegram_impl(
        tg_id=tg_id,
        username=username,
        full_name=full_name,
        language_code=language_code,
    )


async def get_or_create_user_by_google(
    google_id: str, email: str, full_name: str = None
) -> User:
    """稳定 facade：core 不直接处理数据库细节。"""
    return await _get_or_create_user_by_google_impl(
        google_id=google_id,
        email=email,
        full_name=full_name,
    )
