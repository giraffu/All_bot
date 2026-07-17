import asyncio
import json
from unittest.mock import ANY, AsyncMock, Mock

import httpx
import pytest
from fastapi import HTTPException

from src.circuit_breaker import CircuitBreakerOpenException
from src.database.models import History
from src.database import core as db_core
from src.web_api.routers import tasks as tasks_router
from src.web_api.services import (
    task_runtime_api_service,
    task_stream_api_service,
    task_stream_service,
)


class _FakeResult:
    def __init__(self, *, single=None):
        self._single = single

    def scalars(self):
        return self

    def first(self):
        return self._single


class _FakeSession:
    def __init__(self, history=None):
        self._history = history

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, _stmt):
        return _FakeResult(single=self._history)


def _session_factory(history=None):
    def factory():
        return _FakeSession(history=history)

    return factory


class _FakeAuthSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePubSub:
    def __init__(
        self,
        messages=None,
        *,
        subscribe_exc=None,
        unsubscribe_exc=None,
        close_exc=None,
    ):
        self._messages = list(messages or [])
        self._subscribe_exc = subscribe_exc
        self._unsubscribe_exc = unsubscribe_exc
        self._close_exc = close_exc
        self.subscribed = []
        self.unsubscribed = []
        self.closed = False

    async def subscribe(self, channel):
        if self._subscribe_exc:
            raise self._subscribe_exc
        self.subscribed.append(channel)

    async def get_message(self, **_kwargs):
        if self._messages:
            next_message = self._messages.pop(0)
            if isinstance(next_message, BaseException):
                raise next_message
            return next_message
        return None

    async def unsubscribe(self, channel):
        if self._unsubscribe_exc:
            raise self._unsubscribe_exc
        self.unsubscribed.append(channel)

    async def close(self):
        if self._close_exc:
            raise self._close_exc
        self.closed = True


class _FakeRedis:
    def __init__(self, pubsub):
        self._pubsub = pubsub

    def pubsub(self):
        return self._pubsub


class _FakeStatusResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400 and self.status_code != 404:
            fake_response = type("Response", (), {"status_code": self.status_code})()
            raise httpx.HTTPStatusError(
                "unexpected status",
                request=None,
                response=fake_response,
            )

    def json(self):
        return self._payload


class _StatusCallRecorder(list):
    record_params = True


class _FakeAsyncClient:
    def __init__(self, responses, calls):
        self._responses = responses
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, timeout, params=None):
        if getattr(self._calls, "record_params", False):
            self._calls.append((url, timeout, params))
        else:
            self._calls.append((url, timeout))
        if not self._responses:
            raise AssertionError("unexpected extra status poll")
        next_response = self._responses.pop(0)
        if isinstance(next_response, BaseException):
            raise next_response
        return next_response


async def _collect_stream_events(response):
    events = []
    async for event in response.body_iterator:
        events.append(event)
    return events


@pytest.fixture(autouse=True)
def _clear_task_stream_status_cache(monkeypatch):
    monkeypatch.setattr(
        task_stream_service,
        "TASK_STREAM_STATUS_CACHE_TTL_SECONDS",
        0,
    )
    task_stream_service.clear_task_stream_status_cache()
    yield
    task_stream_service.clear_task_stream_status_cache()


def test_build_terminal_progress_payload_maps_backend_terminal_states():
    done_payload = task_stream_api_service.build_terminal_progress_payload(
        {"status": "done", "task_type": "image"},
        "task-1",
    )
    error_payload = task_stream_api_service.build_terminal_progress_payload(
        {"status": "error", "error_msg": "worker failed"},
        "task-1",
    )
    cancelled_payload = task_stream_api_service.build_terminal_progress_payload(
        {"status": "cancelled"},
        "task-1",
    )

    assert done_payload == {
        "status": "success",
        "task_id": "task-1",
        "task_type": "image",
    }
    assert error_payload == {
        "status": "failed",
        "task_id": "task-1",
        "error": "worker failed",
    }
    assert cancelled_payload == {
        "status": "cancelled",
        "task_id": "task-1",
        "message": "任务已取消",
    }


@pytest.mark.asyncio
async def test_build_not_found_progress_payload_returns_success_when_history_exists():
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="custom_video",
        output_file="bot-data/history/task-1/output.mp4",
    )

    payload = await task_stream_api_service.build_not_found_progress_payload(
        "task-1",
        123,
        _session_factory(history),
    )

    assert payload == {
        "status": "success",
        "task_id": "task-1",
        "task_type": "custom_video",
    }


