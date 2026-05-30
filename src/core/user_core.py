from __future__ import annotations

from typing import TYPE_CHECKING, Tuple

from src.user_core_bindings import get_default_user_core_bindings

if TYPE_CHECKING:
    from src.database.models import User


async def get_or_create_user_by_telegram(
    tg_id: int, username: str = None, full_name: str = None, language_code: str = None
) -> Tuple[User, bool]:
    """稳定 facade：core 不直接处理数据库细节。"""
    bindings = get_default_user_core_bindings()
    return await bindings.get_or_create_user_by_telegram_func(
        tg_id=tg_id,
        username=username,
        full_name=full_name,
        language_code=language_code,
    )


async def get_or_create_user_by_google(
    google_id: str, email: str, full_name: str = None
) -> User:
    """稳定 facade：core 不直接处理数据库细节。"""
    bindings = get_default_user_core_bindings()
    return await bindings.get_or_create_user_by_google_func(
        google_id=google_id,
        email=email,
        full_name=full_name,
    )
