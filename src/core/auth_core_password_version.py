def build_password_version_blacklist_key(
    *, user_id: int, password_version: int
) -> str:
    return f"allbot:auth:blacklist:{user_id}:{password_version}"


async def blacklist_password_version(
    *,
    redis,
    user_id: int,
    password_version: int,
    ttl_seconds: int = 604800,
) -> None:
    blacklist_key = build_password_version_blacklist_key(
        user_id=user_id,
        password_version=password_version,
    )
    await redis.setex(blacklist_key, ttl_seconds, "1")


async def is_password_version_blacklisted(
    *,
    redis,
    user_id: int,
    password_version: int,
) -> bool:
    blacklist_key = build_password_version_blacklist_key(
        user_id=user_id,
        password_version=password_version,
    )
    return bool(await redis.get(blacklist_key))
