import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from src.database.models import History
from src.database import core as db_core
from src.web_api.routers import tasks as tasks_router


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
    def __init__(self, messages=None):
        self._messages = list(messages or [])
        self.subscribed = []
        self.unsubscribed = []
        self.closed = False

    async def subscribe(self, channel):
        self.subscribed.append(channel)

    async def get_message(self, **_kwargs):
        if self._messages:
            next_message = self._messages.pop(0)
            if isinstance(next_message, BaseException):
                raise next_message
            return next_message
        return None

    async def unsubscribe(self, channel):
        self.unsubscribed.append(channel)

    async def close(self):
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
            response = type("Response", (), {"status_code": self.status_code})()
            raise tasks_router.httpx.HTTPStatusError(
                "unexpected status",
                request=None,
                response=response,
            )

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, responses, calls):
        self._responses = responses
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, timeout):
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


def test_build_terminal_progress_payload_maps_backend_terminal_states():
    done_payload = tasks_router._build_terminal_progress_payload(
        {"status": "done", "task_type": "image"},
        "task-1",
    )
    error_payload = tasks_router._build_terminal_progress_payload(
        {"status": "error", "error_msg": "worker failed"},
        "task-1",
    )
    cancelled_payload = tasks_router._build_terminal_progress_payload(
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
        "status": "failed",
        "task_id": "task-1",
        "error": "任务已取消",
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

    payload = await tasks_router._build_not_found_progress_payload(
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
async def test_build_not_found_progress_payload_returns_failed_when_history_missing():
    payload = await tasks_router._build_not_found_progress_payload(
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

    monkeypatch.setattr(db_core, "AsyncSessionLocal", lambda: _FakeAuthSession())
    monkeypatch.setattr(tasks_router.redis_client, "redis", _FakeRedis(pubsub))
    monkeypatch.setattr(
        tasks_router,
        "_get_owned_active_task",
        AsyncMock(return_value={"task_id": "task-1", "user_id": 123}),
    )
    monkeypatch.setattr(
        tasks_router.httpx,
        "AsyncClient",
        lambda: _FakeAsyncClient(status_responses, status_calls),
    )
    monkeypatch.setattr(
        tasks_router,
        "_get_user_history_record",
        fake_get_user_history_record,
    )

    response = await tasks_router.task_status_stream(
        "task-1", type("User", (), {"id": 123})()
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

    monkeypatch.setattr(db_core, "AsyncSessionLocal", lambda: _FakeAuthSession())
    monkeypatch.setattr(tasks_router.redis_client, "redis", _FakeRedis(pubsub))
    monkeypatch.setattr(
        tasks_router,
        "_get_owned_active_task",
        AsyncMock(return_value={"task_id": "task-1", "user_id": 123}),
    )
    monkeypatch.setattr(
        tasks_router.httpx,
        "AsyncClient",
        lambda: _FakeAsyncClient(status_responses, status_calls),
    )
    monkeypatch.setattr(
        tasks_router,
        "_get_user_history_record",
        fake_get_user_history_record,
    )

    response = await tasks_router.task_status_stream(
        "task-1", type("User", (), {"id": 123})()
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
        ([tasks_router.httpx.ReadTimeout("backend timeout")], "timeout"),
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

    monkeypatch.setattr(db_core, "AsyncSessionLocal", lambda: _FakeAuthSession())
    monkeypatch.setattr(tasks_router.redis_client, "redis", _FakeRedis(pubsub))
    monkeypatch.setattr(
        tasks_router,
        "_get_owned_active_task",
        AsyncMock(return_value={"task_id": "task-1", "user_id": 123}),
    )
    monkeypatch.setattr(
        tasks_router.httpx,
        "AsyncClient",
        lambda: _FakeAsyncClient(list(status_responses), status_calls),
    )
    monkeypatch.setattr(
        tasks_router,
        "_get_user_history_record",
        fake_get_user_history_record,
    )

    response = await tasks_router.task_status_stream(
        "task-1", type("User", (), {"id": 123})()
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
                _FakeStatusResponse(200, {"status": "pending", "queue_pos": 3}),
                _FakeStatusResponse(500),
            ],
            "5xx",
        ),
        (
            [
                _FakeStatusResponse(200, {"status": "pending", "queue_pos": 3}),
                tasks_router.httpx.ReadTimeout("backend timeout"),
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

    monkeypatch.setattr(db_core, "AsyncSessionLocal", lambda: _FakeAuthSession())
    monkeypatch.setattr(tasks_router.redis_client, "redis", _FakeRedis(pubsub))
    monkeypatch.setattr(
        tasks_router,
        "_get_owned_active_task",
        AsyncMock(return_value={"task_id": "task-1", "user_id": 123}),
    )
    monkeypatch.setattr(
        tasks_router.httpx,
        "AsyncClient",
        lambda: _FakeAsyncClient(list(status_responses), status_calls),
    )
    monkeypatch.setattr(
        tasks_router,
        "_get_user_history_record",
        fake_get_user_history_record,
    )

    response = await tasks_router.task_status_stream(
        "task-1", type("User", (), {"id": 123})()
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
            "data": json.dumps({"status": "pending", "queue_pos": 3}),
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
