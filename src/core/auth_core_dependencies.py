from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from src.auth_core_repository_bindings import get_default_auth_core_repository_bindings
from src.core.billing_core import get_default_billing_core_providers
from src.core.user_core import get_or_create_user_by_telegram


@dataclass(frozen=True)
class AuthCoreDependencies:
    redis: Any
    session_factory: Callable[[], Any]
    get_or_create_user_by_telegram_func: Callable[..., Awaitable[tuple[Any, bool]]]
    get_user_detailed_stats_func: Callable[[int], Awaitable[dict]]
    check_web_access_func: Callable[[int], Awaitable[bool]]
    is_integrity_error_func: Callable[[Exception], bool]
    get_user_by_username_func: Callable[..., Awaitable[Any]] | None = None
    get_user_by_id_func: Callable[..., Awaitable[Any]] | None = None

def build_auth_core_dependencies(
    *,
    redis=None,
    session_factory=None,
    get_or_create_user_by_telegram_func=None,
    get_user_by_username_func=None,
    get_user_by_id_func=None,
    permission_service=None,
) -> AuthCoreDependencies:
    """受控 composition root：集中装配 auth_core 运行时依赖。"""
    if permission_service is None:
        permission_service_impl = (
            get_default_billing_core_providers().get_permission_service_func()
        )
    else:
        permission_service_impl = permission_service

    if redis is None:
        redis = get_default_billing_core_providers().get_redis_client_func().redis

    repository_bindings = get_default_auth_core_repository_bindings()

    if session_factory is None:
        session_factory = repository_bindings.session_factory

    if get_user_by_username_func is None:
        get_user_by_username_func = repository_bindings.get_user_by_username_func

    if get_user_by_id_func is None:
        get_user_by_id_func = repository_bindings.get_user_by_id_func

    if get_or_create_user_by_telegram_func is None:
        get_or_create_user_by_telegram_func = get_or_create_user_by_telegram

    return AuthCoreDependencies(
        redis=redis,
        session_factory=session_factory,
        get_or_create_user_by_telegram_func=get_or_create_user_by_telegram_func,
        get_user_detailed_stats_func=permission_service_impl.get_user_detailed_stats,
        check_web_access_func=permission_service_impl.check_web_access,
        get_user_by_username_func=get_user_by_username_func,
        get_user_by_id_func=get_user_by_id_func,
        is_integrity_error_func=repository_bindings.is_integrity_error_func,
    )
