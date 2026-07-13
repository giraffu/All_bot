import logging
from unittest.mock import AsyncMock

import httpx
import pytest

from src.services.private_qqcc_bot_telegram_gateway import (
    PrivateBotTelegramGatewayError,
    TelegramHttpPrivateBotGateway,
)


@pytest.mark.asyncio
async def test_private_bot_gateway_inspects_identity_without_exposing_token():
    request = AsyncMock(
        side_effect=[
            {
                "ok": True,
                "result": {
                    "id": 123,
                    "username": "tenant_bot",
                    "first_name": "Tenant",
                },
            },
            {"ok": True, "result": {"url": ""}},
        ]
    )
    gateway = TelegramHttpPrivateBotGateway(request_func=request)

    identity = await gateway.inspect_token("123:secret-value")

    assert identity.bot_id == 123
    assert identity.username == "tenant_bot"
    assert identity.display_name == "Tenant"
    assert identity.webhook_url == ""
    assert [call.args[0] for call in request.await_args_list] == [
        "getMe",
        "getWebhookInfo",
    ]


@pytest.mark.asyncio
async def test_private_bot_gateway_returns_only_sanitized_errors():
    request = AsyncMock(side_effect=RuntimeError("request for 123:secret-value failed"))
    gateway = TelegramHttpPrivateBotGateway(request_func=request)

    with pytest.raises(PrivateBotTelegramGatewayError) as exc_info:
        await gateway.inspect_token("123:secret-value")

    assert exc_info.value.code == "telegram_unavailable"
    assert "secret-value" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


@pytest.mark.asyncio
async def test_gateway_redacts_token_from_http_client_request_logs(
    monkeypatch,
    caplog,
):
    secret_token = "123456:SUPER_SECRET_TOKEN"
    real_async_client = httpx.AsyncClient

    def _client(*_args, **kwargs):
        async def _respond(request: httpx.Request):
            method = request.url.path.rsplit("/", 1)[-1]
            result = (
                {"id": 123456, "username": "safe_bot", "first_name": "Safe"}
                if method == "getMe"
                else {"url": ""}
            )
            return httpx.Response(200, json={"ok": True, "result": result})

        kwargs["transport"] = httpx.MockTransport(_respond)
        return real_async_client(**kwargs)

    monkeypatch.setattr(
        "src.services.private_qqcc_bot_telegram_gateway.httpx.AsyncClient",
        _client,
    )
    caplog.set_level(logging.INFO, logger="httpx")

    await TelegramHttpPrivateBotGateway().inspect_token(secret_token)

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert secret_token not in rendered
    assert "/bot<redacted>/getMe" in rendered


def test_gateway_redacts_descendant_httpcore_warning_records(caplog):
    secret_token = "123456:DESCENDANT_SECRET_TOKEN"
    caplog.set_level(logging.WARNING, logger="httpcore.connection")

    logging.getLogger("httpcore.connection").warning(
        "request failed at %s",
        f"https://api.telegram.org/bot{secret_token}/getMe",
    )

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert secret_token not in rendered
    assert "/bot<redacted>/getMe" in rendered


@pytest.mark.asyncio
async def test_private_bot_gateway_sets_and_deletes_webhook_with_explicit_drop_policy():
    request = AsyncMock(return_value={"ok": True, "result": True})
    gateway = TelegramHttpPrivateBotGateway(request_func=request)

    await gateway.set_webhook(
        token="123:secret-value",
        url="https://api.example.test/hook/id",
        secret_token="safe_secret",
        drop_pending_updates=True,
    )
    await gateway.delete_webhook(
        token="123:secret-value",
        drop_pending_updates=True,
    )

    assert request.await_args_list[0].args == ("setWebhook", "123:secret-value")
    assert request.await_args_list[0].kwargs["payload"]["secret_token"] == "safe_secret"
    assert request.await_args_list[1].args == ("deleteWebhook", "123:secret-value")
