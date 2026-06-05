from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from src.auth_core_repository_bindings import get_default_auth_core_repository_bindings

DUMMY_PASSWORD_HASH = "$2b$12$xGzN6R9UuP.BvA8aH3/1/.P7f1k4uX8q9Pz7vR5n3yO1l6t9uV2.O"


@dataclass(slots=True)
class PasswordLoginAttempt:
    user: object | None
    is_valid: bool


async def authenticate_password_credentials(
    *,
    session,
    username: str,
    password: str,
    verify_password_func: Callable[[str, str], Awaitable[bool]],
    get_user_by_username_func: Callable[..., Awaitable[object | None]] | None = None,
) -> PasswordLoginAttempt:
    if get_user_by_username_func is None:
        get_user_by_username_func = (
            get_default_auth_core_repository_bindings().get_user_by_username_func
        )

    user = await get_user_by_username_func(session, username)

    hashed_password = (
        user.hashed_password if user and user.hashed_password else DUMMY_PASSWORD_HASH
    )
    is_valid = await verify_password_func(password, hashed_password)

    return PasswordLoginAttempt(
        user=user,
        is_valid=bool(user and user.hashed_password and is_valid),
    )
