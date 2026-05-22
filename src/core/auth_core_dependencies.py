from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from src.core.user_core import get_or_create_user_by_telegram
from src.database.core import AsyncSessionLocal
from src.services.permission_service import permission_service
from src.services.redis_client import redis_client


@dataclass(frozen=True)
class AuthCoreDependencies:
    redis: Any
    session_factory: Callable[[], Any]
    get_or_create_user_by_telegram_func: Callable[..., Awaitable[tuple[Any, bool]]]
    get_user_detailed_stats_func: Callable[[int], Awaitable[dict]]
    check_web_access_func: Callable[[int], Awaitable[bool]]


def build_auth_core_dependencies() -> AuthCoreDependencies:
    return AuthCoreDependencies(
        redis=redis_client.redis,
        session_factory=AsyncSessionLocal,
        get_or_create_user_by_telegram_func=get_or_create_user_by_telegram,
        get_user_detailed_stats_func=permission_service.get_user_detailed_stats,
        check_web_access_func=permission_service.check_web_access,
    )
