from collections.abc import Awaitable, Callable

from src.auth_core_repository_bindings import get_default_auth_core_repository_bindings


async def get_bindable_user(
    *,
    session,
    user_id: int,
    check_web_access_func: Callable[[int], Awaitable[bool]],
    user_not_found_error_factory: Callable[[], Exception],
    insufficient_permission_error_factory: Callable[[], Exception],
    get_user_by_id_func: Callable[..., Awaitable[object | None]] | None = None,
):
    if get_user_by_id_func is None:
        get_user_by_id_func = get_default_auth_core_repository_bindings().get_user_by_id_func

    user = await get_user_by_id_func(session, user_id)
    if not user:
        raise user_not_found_error_factory()

    if not await check_web_access_func(user.id):
        raise insufficient_permission_error_factory()

    return user


async def bind_password_to_user(
    *,
    session,
    user,
    username: str,
    password: str,
    get_password_hash_func: Callable[[str], Awaitable[str]],
) -> int:
    previous_password_version = user.password_version
    hashed_password = await get_password_hash_func(password)

    user.username = username
    user.hashed_password = hashed_password
    user.password_version += 1
    session.add(user)
    await session.flush()

    return previous_password_version
