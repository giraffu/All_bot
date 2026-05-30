from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class UserCoreBindings:
    get_or_create_user_by_telegram_func: object
    get_or_create_user_by_google_func: object


@lru_cache(maxsize=1)
def get_default_user_core_bindings() -> UserCoreBindings:
    from src.services.user_persistence_service import (
        get_or_create_user_by_google,
        get_or_create_user_by_telegram,
    )

    return UserCoreBindings(
        get_or_create_user_by_telegram_func=get_or_create_user_by_telegram,
        get_or_create_user_by_google_func=get_or_create_user_by_google,
    )
