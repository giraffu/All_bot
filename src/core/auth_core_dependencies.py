from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from src.core.user_core import get_or_create_user_by_telegram
from src.database.core import AsyncSessionLocal


class _CompatServiceProxy:
    def __init__(self, loader):
        self._loader = loader

    def __getattr__(self, name):
        return getattr(self._loader(), name)


def _load_permission_service():
    from src.services.permission_service import permission_service as permission_service_impl

    return permission_service_impl


def _load_redis_client():
    from src.services.redis_client import redis_client as redis_client_impl

    return redis_client_impl


permission_service = _CompatServiceProxy(_load_permission_service)
redis_client = _CompatServiceProxy(_load_redis_client)


@dataclass(frozen=True)
class AuthCoreDependencies:
    redis: Any
    session_factory: Callable[[], Any]
    get_or_create_user_by_telegram_func: Callable[..., Awaitable[tuple[Any, bool]]]
    get_user_detailed_stats_func: Callable[[int], Awaitable[dict]]
    check_web_access_func: Callable[[int], Awaitable[bool]]


def _get_auth_core_redis():
    return redis_client.redis


def _get_auth_core_permission_service():
    return permission_service


def _get_auth_core_session_factory():
    return AsyncSessionLocal


def _get_auth_core_get_or_create_user_by_telegram_func():
    return get_or_create_user_by_telegram


def build_auth_core_dependencies() -> AuthCoreDependencies:
    """受控 composition root：集中装配 auth_core 运行时依赖。"""
    permission_service_impl = _get_auth_core_permission_service()
    return AuthCoreDependencies(
        redis=_get_auth_core_redis(),
        session_factory=_get_auth_core_session_factory(),
        get_or_create_user_by_telegram_func=(
            _get_auth_core_get_or_create_user_by_telegram_func()
        ),
        get_user_detailed_stats_func=permission_service_impl.get_user_detailed_stats,
        check_web_access_func=permission_service_impl.check_web_access,
    )