@pytest.mark.asyncio
async def test_get_task_status_payload_returns_pending_type_queue_without_progress():
    captured_task_ids = []
    captured_kwargs = []

    async def fake_get_task_status(task_id, **kwargs):
        captured_task_ids.append(task_id)
        captured_kwargs.append(kwargs)
        return {
            "status": "pending",
            "queue_pos": 9,
            "queue_type_pos": 2,
            "progress": 0.4,
            "task_type": "txt2img",
        }

    payload = await task_runtime_api_service.get_task_status_payload_for_user(
        task_id="registry-1",
        user_id=123,
        session_factory=_session_factory(None),
        get_owned_active_task_func=AsyncMock(
            return_value={
                "user_id": 123,
                "backend_task_id": "backend-1",
            }
        ),
        get_task_status_func=fake_get_task_status,
    )

    assert captured_task_ids == ["backend-1"]
    assert captured_kwargs == [{"include_type_position": True}]
    assert payload == {
        "status": "pending",
        "task_id": "registry-1",
        "task_type": "txt2img",
        "media_type": "image",
        "queue_pos": 2,
    }
    assert "progress" not in payload


@pytest.mark.asyncio
async def test_get_task_status_payload_falls_back_to_global_queue_when_type_queue_missing():
    async def fake_get_task_status(_task_id, **kwargs):
        assert kwargs == {"include_type_position": True}
        return {
            "status": "pending",
            "queue_pos": 4,
            "progress": 0.4,
            "task_type": "txt2img",
        }

    payload = await task_runtime_api_service.get_task_status_payload_for_user(
        task_id="registry-1",
        user_id=123,
        session_factory=_session_factory(None),
        get_owned_active_task_func=AsyncMock(
            return_value={
                "user_id": 123,
                "backend_task_id": "backend-1",
            }
        ),
        get_task_status_func=fake_get_task_status,
    )

    assert payload["queue_pos"] == 4


@pytest.mark.asyncio
async def test_get_task_status_payload_running_drops_queue_and_progress():
    payload = await task_runtime_api_service.get_task_status_payload_for_user(
        task_id="registry-1",
        user_id=123,
        session_factory=_session_factory(None),
        get_owned_active_task_func=AsyncMock(
            return_value={
                "user_id": 123,
                "backend_task_id": "backend-1",
            }
        ),
        get_task_status_func=AsyncMock(
            return_value={
                "status": "running",
                "queue_pos": 1,
                "progress": 0.65,
                "task_type": "custom_video",
            }
        ),
    )

    assert payload == {
        "status": "running",
        "task_id": "registry-1",
        "task_type": "custom_video",
        "media_type": "video",
    }
    assert "progress" not in payload
    assert "queue_pos" not in payload


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "central_error",
    [
        CircuitBreakerOpenException("Circuit is open"),
        httpx.ReadTimeout("", request=httpx.Request("GET", "http://central/status")),
    ],
)
async def test_get_task_status_payload_degrades_active_task_when_central_unavailable(
    central_error,
):
    payload = await task_runtime_api_service.get_task_status_payload_for_user(
        task_id="registry-1",
        user_id=123,
        session_factory=_session_factory(None),
        get_owned_active_task_func=AsyncMock(
            return_value={
                "user_id": 123,
                "backend_task_id": "backend-1",
                "task_type": "custom_video",
            }
        ),
        get_task_status_func=AsyncMock(side_effect=central_error),
    )

    assert payload == {
        "status": "running",
        "task_id": "registry-1",
        "task_type": "custom_video",
        "media_type": "video",
    }


@pytest.mark.asyncio
async def test_get_task_status_payload_prefers_history_during_central_outage():
    history = History(
        id=11,
        user_id=123,
        task_id="registry-1",
        type="custom_video",
        output_file="bot-data/history/registry-1/output.mp4",
    )

    payload = await task_runtime_api_service.get_task_status_payload_for_user(
        task_id="registry-1",
        user_id=123,
        session_factory=_session_factory(history),
        get_owned_active_task_func=AsyncMock(
            return_value={
                "user_id": 123,
                "backend_task_id": "backend-1",
                "task_type": "custom_video",
            }
        ),
        get_task_status_func=AsyncMock(
            side_effect=CircuitBreakerOpenException("Circuit is open")
        ),
    )

    assert payload == {
        "status": "success",
        "task_id": "registry-1",
        "task_type": "custom_video",
        "media_type": "video",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("backend_status", "expected"),
    [
        ("done", {"status": "success", "task_id": "registry-1"}),
        (
            "error",
            {
                "status": "failed",
                "task_id": "registry-1",
                "error": "worker failed",
            },
        ),
        (
            "cancelled",
            {
                "status": "cancelled",
                "task_id": "registry-1",
                "message": "用户已取消",
            },
        ),
    ],
)
async def test_get_task_status_payload_maps_terminal_states(
    backend_status,
    expected,
):
    payload = await task_runtime_api_service.get_task_status_payload_for_user(
        task_id="registry-1",
        user_id=123,
        session_factory=_session_factory(None),
        get_owned_active_task_func=AsyncMock(
            return_value={
                "user_id": 123,
                "backend_task_id": "backend-1",
            }
        ),
        get_task_status_func=AsyncMock(
            return_value={
                "status": backend_status,
                "error_msg": "worker failed",
                "message": "用户已取消",
            }
        ),
    )

    assert payload == expected
    assert "progress" not in payload


