import httpx
import pytest

from src import api_client as api_client_module
from src.circuit_breaker import CircuitBreakerOpenException


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


@pytest.mark.asyncio
async def test_request_uses_isolated_circuit_breaker_keys(monkeypatch):
    client = api_client_module.APIClient.__new__(api_client_module.APIClient)
    calls = []

    class FakeBreaker:
        async def call(self, func):
            calls.append("breaker")
            return await func()

    class FakeHttpClient:
        async def request(self, method, url, **kwargs):
            calls.append((method, url, kwargs))
            return httpx.Response(
                200,
                json={"ok": True},
                request=httpx.Request(method, url),
            )

    monkeypatch.setattr(
        api_client_module,
        "get_circuit_breaker",
        lambda key: (
            calls.append(("key", key)) or FakeBreaker()
        ),
    )
    client.headers = {}
    client.client = FakeHttpClient()

    response = await client._request(
        "GET",
        "http://central/status/task-1",
        circuit_breaker_key="status",
    )

    assert response.json() == {"ok": True}
    assert calls[0] == ("key", "status")


@pytest.mark.asyncio
async def test_request_open_status_breaker_does_not_block_submit_key(monkeypatch):
    client = api_client_module.APIClient.__new__(api_client_module.APIClient)
    calls = []

    class OpenBreaker:
        async def call(self, _func):
            raise CircuitBreakerOpenException("Circuit is open")

    class ClosedBreaker:
        async def call(self, func):
            return await func()

    class FakeHttpClient:
        async def request(self, method, url, **kwargs):
            calls.append((method, url))
            return httpx.Response(
                200,
                json={"task_id": "task-1"},
                request=httpx.Request(method, url),
            )

    def fake_get_circuit_breaker(key):
        return OpenBreaker() if key == "status" else ClosedBreaker()

    monkeypatch.setattr(
        api_client_module,
        "get_circuit_breaker",
        fake_get_circuit_breaker,
    )
    client.headers = {}
    client.client = FakeHttpClient()

    with pytest.raises(CircuitBreakerOpenException):
        await client._request(
            "GET",
            "http://central/status/task-1",
            circuit_breaker_key="status",
        )

    response = await client._request(
        "POST",
        "http://central/comfy_img2img",
        circuit_breaker_key="submit",
    )

    assert response.json() == {"task_id": "task-1"}
    assert calls == [("POST", "http://central/comfy_img2img")]


def test_central_api_circuit_failure_classifier_counts_5xx_not_4xx():
    request = httpx.Request("GET", "http://central/status/task-1")
    client_error = httpx.HTTPStatusError(
        "bad request",
        request=request,
        response=httpx.Response(400, request=request),
    )
    server_error = httpx.HTTPStatusError(
        "service unavailable",
        request=request,
        response=httpx.Response(503, request=request),
    )

    assert api_client_module.should_count_central_api_circuit_failure(client_error) is False
    assert api_client_module.should_count_central_api_circuit_failure(server_error) is True
    assert (
        api_client_module.should_count_central_api_circuit_failure(
            httpx.ConnectError("connection lost")
        )
        is True
    )
