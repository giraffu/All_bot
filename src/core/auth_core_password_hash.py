import asyncio
import hashlib

import bcrypt


def verify_password_sync(plain_password: str, hashed_password: str) -> bool:
    pre_hashed = hashlib.sha256(plain_password.encode("utf-8")).hexdigest()
    return bcrypt.checkpw(pre_hashed.encode("utf-8"), hashed_password.encode("utf-8"))


async def verify_password(plain_password: str, hashed_password: str) -> bool:
    return await asyncio.to_thread(
        verify_password_sync,
        plain_password,
        hashed_password,
    )


def get_password_hash_sync(password: str) -> str:
    pre_hashed = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return bcrypt.hashpw(pre_hashed.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def get_password_hash(password: str) -> str:
    return await asyncio.to_thread(get_password_hash_sync, password)
