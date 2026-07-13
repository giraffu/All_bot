import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, Request

from app.dependencies import get_redis
from app.main_bootstrap import (
    build_request_state_getter,
    check_zombie_tasks_loop,
    get_minio_client,
    lifespan,
    redis_transient_exception_handler,
    verify_token,
)


def test_verify_token_accepts_matching_credential():
    credentials = SimpleNamespace(credentials="secret")
    assert verify_token(credentials=credentials, expected_token="secret") == "secret"


def test_verify_token_rejects_invalid_credential():
    credentials = SimpleNamespace(credentials="wrong")
    with pytest.raises(HTTPException) as exc_info:
        verify_token(credentials=credentials, expected_token="secret")
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid token"


def test_build_request_state_getter_marks_request_as_fastapi_request():
    dependency = build_request_state_getter(attr_name="minio_client")
    annotations = dependency.__annotations__
    assert annotations["request"] is Request


@pytest.mark.asyncio
async def test_check_zombie_tasks_loop_runs_single_iteration_then_stops():
    redis = SimpleNamespace(close=AsyncMock())
    queue_manager = SimpleNamespace(check_zombie_tasks=AsyncMock())
    logger = MagicMock()

    def queue_manager_cls(passed_redis):
        assert passed_redis is redis
        return queue_manager

    async def stop_sleep(_seconds):
        raise RuntimeError("stop-loop")

    with pytest.raises(RuntimeError, match="stop-loop"):
        await check_zombie_tasks_loop(
            settings=SimpleNamespace(redis_url="redis://example"),
            queue_manager_cls=queue_manager_cls,
            logger=logger,
            sleep_func=stop_sleep,
            redis_from_url=lambda url: redis,
        )

    queue_manager.check_zombie_tasks.assert_awaited_once()
    redis.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifespan_sets_minio_client_on_app_state():
    app = SimpleNamespace(state=SimpleNamespace())
    logger = MagicMock()
    zombie_task = None
    redis = SimpleNamespace(close=AsyncMock())

    async def noop_loop():
        await asyncio.Event().wait()

    async with lifespan(
        fastapi_app=app,
        settings=SimpleNamespace(
            minio_endpoint="minio:9000",
            minio_access_key="key",
            minio_secret_key="secret",
            minio_secure=False,
            redis_url="redis://example",
        ),
        logger=logger,
        check_zombie_tasks_loop_func=noop_loop,
        redis_from_url=lambda url: redis,
    ):
        assert hasattr(app.state, "minio_client")
        assert app.state.redis is redis
        zombie_task = app.state.zombie_tasks_loop_task
        assert zombie_task is not None
        assert zombie_task.done() is False
        assert get_minio_client(SimpleNamespace(app=app)) is app.state.minio_client
        assert app.state.minio_client._region_map["comfyui-temp"] == "us-east-1"
        assert app.state.minio_client._region_map["bot-data"] == "us-east-1"
    assert zombie_task.cancelled() is True
    redis.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_redis_reuses_app_state_client():
    redis = SimpleNamespace(close=AsyncMock())
    app = SimpleNamespace(state=SimpleNamespace(redis=redis))
    dependency = get_redis(SimpleNamespace(app=app))

    assert await dependency.__anext__() is redis
    with pytest.raises(StopAsyncIteration):
        await dependency.__anext__()
    redis.close.assert_not_called()


@pytest.mark.asyncio
async def test_redis_transient_exception_handler_returns_retryable_503():
    response = await redis_transient_exception_handler(
        SimpleNamespace(url="/comfy_img2img"),
        ConnectionResetError("Connection lost"),
    )

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "2"
    assert json.loads(response.body) == {
        "detail": "Central Redis temporarily unavailable; please retry shortly"
    }