@pytest.mark.asyncio
async def test_get_task_status_payload_returns_success_when_only_history_exists():
    history = History(
        id=11,
        user_id=123,
        task_id="registry-1",
        type="custom_video",
        output_file="bot-data/history/registry-1/output.mp4",
    )

    payload = await task_runtime_api_service.get_task_status_payload_for_user(
        task_id="registry-1",
        user_id=123,
        session_factory=_session_factory(history),
        get_owned_active_task_func=AsyncMock(return_value=None),
        get_task_status_func=AsyncMock(side_effect=AssertionError("should not fetch")),
    )

    assert payload == {
        "status": "success",
        "task_id": "registry-1",
        "task_type": "custom_video",
        "media_type": "video",
    }


@pytest.mark.asyncio
async def test_build_not_found_progress_payload_returns_failed_when_history_missing():
    payload = await task_stream_api_service.build_not_found_progress_payload(
        "task-1",
        123,
        _session_factory(None),
    )

    assert payload == {
        "status": "failed",
        "task_id": "task-1",
        "error": "任务不存在或无权限",
    }


@pytest.mark.asyncio
async def test_build_task_stream_response_payload_rejects_unowned_task(monkeypatch):
    dependencies = task_stream_api_service.TaskStreamResponseDependencies(
        get_owned_active_task_func=AsyncMock(return_value=None),
        get_user_history_record_func=AsyncMock(return_value=None),
        build_not_found_progress_payload_func=(
            task_stream_api_service.build_not_found_progress_payload
        ),
        build_terminal_progress_payload_func=(
            task_stream_api_service.build_terminal_progress_payload
        ),
        build_task_status_stream_response_func=(
            task_stream_api_service.build_task_status_stream_response
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        await task_stream_api_service.build_task_stream_response_payload(
            task_id="task-1",
            user_id=123,
            session_factory=_session_factory(None),
            redis=_FakeRedis(_FakePubSub()),
            api_base="http://127.0.0.1:8003",
            httpx_async_client_factory=lambda: _FakeAsyncClient([], []),
            logger=tasks_router.logger,
            dependencies=dependencies,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_task_status_stream_routes_to_service(monkeypatch):
    expected = object()
    service_mock = AsyncMock(return_value=expected)
    monkeypatch.setattr(
        tasks_router,
        "build_task_status_stream_response_for_user",
        service_mock,
    )

    response = await tasks_router.task_status_stream(
        "task-1",
        type("User", (), {"id": 123})(),
    )

    assert response is expected
    service_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_build_task_status_stream_response_for_user_uses_default_runtime_dependencies(
    monkeypatch,
):
    expected = object()
    redis = _FakeRedis(_FakePubSub())
    service_mock = AsyncMock(return_value=expected)

    monkeypatch.setattr(db_core, "AsyncSessionLocal", _FakeAuthSession)
    monkeypatch.setattr(task_runtime_api_service, "AsyncSessionLocal", _FakeAuthSession)
    monkeypatch.setattr(task_runtime_api_service.redis_client, "redis", redis)
    monkeypatch.setattr(
        task_runtime_api_service,
        "build_task_stream_response_payload",
        service_mock,
    )

    response = await task_runtime_api_service.build_task_status_stream_response_for_user(
        task_id="task-1",
        user_id=123,
        logger_override=tasks_router.logger,
    )

    assert response is expected
    service_mock.assert_awaited_once_with(
        task_id="task-1",
        user_id=123,
        session_factory=_FakeAuthSession,
        redis=redis,
        api_base=task_runtime_api_service.API_BASE,
        httpx_async_client_factory=httpx.AsyncClient,
        logger=tasks_router.logger,
    )


@pytest.mark.asyncio
async def test_build_task_stream_response_payload_uses_backend_task_id_for_runtime_stream():
    expected = object()
    service_mock = Mock(return_value=expected)
    dependencies = task_stream_api_service.TaskStreamResponseDependencies(
        get_owned_active_task_func=AsyncMock(
            return_value={
                "task_id": "task-1",
                "user_id": 123,
                "backend_task_id": "backend-1",
            }
        ),
        get_user_history_record_func=AsyncMock(return_value=None),
        build_not_found_progress_payload_func=(
            task_stream_api_service.build_not_found_progress_payload
        ),
        build_terminal_progress_payload_func=(
            task_stream_api_service.build_terminal_progress_payload
        ),
        build_task_status_stream_response_func=service_mock,
    )

    response = await task_stream_api_service.build_task_stream_response_payload(
        task_id="task-1",
        user_id=123,
        session_factory=_session_factory(None),
        redis=_FakeRedis(_FakePubSub()),
        api_base="http://127.0.0.1:8003",
        httpx_async_client_factory=lambda: _FakeAsyncClient([], []),
        logger=tasks_router.logger,
        dependencies=dependencies,
    )

    assert response is expected
    service_mock.assert_called_once_with(
        task_id="task-1",
        runtime_task_id="backend-1",
        user_id=123,
        session_factory=ANY,
        redis=ANY,
        api_base="http://127.0.0.1:8003",
        httpx_async_client_factory=ANY,
        logger=tasks_router.logger,
        build_not_found_progress_payload=ANY,
        build_terminal_progress_payload=ANY,
    )


@pytest.mark.asyncio
async def test_task_status_stream_emits_history_success_without_status_poll_when_history_only():
    status_calls = []
    pubsub = _FakePubSub()
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="custom_video",
        output_file="bot-data/history/task-1/output.mp4",
    )

    dependencies = task_stream_api_service.TaskStreamResponseDependencies(
        get_owned_active_task_func=AsyncMock(return_value=None),
        get_user_history_record_func=AsyncMock(return_value=history),
        build_not_found_progress_payload_func=(
            task_stream_api_service.build_not_found_progress_payload
        ),
        build_terminal_progress_payload_func=(
            task_stream_api_service.build_terminal_progress_payload
        ),
        build_task_status_stream_response_func=(
            task_stream_api_service.build_task_status_stream_response
        ),
    )

    response = await task_stream_api_service.build_task_stream_response_payload(
        task_id="task-1",
        user_id=123,
        session_factory=_session_factory(history),
        redis=_FakeRedis(pubsub),
        api_base="http://127.0.0.1:8003",
        httpx_async_client_factory=lambda: _FakeAsyncClient([], status_calls),
        logger=tasks_router.logger,
        dependencies=dependencies,
    )
    events = await _collect_stream_events(response)

    assert len(events) == 2
    assert events[0] == {
        "event": "connected",
        "data": json.dumps({"status": "listening", "task_id": "task-1"}),
    }
    assert events[1]["event"] == "progress"
    assert json.loads(events[1]["data"]) == {
        "status": "success",
        "task_id": "task-1",
        "task_type": "custom_video",
    }
    assert status_calls == []
    assert pubsub.subscribed == ["comfy:task_events:task-1"]
    assert pubsub.unsubscribed == ["comfy:task_events:task-1"]
    assert pubsub.closed is True


@pytest.mark.asyncio
async def test_fetch_task_status_full_uses_short_shared_cache(monkeypatch):
    status_calls = _StatusCallRecorder()
    status_responses = [
        _FakeStatusResponse(200, {"status": "pending", "queue_pos": 3})
    ]
    monkeypatch.setattr(
        task_stream_service,
        "TASK_STREAM_STATUS_CACHE_TTL_SECONDS",
        2.0,
    )

    first = await task_stream_service._fetch_task_status_full(
        task_id="backend-1",
        api_base="http://127.0.0.1:8003",
        httpx_async_client_factory=lambda: _FakeAsyncClient(
            status_responses,
            status_calls,
        ),
        logger=tasks_router.logger,
    )
    second = await task_stream_service._fetch_task_status_full(
        task_id="backend-1",
        api_base="http://127.0.0.1:8003",
        httpx_async_client_factory=lambda: _FakeAsyncClient([], status_calls),
        logger=tasks_router.logger,
    )

    assert first == {"status": "pending", "queue_pos": 3}
    assert second == {"status": "pending", "queue_pos": 3}
    assert status_calls == [
        (
            "http://127.0.0.1:8003/status/backend-1",
            2.0,
            {"include_type_position": "true"},
        )
    ]


@pytest.mark.asyncio
async def test_fetch_task_status_full_prunes_old_shared_cache(monkeypatch):
    status_calls = []
    monkeypatch.setattr(
        task_stream_service,
        "TASK_STREAM_STATUS_CACHE_TTL_SECONDS",
        30.0,
    )
    monkeypatch.setattr(
        task_stream_service,
        "TASK_STREAM_STATUS_CACHE_MAX_ENTRIES",
        1,
    )

    await task_stream_service._fetch_task_status_full(
        task_id="backend-1",
        api_base="http://127.0.0.1:8003",
        httpx_async_client_factory=lambda: _FakeAsyncClient(
            [_FakeStatusResponse(200, {"status": "pending"})],
            status_calls,
        ),
        logger=tasks_router.logger,
    )
    await task_stream_service._fetch_task_status_full(
        task_id="backend-2",
        api_base="http://127.0.0.1:8003",
        httpx_async_client_factory=lambda: _FakeAsyncClient(
            [_FakeStatusResponse(200, {"status": "running"})],
            status_calls,
        ),
        logger=tasks_router.logger,
    )
    await task_stream_service._fetch_task_status_full(
        task_id="backend-1",
        api_base="http://127.0.0.1:8003",
        httpx_async_client_factory=lambda: _FakeAsyncClient(
            [_FakeStatusResponse(200, {"status": "done"})],
            status_calls,
        ),
        logger=tasks_router.logger,
    )

    assert len(task_stream_service._task_stream_status_cache) == 1
    assert status_calls == [
        ("http://127.0.0.1:8003/status/backend-1", 2.0),
        ("http://127.0.0.1:8003/status/backend-2", 2.0),
        ("http://127.0.0.1:8003/status/backend-1", 2.0),
    ]


def test_task_stream_status_poll_interval_backs_off_to_configured_cap(monkeypatch):
    monkeypatch.setattr(
        task_stream_service,
        "TASK_STREAM_PENDING_STATUS_POLL_INITIAL_SECONDS",
        5.0,
    )
    monkeypatch.setattr(
        task_stream_service,
        "TASK_STREAM_PENDING_STATUS_POLL_MAX_SECONDS",
        20.0,
    )
    monkeypatch.setattr(
        task_stream_service,
        "TASK_STREAM_STATUS_POLL_BACKOFF_MULTIPLIER",
        2.0,
    )

    first_backoff = task_stream_service._next_task_stream_status_poll_interval(
        current_interval=5.0,
        is_running=False,
        status_changed=False,
    )
    second_backoff = task_stream_service._next_task_stream_status_poll_interval(
        current_interval=first_backoff,
        is_running=False,
        status_changed=False,
    )
    capped_backoff = task_stream_service._next_task_stream_status_poll_interval(
        current_interval=second_backoff,
        is_running=False,
        status_changed=False,
    )
    reset_interval = task_stream_service._next_task_stream_status_poll_interval(
        current_interval=capped_backoff,
        is_running=False,
        status_changed=True,
    )

    assert first_backoff == 10.0
    assert second_backoff == 20.0
    assert capped_backoff == 20.0
    assert reset_interval == 5.0


def test_task_stream_status_poll_signature_tracks_type_queue_position():
    base = task_stream_service._build_task_stream_status_poll_signature(
        {"status": "pending", "queue_pos": 9, "queue_type_pos": 3, "debug": "ignored"}
    )
    same = task_stream_service._build_task_stream_status_poll_signature(
        {"status": "pending", "queue_pos": 9, "queue_type_pos": 3, "debug": "changed"}
    )
    changed = task_stream_service._build_task_stream_status_poll_signature(
        {"status": "pending", "queue_pos": 9, "queue_type_pos": 2, "debug": "ignored"}
    )

    assert same == base
    assert changed != base
    assert base[:3] == ("pending", 9, 3)


@pytest.mark.asyncio
async def test_task_status_stream_emits_success_once_and_stops_when_initial_status_is_not_found_with_history(
    monkeypatch,
):
    status_calls = []
    status_responses = [_FakeStatusResponse(404)]
    pubsub = _FakePubSub()
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="custom_video",
        output_file="bot-data/history/task-1/output.mp4",
    )

    async def fake_get_user_history_record(_task_id, _user_id, _session_factory):
        return history

    dependencies = task_stream_api_service.TaskStreamResponseDependencies(
        get_owned_active_task_func=AsyncMock(
            return_value={"task_id": "task-1", "user_id": 123}
        ),
        get_user_history_record_func=fake_get_user_history_record,
        build_not_found_progress_payload_func=(
            task_stream_api_service.build_not_found_progress_payload
        ),
        build_terminal_progress_payload_func=(
            task_stream_api_service.build_terminal_progress_payload
        ),
        build_task_status_stream_response_func=(
            task_stream_api_service.build_task_status_stream_response
        ),
    )

    response = await task_stream_api_service.build_task_stream_response_payload(
        task_id="task-1",
        user_id=123,
        session_factory=_session_factory(history),
        redis=_FakeRedis(pubsub),
        api_base="http://127.0.0.1:8003",
        httpx_async_client_factory=lambda: _FakeAsyncClient(status_responses, status_calls),
        logger=tasks_router.logger,
        dependencies=dependencies,
    )
    events = await _collect_stream_events(response)

    assert len(events) == 2
    assert events[0] == {
        "event": "connected",
        "data": json.dumps({"status": "listening", "task_id": "task-1"}),
    }
    assert events[1]["event"] == "progress"
    assert json.loads(events[1]["data"]) == {
        "status": "success",
        "task_id": "task-1",
        "task_type": "custom_video",
    }
    assert status_calls == [("http://127.0.0.1:8003/status/task-1", 2.0)]
    assert pubsub.subscribed == ["comfy:task_events:task-1"]
    assert pubsub.unsubscribed == ["comfy:task_events:task-1"]
    assert pubsub.closed is True


@pytest.mark.asyncio
async def test_task_status_stream_uses_runtime_task_id_for_status_poll_and_pubsub():
    status_calls = []
    status_responses = [_FakeStatusResponse(200, {"status": "done", "task_type": "txt2img"})]
    pubsub = _FakePubSub()

    response = task_stream_api_service.build_task_status_stream_response(
        task_id="task-1",
        runtime_task_id="backend-1",
        user_id=123,
        session_factory=_session_factory(None),
        redis=_FakeRedis(pubsub),
        api_base="http://127.0.0.1:8003",
        httpx_async_client_factory=lambda: _FakeAsyncClient(status_responses, status_calls),
        logger=tasks_router.logger,
        build_not_found_progress_payload=(
            task_stream_api_service.build_not_found_progress_payload
        ),
        build_terminal_progress_payload=(
            task_stream_api_service.build_terminal_progress_payload
        ),
    )
    events = await _collect_stream_events(response)

    assert status_calls == [("http://127.0.0.1:8003/status/backend-1", 2.0)]
    assert pubsub.subscribed == ["comfy:task_events:backend-1"]
    assert pubsub.unsubscribed == ["comfy:task_events:backend-1"]
    assert pubsub.closed is True
    assert json.loads(events[1]["data"]) == {
        "status": "success",
        "task_id": "task-1",
        "task_type": "txt2img",
    }


@pytest.mark.asyncio
async def test_task_status_stream_stops_after_pubsub_success_alias():
    status_calls = []
    status_responses = [_FakeStatusResponse(200, {"status": "pending"})]
    pubsub = _FakePubSub(
        messages=[
            {"data": json.dumps({"status": "success", "task_type": "txt2img"})},
            RuntimeError("stream continued after terminal alias"),
        ]
    )

    response = task_stream_api_service.build_task_status_stream_response(
        task_id="task-1",
        runtime_task_id=None,
        user_id=123,
        session_factory=_session_factory(None),
        redis=_FakeRedis(pubsub),
        api_base="http://127.0.0.1:8003",
        httpx_async_client_factory=lambda: _FakeAsyncClient(status_responses, status_calls),
        logger=tasks_router.logger,
        build_not_found_progress_payload=(
            task_stream_api_service.build_not_found_progress_payload
        ),
        build_terminal_progress_payload=(
            task_stream_api_service.build_terminal_progress_payload
        ),
    )
    events = await _collect_stream_events(response)

    assert len(events) == 2
    assert events[0] == {
        "event": "connected",
        "data": json.dumps({"status": "listening", "task_id": "task-1"}),
    }
    assert json.loads(events[1]["data"]) == {
        "status": "success",
        "task_id": "task-1",
        "task_type": "txt2img",
    }
    assert status_calls == [("http://127.0.0.1:8003/status/task-1", 2.0)]
    assert pubsub.unsubscribed == ["comfy:task_events:task-1"]
    assert pubsub.closed is True


@pytest.mark.asyncio
async def test_task_status_stream_polls_terminal_status_after_running_without_pubsub_event():
    status_calls = []
    status_responses = [
        _FakeStatusResponse(200, {"status": "running"}),
        _FakeStatusResponse(200, {"status": "error", "error_msg": "heartbeat lost"}),
    ]
    pubsub = _FakePubSub(
        messages=[
            None,
            RuntimeError("stream should stop after terminal status poll"),
        ]
    )

    response = task_stream_api_service.build_task_status_stream_response(
        task_id="task-1",
        runtime_task_id=None,
        user_id=123,
        session_factory=_session_factory(None),
        redis=_FakeRedis(pubsub),
        api_base="http://127.0.0.1:8003",
        httpx_async_client_factory=lambda: _FakeAsyncClient(status_responses, status_calls),
        logger=tasks_router.logger,
        build_not_found_progress_payload=(
            task_stream_api_service.build_not_found_progress_payload
        ),
        build_terminal_progress_payload=(
            task_stream_api_service.build_terminal_progress_payload
        ),
    )
    events = await _collect_stream_events(response)

    assert len(events) == 2
    assert json.loads(events[1]["data"]) == {
        "status": "failed",
        "task_id": "task-1",
        "error": "heartbeat lost",
    }
    assert status_calls == [
        ("http://127.0.0.1:8003/status/task-1", 2.0),
        ("http://127.0.0.1:8003/status/task-1", 2.0),
    ]
    assert pubsub.unsubscribed == ["comfy:task_events:task-1"]
    assert pubsub.closed is True


@pytest.mark.asyncio
async def test_task_status_stream_falls_back_to_status_poll_when_pubsub_disconnects():
    status_calls = []
    status_responses = [
        _FakeStatusResponse(200, {"status": "pending"}),
        _FakeStatusResponse(200, {"status": "done", "task_type": "txt2img"}),
    ]
    pubsub = _FakePubSub(messages=[ConnectionResetError("connection lost")])

    response = task_stream_api_service.build_task_status_stream_response(
        task_id="task-1",
        runtime_task_id="backend-1",
        user_id=123,
        session_factory=_session_factory(None),
        redis=_FakeRedis(pubsub),
        api_base="http://127.0.0.1:8003",
        httpx_async_client_factory=lambda: _FakeAsyncClient(status_responses, status_calls),
        logger=tasks_router.logger,
        build_not_found_progress_payload=(
            task_stream_api_service.build_not_found_progress_payload
        ),
        build_terminal_progress_payload=(
            task_stream_api_service.build_terminal_progress_payload
        ),
    )
    events = await _collect_stream_events(response)

    assert [event["event"] for event in events] == ["connected", "progress"]
    assert json.loads(events[1]["data"]) == {
        "status": "success",
        "task_id": "task-1",
        "task_type": "txt2img",
    }
    assert status_calls == [
        ("http://127.0.0.1:8003/status/backend-1", 2.0),
        ("http://127.0.0.1:8003/status/backend-1", 2.0),
    ]
    assert pubsub.subscribed == ["comfy:task_events:backend-1"]
    assert pubsub.unsubscribed == ["comfy:task_events:backend-1"]
    assert pubsub.closed is True


@pytest.mark.asyncio
async def test_task_status_stream_uses_status_poll_when_pubsub_subscribe_fails():
    status_calls = []
    status_responses = [
        _FakeStatusResponse(200, {"status": "pending"}),
        _FakeStatusResponse(200, {"status": "done", "task_type": "txt2img"}),
    ]
    pubsub = _FakePubSub(subscribe_exc=ConnectionResetError("subscribe lost"))

    response = task_stream_api_service.build_task_status_stream_response(
        task_id="task-1",
        runtime_task_id="backend-1",
        user_id=123,
        session_factory=_session_factory(None),
        redis=_FakeRedis(pubsub),
        api_base="http://127.0.0.1:8003",
        httpx_async_client_factory=lambda: _FakeAsyncClient(status_responses, status_calls),
        logger=tasks_router.logger,
        build_not_found_progress_payload=(
            task_stream_api_service.build_not_found_progress_payload
        ),
        build_terminal_progress_payload=(
            task_stream_api_service.build_terminal_progress_payload
        ),
    )
    events = await _collect_stream_events(response)

    assert [event["event"] for event in events] == ["connected", "progress"]
    assert json.loads(events[1]["data"]) == {
        "status": "success",
        "task_id": "task-1",
        "task_type": "txt2img",
    }
    assert status_calls == [
        ("http://127.0.0.1:8003/status/backend-1", 2.0),
        ("http://127.0.0.1:8003/status/backend-1", 2.0),
    ]
    assert pubsub.subscribed == []


@pytest.mark.asyncio
async def test_task_status_stream_ignores_pubsub_cleanup_failures():
    status_calls = []
    status_responses = [_FakeStatusResponse(200, {"status": "pending"})]
    pubsub = _FakePubSub(
        messages=[
            {"data": json.dumps({"status": "success", "task_type": "txt2img"})},
        ],
        unsubscribe_exc=ConnectionResetError("unsubscribe lost"),
        close_exc=ConnectionResetError("close lost"),
    )

    response = task_stream_api_service.build_task_status_stream_response(
        task_id="task-1",
        runtime_task_id="backend-1",
        user_id=123,
        session_factory=_session_factory(None),
        redis=_FakeRedis(pubsub),
        api_base="http://127.0.0.1:8003",
        httpx_async_client_factory=lambda: _FakeAsyncClient(status_responses, status_calls),
        logger=tasks_router.logger,
        build_not_found_progress_payload=(
            task_stream_api_service.build_not_found_progress_payload
        ),
        build_terminal_progress_payload=(
            task_stream_api_service.build_terminal_progress_payload
        ),
    )
    events = await _collect_stream_events(response)

    assert len(events) == 2
    assert json.loads(events[1]["data"]) == {
        "status": "success",
        "task_id": "task-1",
        "task_type": "txt2img",
    }
    assert pubsub.closed is False


@pytest.mark.asyncio
async def test_task_status_stream_emits_failed_once_and_stops_when_queue_poll_later_returns_not_found_without_history(
    monkeypatch,
):
    status_calls = []
    status_responses = [
        _FakeStatusResponse(200, {"status": "pending", "queue_pos": 3}),
        _FakeStatusResponse(404),
    ]
    pubsub = _FakePubSub(messages=[None])

    async def fake_get_user_history_record(_task_id, _user_id, _session_factory):
        return None

    dependencies = task_stream_api_service.TaskStreamResponseDependencies(
        get_owned_active_task_func=AsyncMock(
            return_value={"task_id": "task-1", "user_id": 123}
        ),
        get_user_history_record_func=fake_get_user_history_record,
        build_not_found_progress_payload_func=(
            task_stream_api_service.build_not_found_progress_payload
        ),
        build_terminal_progress_payload_func=(
            task_stream_api_service.build_terminal_progress_payload
        ),
        build_task_status_stream_response_func=(
            task_stream_api_service.build_task_status_stream_response
        ),
    )

    response = await task_stream_api_service.build_task_stream_response_payload(
        task_id="task-1",
        user_id=123,
        session_factory=_session_factory(None),
        redis=_FakeRedis(pubsub),
        api_base="http://127.0.0.1:8003",
        httpx_async_client_factory=lambda: _FakeAsyncClient(status_responses, status_calls),
        logger=tasks_router.logger,
        dependencies=dependencies,
    )
    events = await _collect_stream_events(response)

    assert len(events) == 2
    assert events[0] == {
        "event": "connected",
        "data": json.dumps({"status": "listening", "task_id": "task-1"}),
    }
    assert events[1]["event"] == "progress"
    assert json.loads(events[1]["data"]) == {
        "status": "failed",
        "task_id": "task-1",
        "error": "任务不存在或无权限",
    }
    assert status_calls == [
        ("http://127.0.0.1:8003/status/task-1", 2.0),
        ("http://127.0.0.1:8003/status/task-1", 2.0),
    ]
    assert pubsub.subscribed == ["comfy:task_events:task-1"]
    assert pubsub.unsubscribed == ["comfy:task_events:task-1"]
    assert pubsub.closed is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_responses", "case_name"),
    [
        ([_FakeStatusResponse(500)], "5xx"),
        ([httpx.ReadTimeout("backend timeout")], "timeout"),
    ],
)
async def test_task_status_stream_does_not_emit_not_found_terminal_event_for_transient_backend_failures(
    monkeypatch,
    status_responses,
    case_name,
):
    status_calls = []
    pubsub = _FakePubSub(messages=[asyncio.CancelledError()])
    history_lookup_calls = []

    async def fake_get_user_history_record(_task_id, _user_id, _session_factory):
        history_lookup_calls.append((_task_id, _user_id))
        return None

    dependencies = task_stream_api_service.TaskStreamResponseDependencies(
        get_owned_active_task_func=AsyncMock(
            return_value={"task_id": "task-1", "user_id": 123}
        ),
        get_user_history_record_func=fake_get_user_history_record,
        build_not_found_progress_payload_func=(
            task_stream_api_service.build_not_found_progress_payload
        ),
        build_terminal_progress_payload_func=(
            task_stream_api_service.build_terminal_progress_payload
        ),
        build_task_status_stream_response_func=(
            task_stream_api_service.build_task_status_stream_response
        ),
    )

    response = await task_stream_api_service.build_task_stream_response_payload(
        task_id="task-1",
        user_id=123,
        session_factory=_session_factory(None),
        redis=_FakeRedis(pubsub),
        api_base="http://127.0.0.1:8003",
        httpx_async_client_factory=lambda: _FakeAsyncClient(list(status_responses), status_calls),
        logger=tasks_router.logger,
        dependencies=dependencies,
    )
    events = await _collect_stream_events(response)

    assert case_name in {"5xx", "timeout"}
    assert events == [
        {
            "event": "connected",
            "data": json.dumps({"status": "listening", "task_id": "task-1"}),
        }
    ]
    assert status_calls == [("http://127.0.0.1:8003/status/task-1", 2.0)]
    assert history_lookup_calls == [("task-1", 123)]
    assert pubsub.subscribed == ["comfy:task_events:task-1"]
    assert pubsub.unsubscribed == ["comfy:task_events:task-1"]
    assert pubsub.closed is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_responses", "case_name"),
    [
        (
            [
                _FakeStatusResponse(
                    200,
                    {"status": "pending", "queue_pos": 3, "queue_type_pos": 1},
                ),
                _FakeStatusResponse(500),
            ],
            "5xx",
        ),
        (
            [
                _FakeStatusResponse(
                    200,
                    {"status": "pending", "queue_pos": 3, "queue_type_pos": 1},
                ),
                httpx.ReadTimeout("backend timeout"),
            ],
            "timeout",
        ),
    ],
)
async def test_task_status_stream_does_not_emit_terminal_event_when_queue_poll_hits_transient_backend_failures(
    monkeypatch,
    status_responses,
    case_name,
):
    status_calls = []
    pubsub = _FakePubSub(messages=[None, asyncio.CancelledError()])
    history_lookup_calls = []

    async def fake_get_user_history_record(_task_id, _user_id, _session_factory):
        history_lookup_calls.append((_task_id, _user_id))
        return None

    dependencies = task_stream_api_service.TaskStreamResponseDependencies(
        get_owned_active_task_func=AsyncMock(
            return_value={"task_id": "task-1", "user_id": 123}
        ),
        get_user_history_record_func=fake_get_user_history_record,
        build_not_found_progress_payload_func=(
            task_stream_api_service.build_not_found_progress_payload
        ),
        build_terminal_progress_payload_func=(
            task_stream_api_service.build_terminal_progress_payload
        ),
        build_task_status_stream_response_func=(
            task_stream_api_service.build_task_status_stream_response
        ),
    )

    response = await task_stream_api_service.build_task_stream_response_payload(
        task_id="task-1",
        user_id=123,
        session_factory=_session_factory(None),
        redis=_FakeRedis(pubsub),
        api_base="http://127.0.0.1:8003",
        httpx_async_client_factory=lambda: _FakeAsyncClient(list(status_responses), status_calls),
        logger=tasks_router.logger,
        dependencies=dependencies,
    )
    events = await _collect_stream_events(response)

    assert case_name in {"5xx", "timeout"}
    assert events == [
        {
            "event": "connected",
            "data": json.dumps({"status": "listening", "task_id": "task-1"}),
        },
        {
            "event": "progress",
            "data": json.dumps({"status": "pending", "queue_pos": 1}),
        },
    ]
    assert all(
        json.loads(event["data"]).get("status") not in {"success", "failed"}
        for event in events
        if event["event"] == "progress"
    )
    assert status_calls == [
        ("http://127.0.0.1:8003/status/task-1", 2.0),
        ("http://127.0.0.1:8003/status/task-1", 2.0),
    ]
    assert history_lookup_calls == [("task-1", 123)]
    assert pubsub.subscribed == ["comfy:task_events:task-1"]
    assert pubsub.unsubscribed == ["comfy:task_events:task-1"]
    assert pubsub.closed is True
