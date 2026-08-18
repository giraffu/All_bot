from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

from sqlalchemy.exc import IntegrityError


@dataclass(frozen=True)
class AuthCoreRepositoryBindings:
    session_factory: object
    get_user_by_username_func: object
    get_user_by_id_func: object
    is_integrity_error_func: Callable[[Exception], bool]


@lru_cache(maxsize=1)
def get_default_auth_core_repository_bindings() -> AuthCoreRepositoryBindings:
    from src.database.core import AsyncSessionLocal
    from src.services.auth_user_repository import get_user_by_id, get_user_by_username

    return AuthCoreRepositoryBindings(
        session_factory=AsyncSessionLocal,
        get_user_by_username_func=get_user_by_username,
        get_user_by_id_func=get_user_by_id,
        is_integrity_error_func=lambda error: isinstance(error, IntegrityError),
    )
