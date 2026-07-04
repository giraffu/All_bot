from collections.abc import Callable
from typing import Any

import redis.asyncio as redis
from redis.asyncio import Redis


DEFAULT_REDIS_CONNECTION_KWARGS: dict[str, Any] = {
    "socket_connect_timeout": 5,
    "socket_timeout": 5,
    "health_check_interval": 15,
    "socket_keepalive": True,
    "retry_on_timeout": True,
}


def build_redis_client(
    url: str,
    *,
    decode_responses: bool = False,
    from_url_func: Callable[..., Redis] = redis.from_url,
    **overrides: Any,
) -> Redis:
    kwargs = {
        **DEFAULT_REDIS_CONNECTION_KWARGS,
        "decode_responses": decode_responses,
        **overrides,
    }
    return from_url_func(url, **kwargs)
