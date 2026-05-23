import asyncio
import hashlib

import bcrypt


def verify_password_sync(plain_password: str, hashed_password: str) -> bool:
    pre_hashed = hashlib.sha256(plain_password.encode("utf-8")).hexdigest()
    return bcrypt.checkpw(pre_hashed.encode("utf-8"), hashed_password.encode("utf-8"))


async def verify_password(
    plain_password: str,
    hashed_password: str,
    *,
    verify_password_sync_func=None,
    to_thread_func=None,
) -> bool:
    if verify_password_sync_func is None:
        verify_password_sync_func = verify_password_sync
    if to_thread_func is None:
        to_thread_func = asyncio.to_thread

    return await to_thread_func(
        verify_password_sync_func,
        plain_password,
        hashed_password,
    )


def get_password_hash_sync(password: str) -> str:
    pre_hashed = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return bcrypt.hashpw(pre_hashed.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def get_password_hash(
    password: str,
    *,
    get_password_hash_sync_func=None,
    to_thread_func=None,
) -> str:
    if get_password_hash_sync_func is None:
        get_password_hash_sync_func = get_password_hash_sync
    if to_thread_func is None:
        to_thread_func = asyncio.to_thread

    return await to_thread_func(get_password_hash_sync_func, password)
