from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from src.core.user_core import get_or_create_user_by_telegram
from src.database.core import AsyncSessionLocal


@dataclass(frozen=True)
class AuthCoreDependencies:
    redis: Any
    session_factory: Callable[[], Any]
    get_or_create_user_by_telegram_func: Callable[..., Awaitable[tuple[Any, bool]]]
    get_user_detailed_stats_func: Callable[[int], Awaitable[dict]]
    check_web_access_func: Callable[[int], Awaitable[bool]]

def build_auth_core_dependencies(
    *,
    redis=None,
    session_factory=None,
    get_or_create_user_by_telegram_func=None,
    permission_service=None,
) -> AuthCoreDependencies:
    """受控 composition root：集中装配 auth_core 运行时依赖。"""
    if permission_service is None:
        from src.services.permission_service import (
            permission_service as permission_service_impl,
        )
    else:
        permission_service_impl = permission_service

    if redis is None:
        from src.services.redis_client import redis_client as redis_client_impl

        redis = redis_client_impl.redis

    if session_factory is None:
        session_factory = AsyncSessionLocal

    if get_or_create_user_by_telegram_func is None:
        get_or_create_user_by_telegram_func = get_or_create_user_by_telegram

    return AuthCoreDependencies(
        redis=redis,
        session_factory=session_factory,
        get_or_create_user_by_telegram_func=get_or_create_user_by_telegram_func,
        get_user_detailed_stats_func=permission_service_impl.get_user_detailed_stats,
        check_web_access_func=permission_service_impl.check_web_access,
    )
