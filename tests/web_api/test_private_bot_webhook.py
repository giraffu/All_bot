import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.services.private_qqcc_bot_webhook_queue import (
    PrivateQqccBotWebhookQueue,
    PrivateQqccBotWebhookQueueError,
)
from src.web_api import dependencies as web_dependencies
from src.web_api.routers import private_bots


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


def _build_app(*, bot):
    app = FastAPI()
    app.include_router(private_bots.router, prefix="/api/private-bots")
    db = SimpleNamespace(execute=AsyncMock(return_value=_ScalarResult(bot)))

    async def _override_get_db():
        yield db

    app.dependency_overrides[web_dependencies.get_db] = _override_get_db
    return app, db


def _active_bot(**overrides):
    values = {
        "id": 41,
        "webhook_secret_hash": hashlib.sha256(b"telegram-secret").hexdigest(),
        "owner_enabled": True,
        "admin_enabled": True,
        "runtime_status": "active",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


async def _post(app, *, public_id="public-id", secret="telegram-secret", json_body=None):
    headers = {}
    if secret is not None:
        headers["X-Telegram-Bot-Api-Secret-Token"] = secret
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        return await client.post(
            f"/api/private-bots/webhook/{public_id}",
            headers=headers,
            json={"update_id": 1001} if json_body is None else json_body,
        )


@pytest.mark.asyncio
async def test_unknown_private_bot_webhook_returns_404(monkeypatch):
    app, db = _build_app(bot=None)
    enqueue = AsyncMock()
    monkeypatch.setattr(private_bots, "enqueue_private_qqcc_bot_update", enqueue)

    response = await _post(app)

    assert response.status_code == 404
    assert response.json()["detail"] == "Private bot webhook not found"
    db.execute.assert_awaited_once()
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("secret", [None, "wrong-secret"])
async def test_private_bot_webhook_rejects_missing_or_wrong_secret(monkeypatch, secret):
    app, _ = _build_app(bot=_active_bot())
    enqueue = AsyncMock()
    monkeypatch.setattr(private_bots, "enqueue_private_qqcc_bot_update", enqueue)

    response = await _post(app, secret=secret)

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid webhook secret"
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"owner_enabled": False},
        {"admin_enabled": False},
        {"runtime_status": "paused"},
    ],
)
async def test_inactive_private_bot_update_is_dropped_without_retry(
    monkeypatch, overrides
):
    app, _ = _build_app(bot=_active_bot(**overrides))
    enqueue = AsyncMock()
    monkeypatch.setattr(private_bots, "enqueue_private_qqcc_bot_update", enqueue)

    response = await _post(app)

    assert response.status_code == 200
    assert response.json() == {"status": "dropped", "reason": "inactive"}
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        [],
        {},
        {"update_id": True},
        {"update_id": 0},
        {"update_id": -1},
        {"update_id": "1001"},
    ],
)
async def test_private_bot_webhook_requires_object_with_positive_integer_update_id(
    monkeypatch, body
):
    app, _ = _build_app(bot=_active_bot())
    enqueue = AsyncMock()
    monkeypatch.setattr(private_bots, "enqueue_private_qqcc_bot_update", enqueue)

    response = await _post(app, json_body=body)

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid Telegram update"
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_private_bot_webhook_queues_first_update(monkeypatch):
    bot = _active_bot(id=99)
    app, _ = _build_app(bot=bot)
    update = {"update_id": 1001, "message": {"text": "hello"}}
    enqueue = AsyncMock(return_value=True)
    monkeypatch.setattr(private_bots, "enqueue_private_qqcc_bot_update", enqueue)

    response = await _post(app, json_body=update)

    assert response.status_code == 202
    assert response.json() == {"status": "queued"}
    enqueue.assert_awaited_once_with(
        private_bot_id=99,
        update_id=1001,
        update=update,
    )


@pytest.mark.asyncio
async def test_duplicate_private_bot_webhook_returns_success_without_requeue(
    monkeypatch,
):
    app, _ = _build_app(bot=_active_bot())
    enqueue = AsyncMock(return_value=False)
    monkeypatch.setattr(private_bots, "enqueue_private_qqcc_bot_update", enqueue)

    response = await _post(app)

    assert response.status_code == 200
    assert response.json() == {"status": "duplicate"}


