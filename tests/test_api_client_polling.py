import logging

import httpx
import pytest
import redis.asyncio as redis_asyncio

from src import api_client as api_client_module


@pytest.mark.asyncio
async def test_iter_poll_progress_backs_off_and_resets_on_state_change(monkeypatch):
    client = api_client_module.APIClient.__new__(api_client_module.APIClient)
    payloads = iter(
        [
            {"status": "pending", "progress": 0.1, "queue_pos": 2},
            {"status": "pending", "progress": 0.1, "queue_pos": 2},
            {"status": "running", "progress": 0.5, "queue_pos": None},
            {"status": "done", "progress": 1.0, "queue_pos": None},
        ]
    )
    sleeps = []

    async def fake_fetch_progress_status(_status_url):
        return next(payloads)

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(client, "_fetch_progress_status", fake_fetch_progress_status)
    monkeypatch.setattr(
        client,
        "_is_terminal_progress_payload",
        lambda payload: payload.get("status") == "done",
    )
    monkeypatch.setattr(api_client_module, "POLL_INTERVAL", 2)
    monkeypatch.setattr(api_client_module, "BOT_STATUS_POLL_INITIAL_INTERVAL", 5)
    monkeypatch.setattr(api_client_module, "BOT_STATUS_POLL_MAX_INTERVAL", 20)
    monkeypatch.setattr(api_client_module.asyncio, "sleep", fake_sleep)

    events = [
        event
        async for event in client._iter_poll_progress(
            task_id="task-1",
            status_url="http://central/status/task-1",
        )
    ]

    assert [event["status"] for event in events] == [
        "pending",
        "pending",
        "running",
        "done",
    ]
    assert sleeps == [5, 7.5, 5]


class _FakePubSub:
    def __init__(self):
        self.unsubscribed = []
        self.closed = False

    async def subscribe(self, _channel):
        return None

    async def get_message(self, **_kwargs):
        raise ConnectionResetError("connection closed by server")

    async def unsubscribe(self, channel):
        self.unsubscribed.append(channel)

    async def close(self):
        self.closed = True


class _FakeRedisClient:
    def __init__(self, pubsub):
        self._pubsub = pubsub
        self.closed = False

    def pubsub(self):
        return self._pubsub

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
async def test_listen_for_progress_falls_back_to_polling_after_pubsub_disconnect(
    monkeypatch,
    caplog,
):
    client = api_client_module.APIClient.__new__(api_client_module.APIClient)
    payloads = iter(
        [
            {"status": "pending", "progress": 0.1, "queue_pos": 2},
            {"status": "done", "progress": 1.0, "queue_pos": None},
        ]
    )
    pubsub = _FakePubSub()
    redis_client = _FakeRedisClient(pubsub)

    async def fake_fetch_progress_status(_status_url):
        return next(payloads)

    monkeypatch.setattr(client, "_fetch_progress_status", fake_fetch_progress_status)
    monkeypatch.setattr(
        client,
        "_is_terminal_progress_payload",
        lambda payload: payload.get("status") == "done",
    )
    monkeypatch.setattr(redis_asyncio, "from_url", lambda *_args, **_kwargs: redis_client)

    with caplog.at_level(logging.WARNING):
        events = [event async for event in client.listen_for_progress("task-1")]

    assert [event["status"] for event in events] == ["pending", "done"]
    assert pubsub.unsubscribed == ["comfy:task_events:task-1"]
    assert pubsub.closed is True
    assert redis_client.closed is True
    assert "Falling back to HTTP polling" in caplog.text
    assert not [
        record
        for record in caplog.records
        if record.levelno >= logging.ERROR
        and "Pub/Sub error" in record.getMessage()
    ]


@pytest.mark.asyncio
async def test_listen_for_progress_keeps_404_cancelled_semantics(monkeypatch):
    client = api_client_module.APIClient.__new__(api_client_module.APIClient)
    request = httpx.Request("GET", "http://central/status/task-missing")
    response = httpx.Response(404, request=request)

    async def fake_fetch_progress_status(_status_url):
        raise httpx.HTTPStatusError(
            "missing",
            request=request,
            response=response,
        )

    monkeypatch.setattr(client, "_fetch_progress_status", fake_fetch_progress_status)

    events = []
    with pytest.raises(RuntimeError, match="not found"):
        async for event in client.listen_for_progress("task-missing"):
            events.append(event)

    assert events == [{"status": "cancelled", "error": "Task cancelled (404)"}]
