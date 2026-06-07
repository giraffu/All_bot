from fastapi import Depends, Request
from redis.asyncio import Redis

from app.config import settings
from app.queue_manager import QueueManager


async def get_redis(request: Request):
    shared_redis = getattr(request.app.state, "redis", None)
    if shared_redis is not None:
        yield shared_redis
        return

    redis = Redis.from_url(settings.redis_url)
    try:
        yield redis
    finally:
        await redis.close()


async def get_queue_manager(redis: Redis = Depends(get_redis)):
    return QueueManager(redis)