@pytest.mark.asyncio
async def test_private_bot_webhook_returns_503_when_redis_is_unavailable(monkeypatch):
    app, _ = _build_app(bot=_active_bot())
    enqueue = AsyncMock(side_effect=PrivateQqccBotWebhookQueueError("redis down"))
    monkeypatch.setattr(private_bots, "enqueue_private_qqcc_bot_update", enqueue)

    response = await _post(app)

    assert response.status_code == 503
    assert response.json()["detail"] == "Webhook queue unavailable"


@pytest.mark.asyncio
async def test_private_bot_webhook_rejects_oversized_body_before_json_decode(monkeypatch):
    app, _ = _build_app(bot=_active_bot())
    enqueue = AsyncMock()
    monkeypatch.setattr(private_bots, "enqueue_private_qqcc_bot_update", enqueue)
    headers = {"X-Telegram-Bot-Api-Secret-Token": "telegram-secret"}
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/private-bots/webhook/public-id",
            headers=headers,
            content=b"{" + b"x" * (private_bots.PRIVATE_BOT_WEBHOOK_MAX_BYTES + 1),
        )

    assert response.status_code == 413
    enqueue.assert_not_awaited()


class _FakeRedis:
    def __init__(self, result=1, error=None):
        self.result = result
        self.error = error
        self.calls = []

    async def eval(self, *args):
        self.calls.append(args)
        if self.error is not None:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_webhook_queue_uses_prefixed_atomic_dedupe_and_stream_payload():
    redis = _FakeRedis(result=1)
    queue = PrivateQqccBotWebhookQueue(
        redis=redis,
        redis_prefix="test-prefix:",
        clock=lambda: 1_789_800_123.5,
    )
    update = {"update_id": 77, "message": {"text": "safe"}}

    queued = await queue.enqueue(private_bot_id=12, update_id=77, update=update)

    assert queued is True
    assert len(redis.calls) == 1
    (
        script,
        key_count,
        dedupe_key,
        stream_key,
        metrics_key,
        ttl,
        bot_id,
        update_id,
        payload,
        received_at,
        deferred_errors,
    ) = redis.calls[0]
    assert key_count == 3
    assert dedupe_key == "test-prefix:private_qqcc_bot:webhook:dedupe:12:77"
    assert stream_key == "test-prefix:private_qqcc_bot:webhook:updates"
    assert metrics_key == "test-prefix:private_qqcc_bot:metrics:counters"
    assert ttl == "86400"
    assert bot_id == "12"
    assert update_id == "77"
    assert json.loads(payload) == update
    assert received_at == "1789800123.5"
    assert deferred_errors == "0"
    assert "secret" not in " ".join(map(str, redis.calls[0])).lower()
    assert script.index('redis.call("XADD"') < script.index('redis.pcall("SET"')


@pytest.mark.asyncio
async def test_webhook_queue_flushes_deferred_redis_error_metric_on_recovery():
    redis = _FakeRedis(error=ConnectionError("redis unavailable"))
    queue = PrivateQqccBotWebhookQueue(redis=redis, redis_prefix="test-prefix:")

    with pytest.raises(PrivateQqccBotWebhookQueueError):
        await queue.enqueue(
            private_bot_id=1,
            update_id=1,
            update={"update_id": 1},
        )
    redis.error = None
    redis.result = 1

    assert await queue.enqueue(
        private_bot_id=1,
        update_id=2,
        update={"update_id": 2},
    )
    assert redis.calls[-1][-1] == "1"


@pytest.mark.asyncio
async def test_webhook_queue_reports_duplicate_and_wraps_redis_failures():
    duplicate_queue = PrivateQqccBotWebhookQueue(
        redis=_FakeRedis(result=0),
        redis_prefix="test-prefix:",
    )
    assert (
        await duplicate_queue.enqueue(
            private_bot_id=1,
            update_id=2,
            update={"update_id": 2},
        )
        is False
    )

    failing_queue = PrivateQqccBotWebhookQueue(
        redis=_FakeRedis(error=ConnectionError("redis unavailable")),
        redis_prefix="test-prefix:",
    )
    with pytest.raises(PrivateQqccBotWebhookQueueError):
        await failing_queue.enqueue(
            private_bot_id=1,
            update_id=2,
            update={"update_id": 2},
        )


def test_web_bff_registers_private_bot_webhook_router():
    from src.web_api.main import app

    assert any(
        getattr(route, "path", None) == "/api/private-bots/webhook/{public_id}"
        for route in app.routes
    )
