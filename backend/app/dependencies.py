from fastapi import Depends, Request
from redis.asyncio import Redis
from src.services.redis_connection import build_redis_client

from app.config import settings
from app.queue_manager import QueueManager


async def get_redis(request: Request):
    shared_redis = getattr(request.app.state, "redis", None)
    if shared_redis is not None:
        yield shared_redis
        return

    redis = build_redis_client(settings.redis_url)
    try:
        yield redis
    finally:
        await redis.close()


async def get_queue_manager(redis: Redis = Depends(get_redis)):
    return QueueManager(redis)


def get_minio_client(request: Request):
    return getattr(request.app.state, "minio_client", None)
