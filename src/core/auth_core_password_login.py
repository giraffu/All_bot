from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import select, text

from src.database.models import User

DUMMY_PASSWORD_HASH = "$2b$12$xGzN6R9UuP.BvA8aH3/1/.P7f1k4uX8q9Pz7vR5n3yO1l6t9uV2.O"


@dataclass(slots=True)
class PasswordLoginAttempt:
    user: User | None
    is_valid: bool


async def authenticate_password_credentials(
    *,
    session,
    username: str,
    password: str,
    verify_password_func: Callable[[str, str], Awaitable[bool]],
) -> PasswordLoginAttempt:
    stmt = (
        select(User)
        .where(text("lower(username) = :uname"))
        .params(uname=username.lower())
    )
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    hashed_password = (
        user.hashed_password if user and user.hashed_password else DUMMY_PASSWORD_HASH
    )
    is_valid = await verify_password_func(password, hashed_password)

    return PasswordLoginAttempt(
        user=user,
        is_valid=bool(user and user.hashed_password and is_valid),
    )
