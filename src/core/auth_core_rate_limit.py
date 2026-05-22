def build_login_rate_limit_keys(*, client_ip: str, username: str) -> tuple[str, str]:
    return (
        f"allbot:ratelimit:login:ip:{client_ip}",
        f"allbot:ratelimit:login:user:{username.lower()}",
    )


def build_bind_rate_limit_keys(*, client_ip: str, user_id: int) -> tuple[str, str]:
    return (
        f"allbot:ratelimit:bind:ip:{client_ip}",
        f"allbot:ratelimit:bind:user:{user_id}",
    )


async def is_rate_limited(
    *,
    redis,
    ip_key: str,
    user_key: str,
    max_attempts: int,
    check_script: str,
) -> bool:
    is_locked = await redis.eval(check_script, 2, ip_key, user_key, max_attempts)
    return is_locked == 1


async def increment_rate_limit(
    *,
    redis,
    ip_key: str,
    user_key: str,
    expire_seconds: int,
    incr_script: str,
):
    await redis.eval(incr_script, 2, ip_key, user_key, expire_seconds)


async def clear_rate_limit(
    *,
    redis,
    ip_key: str,
    user_key: str,
):
    await redis.delete(ip_key, user_key)
