import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from src.services.redis_connection import build_redis_client
from src.services.storage_minio_client import (
    build_configured_bucket_names,
    build_minio_client,
)


REDIS_TRANSIENT_HTTP_EXCEPTIONS = (
    RedisConnectionError,
    RedisTimeoutError,
    ConnectionError,
    ConnectionResetError,
    TimeoutError,
)
REDIS_TRANSIENT_RETRY_AFTER_SECONDS = "2"
logger = logging.getLogger(__name__)


def init_minio_client(*, settings, logger):
    try:
        minio_client = build_minio_client(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
            bucket_names=build_configured_bucket_names(),
        )
        logger.info(f"MinIO client initialized: {settings.minio_endpoint}")
        return minio_client
    except Exception as exc:
        logger.error(f"Failed to init MinIO: {exc}")
        return None


def get_minio_client(request: Request):
    return getattr(request.app.state, "minio_client", None)


def build_request_state_getter(*, attr_name: str, default=None):
    def _get_request_state_value(request: Request):
        return getattr(request.app.state, attr_name, default)

    return _get_request_state_value


async def check_zombie_tasks_loop(
    *,
    settings,
    queue_manager_cls,
    logger,
    sleep_func=asyncio.sleep,
    redis_from_url=build_redis_client,
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


def build_zombie_tasks_loop_runner(
    *,
    settings,
    queue_manager_cls,
    logger,
):
    async def _runner():
        await check_zombie_tasks_loop(
            settings=settings,
            queue_manager_cls=queue_manager_cls,
            logger=logger,
        )

    return _runner


def verify_token(*, credentials, expected_token: str):
    if credentials.credentials != expected_token:
        raise HTTPException(status_code=401, detail="Invalid token")
    return credentials.credentials


def build_verify_token_dependency(*, expected_token: str, security):
    async def _verify_token(
        credentials: HTTPAuthorizationCredentials = Depends(security),
    ):
        return verify_token(credentials=credentials, expected_token=expected_token)

    return _verify_token


@asynccontextmanager
async def lifespan(
    *,
    fastapi_app,
    settings,
    logger,
    check_zombie_tasks_loop_func,
    redis_from_url=build_redis_client,
):
    zombie_task = None
    shared_redis = None
    zombie_task = asyncio.create_task(
        check_zombie_tasks_loop_func(),
        name="backend-check-zombie-tasks",
    )
    fastapi_app.state.zombie_tasks_loop_task = zombie_task
    shared_redis = redis_from_url(settings.redis_url)
    fastapi_app.state.redis = shared_redis
    fastapi_app.state.minio_client = init_minio_client(settings=settings, logger=logger)
    try:
        yield
    finally:
        if shared_redis is not None:
            await shared_redis.close()
        if zombie_task is not None:
            zombie_task.cancel()
            try:
                await zombie_task
            except asyncio.CancelledError:
                pass


async def redis_transient_exception_handler(request: Request, exc: Exception):
    logger.warning(
        "Central Redis transient failure on %s: %s",
        getattr(request.url, "path", request.url),
        exc,
    )
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Central Redis temporarily unavailable; please retry shortly"
        },
        headers={"Retry-After": REDIS_TRANSIENT_RETRY_AFTER_SECONDS},
    )


def register_redis_transient_exception_handlers(fastapi_app):
    for exc_type in REDIS_TRANSIENT_HTTP_EXCEPTIONS:
        fastapi_app.add_exception_handler(exc_type, redis_transient_exception_handler)
