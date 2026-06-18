import httpx
import pytest

from src import api_client as api_client_module


@pytest.mark.asyncio
async def test_iter_poll_progress_uses_fixed_low_frequency_interval(monkeypatch):
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
    monkeypatch.setattr(api_client_module, "BOT_STATUS_POLL_INTERVAL", 15)
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
    assert sleeps == [15, 15, 15]


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
async def test_listen_for_progress_uses_polling_without_pubsub(
    monkeypatch,
):
    client = api_client_module.APIClient.__new__(api_client_module.APIClient)
    payloads = iter(
        [
            {"status": "pending", "progress": 0.1, "queue_pos": 2},
            {"status": "done", "progress": 1.0, "queue_pos": None},
        ]
    )
    async def fake_fetch_progress_status(_status_url):
        return next(payloads)

    async def fail_pubsub(*_args, **_kwargs):
        raise AssertionError("Pub/Sub should not be used by listen_for_progress")

    monkeypatch.setattr(client, "_fetch_progress_status", fake_fetch_progress_status)
    monkeypatch.setattr(
        client,
        "_is_terminal_progress_payload",
        lambda payload: payload.get("status") == "done",
    )
    monkeypatch.setattr(client, "_iter_pubsub_progress", fail_pubsub)

    events = [event async for event in client.listen_for_progress("task-1")]

    assert [event["status"] for event in events] == ["pending", "done"]


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
    with pytest.raises(RuntimeError, match="cancelled"):
        async for event in client.listen_for_progress("task-missing"):
            events.append(event)

    assert events == [{"status": "cancelled", "error": "Task cancelled (404)"}]
