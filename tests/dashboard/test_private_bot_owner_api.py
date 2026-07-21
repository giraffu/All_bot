from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from dashboard.backend import private_bot_owner_auth, qqcc_config_main
from dashboard.backend.routers import private_bots

OWNER_SECRET = "a2tra2tra2tra2tra2tra2tra2tra2tra2tra2tra2s="


class _FakeRedis:
    def __init__(self):
        self.values = {}

    async def set(self, key, value, *, ex, nx):
        if nx and key in self.values:
            return False
        self.values[key] = str(value)
        return True

    async def getdel(self, key):
        return self.values.pop(key, None)


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeSession:
    def __init__(self, bot):
        self.bot = bot

    async def execute(self, _stmt):
        return _Result(self.bot)


@pytest.fixture(autouse=True)
def _enable_private_bot_routes(monkeypatch):
    monkeypatch.setenv("PRIVATE_QQCC_BOT_ENABLED", "true")


@pytest.mark.asyncio
async def test_owner_ticket_exchange_bypasses_admin_auth_and_isolates_owner_payload(
    monkeypatch,
):
    redis = _FakeRedis()
    monkeypatch.setenv("PRIVATE_QQCC_BOT_OWNER_JWT_SECRET", OWNER_SECRET)
    monkeypatch.setattr(private_bots.redis_client, "redis", redis)
    bot = SimpleNamespace(
        id=7,
        owner_user_id=42,
        telegram_bot_id=123,
        telegram_username="tenant_bot",
        telegram_display_name="Tenant Bot",
        token_ciphertext="must-not-leak",
        token_fingerprint="must-not-leak",
        webhook_secret_hash="must-not-leak",
        owner_enabled=True,
        admin_enabled=True,
        runtime_status="active",
        last_error_code=None,
        last_error_message=None,
        last_webhook_at=datetime(2026, 7, 12, 12, 0, 0),
        last_update_at=None,
        created_at=datetime(2026, 7, 12, 11, 0, 0),
        updated_at=datetime(2026, 7, 12, 12, 0, 0),
        config={"global_enabled": True},
        config_version=1,
    )

    async def override_get_db():
        yield _FakeSession(bot)

    qqcc_config_main.app.dependency_overrides[private_bots.get_db] = override_get_db
    try:
        ticket = await private_bot_owner_auth.issue_private_bot_owner_ticket(
            internal_user_id=42,
            redis=redis,
        )
        async with AsyncClient(
            transport=ASGITransport(app=qqcc_config_main.app),
            base_url="http://testserver",
        ) as client:
            exchange = await client.post(
                "/api/private-bots/owner/auth/exchange",
                json={"ticket": ticket},
            )
            assert exchange.status_code == 200
            owner_response = await client.get(
                "/api/private-bots/owner/me",
                headers={
                    "Authorization": f"Bearer {exchange.json()['access_token']}"
                },
            )
    finally:
        qqcc_config_main.app.dependency_overrides.pop(private_bots.get_db, None)

    assert owner_response.status_code == 200
    payload = owner_response.json()
    assert payload["bot"]["id"] == 7
    serialized = str(payload)
    assert "must-not-leak" not in serialized


