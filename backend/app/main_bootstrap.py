import asyncio
from contextlib import asynccontextmanager

from fastapi import HTTPException
from minio import Minio
from redis.asyncio import Redis


def init_minio_client(*, settings, logger):
    try:
        minio_client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        logger.info(f"MinIO client initialized: {settings.minio_endpoint}")
        return minio_client
    except Exception as exc:
        logger.error(f"Failed to init MinIO: {exc}")
        return None


def get_minio_client(request):
    return getattr(request.app.state, "minio_client", None)


async def check_zombie_tasks_loop(
    *,
    settings,
    queue_manager_cls,
    logger,
    sleep_func=asyncio.sleep,
    redis_from_url=Redis.from_url,
):
    while True:
        try:
            redis = redis_from_url(settings.redis_url)
            queue_manager = queue_manager_cls(redis)
            await queue_manager.check_zombie_tasks()
            await redis.close()
        except Exception as exc:
            logger.error(f"Error in check_zombie_tasks_loop: {exc}")
        await sleep_func(60)


def verify_token(*, credentials, expected_token: str):
    if credentials.credentials != expected_token:
        raise HTTPException(status_code=401, detail="Invalid token")
    return credentials.credentials


@asynccontextmanager
async def lifespan(
    *,
    fastapi_app,
    settings,
    logger,
    check_zombie_tasks_loop_func,
    validate_workflows_func=None,
):
    if validate_workflows_func is not None:
        validate_workflows_func(settings.workflows_dir)
    asyncio.create_task(check_zombie_tasks_loop_func())
    fastapi_app.state.minio_client = init_minio_client(settings=settings, logger=logger)
    yield
