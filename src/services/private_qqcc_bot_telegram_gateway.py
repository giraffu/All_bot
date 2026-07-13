from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from src.services.private_qqcc_bot_service import PrivateBotTelegramIdentity
from src.services.private_qqcc_bot_telegram_transport import (
    build_private_telegram_bot_base_url,
)


_TELEGRAM_BOT_TOKEN_URL_PATTERN = re.compile(r"/bot[^/\s\"']+/")


def _redact_telegram_token_url(value: object) -> object:
    rendered = str(value)
    if "/bot" not in rendered:
        return value
    return _TELEGRAM_BOT_TOKEN_URL_PATTERN.sub("/bot<redacted>/", rendered)


class _TelegramTokenLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact_telegram_token_url(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_redact_telegram_token_url(arg) for arg in record.args)
        elif isinstance(record.args, dict):
            record.args = {
                key: _redact_telegram_token_url(value)
                for key, value in record.args.items()
            }
        return True


def _install_http_client_token_log_guard() -> None:
    current_factory = logging.getLogRecordFactory()
    if not getattr(current_factory, "_private_bot_token_guard", False):
        token_filter = _TelegramTokenLogFilter()

        def _guarded_record_factory(*args, **kwargs):
            record = current_factory(*args, **kwargs)
            token_filter.filter(record)
            return record

        _guarded_record_factory._private_bot_token_guard = True
        logging.setLogRecordFactory(_guarded_record_factory)

    for logger_name in ("httpx", "httpcore"):
        target = logging.getLogger(logger_name)
        if not any(isinstance(item, _TelegramTokenLogFilter) for item in target.filters):
            target.addFilter(_TelegramTokenLogFilter())
        # These libraries include full URLs in lower-level diagnostics. The
        # application logs sanitized gateway error codes instead.
        target.setLevel(logging.WARNING)


_install_http_client_token_log_guard()


class PrivateBotTelegramGatewayError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


RequestFunc = Callable[..., Awaitable[dict[str, Any]]]


class TelegramHttpPrivateBotGateway:
    def __init__(
        self,
        *,
        request_func: RequestFunc | None = None,
        timeout_seconds: float = 15.0,
    ):
        self.timeout_seconds = timeout_seconds
        self.request_func = request_func or self._request

    async def _request(
        self,
        method: str,
        token: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{build_private_telegram_bot_base_url()}{token}/{method}"
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(url, json=payload or {})
            return response.json()

    async def _call(
        self,
        method: str,
        token: str,
        *,
        payload: dict[str, Any] | None = None,
        invalid_token_on_failure: bool = False,
    ) -> dict[str, Any]:
        try:
            response = await self.request_func(method, token, payload=payload or {})
        except Exception:
            raise PrivateBotTelegramGatewayError(
                "telegram_unavailable",
                "Telegram Bot API is temporarily unavailable",
            ) from None
        if not isinstance(response, dict) or response.get("ok") is not True:
            raise PrivateBotTelegramGatewayError(
                "invalid_token" if invalid_token_on_failure else "telegram_request_failed",
                "Telegram rejected the private Bot request",
            )
        result = response.get("result")
        return result if isinstance(result, dict) else {"value": result}

    async def inspect_token(self, token: str) -> PrivateBotTelegramIdentity:
        bot = await self._call(
            "getMe",
            token,
            invalid_token_on_failure=True,
        )
        webhook = await self._call(
            "getWebhookInfo",
            token,
            invalid_token_on_failure=True,
        )
        try:
            bot_id = int(bot.get("id") or 0)
        except (TypeError, ValueError) as exc:
            raise PrivateBotTelegramGatewayError(
                "invalid_token", "Telegram returned an invalid Bot identity"
            ) from exc
        username = str(bot.get("username") or "").strip()
        if bot_id <= 0 or not username:
            raise PrivateBotTelegramGatewayError(
                "invalid_token", "Telegram returned an invalid Bot identity"
            )
        return PrivateBotTelegramIdentity(
            bot_id=bot_id,
            username=username,
            display_name=str(bot.get("first_name") or username).strip()[:255],
            webhook_url=str(webhook.get("url") or "").strip(),
        )

    async def set_webhook(
        self,
        *,
        token: str,
        url: str,
        secret_token: str,
        drop_pending_updates: bool,
    ) -> None:
        await self._call(
            "setWebhook",
            token,
            payload={
                "url": url,
                "secret_token": secret_token,
                "drop_pending_updates": bool(drop_pending_updates),
                "allowed_updates": ["message", "callback_query"],
            },
        )

    async def delete_webhook(
        self,
        *,
        token: str,
        drop_pending_updates: bool,
    ) -> None:
        await self._call(
            "deleteWebhook",
            token,
            payload={"drop_pending_updates": bool(drop_pending_updates)},
        )