@pytest.mark.asyncio
async def test_admin_private_bot_routes_still_require_admin_token():
    async with AsyncClient(
        transport=ASGITransport(app=qqcc_config_main.app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/private-bots/admin")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_runtime_metrics_endpoint_uses_sanitized_collector(monkeypatch):
    collector = AsyncMock(
        return_value={
            "available": True,
            "stream_backlog": 3,
            "stream_pending": 1,
        }
    )
    monkeypatch.setattr(
        private_bots,
        "collect_private_qqcc_runtime_metrics",
        collector,
    )

    result = await private_bots.get_private_bot_runtime_metrics_for_admin(
        _admin=SimpleNamespace(username="admin"),
    )

    assert result["stream_backlog"] == 3
    collector.assert_awaited_once_with(private_bots.redis_client.redis)


@pytest.mark.asyncio
async def test_public_owner_host_cannot_reach_admin_private_bot_routes(monkeypatch):
    monkeypatch.setenv("PRIVATE_QQCC_BOT_OWNER_HOST", "private.example.test")
    monkeypatch.setenv("QQCC_CONFIG_ADMIN_HOST", "admin.example.test")
    async with AsyncClient(
        transport=ASGITransport(app=qqcc_config_main.app),
        base_url="https://private.example.test",
    ) as client:
        response = await client.get("/api/private-bots/admin")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_owner_api_is_only_available_on_owner_host_when_configured(monkeypatch):
    monkeypatch.setenv("PRIVATE_QQCC_BOT_OWNER_HOST", "private.example.test")
    monkeypatch.setenv("QQCC_CONFIG_ADMIN_HOST", "admin.example.test")
    async with AsyncClient(
        transport=ASGITransport(app=qqcc_config_main.app),
        base_url="https://admin.example.test",
    ) as client:
        response = await client.post(
            "/api/private-bots/owner/auth/exchange",
            json={"ticket": "must-not-be-processed"},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_private_bot_routes_are_404_while_rollout_gate_is_disabled(monkeypatch):
    monkeypatch.setenv("PRIVATE_QQCC_BOT_ENABLED", "false")
    async with AsyncClient(
        transport=ASGITransport(app=qqcc_config_main.app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/private-bots/owner/auth/exchange",
            json={"ticket": "not-used"},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_owner_config_rejects_oversized_http_body_before_parsing():
    async with AsyncClient(
        transport=ASGITransport(app=qqcc_config_main.app),
        base_url="http://testserver",
    ) as client:
        response = await client.put(
            "/api/private-bots/owner/config",
            headers={"Content-Length": str(700 * 1024)},
            content=b"{}",
        )

    assert response.status_code == 413


@pytest.mark.asyncio
async def test_sensitive_owner_validation_never_echoes_token_or_ticket(monkeypatch):
    secret = "123:SUPER_SECRET_MUST_NOT_ECHO"
    monkeypatch.setenv("PRIVATE_QQCC_BOT_OWNER_JWT_SECRET", OWNER_SECRET)
    redis = _FakeRedis()
    ticket = await private_bot_owner_auth.issue_private_bot_owner_ticket(
        internal_user_id=42,
        redis=redis,
    )
    owner_auth = await private_bot_owner_auth.exchange_private_bot_owner_ticket(
        ticket=ticket,
        redis=redis,
        secret_key=OWNER_SECRET,
    )
    async with AsyncClient(
        transport=ASGITransport(app=qqcc_config_main.app),
        base_url="http://testserver",
    ) as client:
        invalid_shape = await client.put(
            "/api/private-bots/owner/credentials",
            json={"token": {"nested": secret}},
            headers={"Authorization": f"Bearer {owner_auth['access_token']}"},
        )
        oversized = await client.post(
            "/api/private-bots/owner/auth/exchange",
            content=(f'{{"ticket":"{secret * 100}"}}').encode(),
            headers={"Content-Type": "application/json"},
        )

    assert invalid_shape.status_code == 422
    assert oversized.status_code == 413
    assert secret not in invalid_shape.text
    assert secret not in oversized.text


@pytest.mark.asyncio
async def test_owner_demo_generation_stays_in_private_bot_media_namespace(monkeypatch):
    bot = SimpleNamespace(
        id=7,
        admin_enabled=True,
        config={"draw_scenes": []},
    )
    submit = AsyncMock(return_value={"generation_id": "task-1", "status": "pending"})
    monkeypatch.setattr(private_bots, "submit_qqcc_demo_generation", submit)
    scene = {
        "id": "portrait",
        "prompt": "portrait prompt",
        "engine": "free_edit_v2",
        "demo_input_media": {
            "object_key": "qqcc/private/7/demo/draw/portrait/input",
            "mime_type": "image/png",
        },
    }

    result = await private_bots.submit_owner_private_bot_demo_generation(
        "draw",
        private_bots.OwnerDemoGenerationRequest(scene=scene),
        owner_user_id=42,
        db=_FakeSession(bot),
    )

    assert result["status"] == "pending"
    submit.assert_awaited_once()
    assert submit.await_args.kwargs["scene_kind"] == "draw"
    assert submit.await_args.kwargs["scene"] == scene
    assert submit.await_args.kwargs["object_prefix"] == "qqcc/private/7/demo"
    assert isinstance(submit.await_args.kwargs["config"], dict)
