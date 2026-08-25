from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Callable
from urllib.parse import urlparse


_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{12,128}$")
_AMOUNT_QUANT = Decimal("0.01")
_REDIS_KEY_PREFIX = "allbot:alipay_checkout:v1:"
DEFAULT_CHECKOUT_TTL_SECONDS = 30 * 60


def _new_checkout_token() -> str:
    return secrets.token_urlsafe(24)


@dataclass(frozen=True)
class AlipayCheckoutSession:
    public_order_id: str
    out_trade_no: str
    subject: str
    amount: str
    pay_url: str
    created_at: str


def _format_amount(value: Decimal | str | int) -> str:
    amount = Decimal(str(value)).quantize(_AMOUNT_QUANT, rounding=ROUND_HALF_UP)
    return f"{amount:.2f}"


def _checkout_ttl_seconds() -> int:
    raw_value = os.getenv(
        "ALIPAY_CHECKOUT_TTL_SECONDS",
        str(DEFAULT_CHECKOUT_TTL_SECONDS),
    )
    try:
        return max(300, min(int(raw_value), 24 * 60 * 60))
    except (TypeError, ValueError):
        return DEFAULT_CHECKOUT_TTL_SECONDS


def _redis_key(token: str) -> str:
    if not _TOKEN_PATTERN.fullmatch(str(token or "")):
        raise ValueError("Invalid Alipay checkout token")
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"{_REDIS_KEY_PREFIX}{token_hash}"


def _extract_pay_url(result: dict | None) -> str:
    if not isinstance(result, dict) or result.get("code") != 1:
        raise ValueError("Alipay payment URL creation failed")
    data = result.get("data")
    pay_url = data.get("payurl") if isinstance(data, dict) else result.get("payurl")
    if not isinstance(pay_url, str) or not pay_url:
        raise ValueError("Alipay payment URL is missing")
    return pay_url


def validate_alipay_launch_url(pay_url: str, *, gateway_url: str) -> None:
    parsed_pay_url = urlparse(pay_url)
    parsed_gateway = urlparse(gateway_url)
    if (
        parsed_pay_url.scheme.lower() != "https"
        or parsed_gateway.scheme.lower() != "https"
        or parsed_pay_url.hostname != parsed_gateway.hostname
        or parsed_pay_url.port != parsed_gateway.port
        or parsed_pay_url.path != parsed_gateway.path
    ):
        raise ValueError("Payment URL is not on the trusted Alipay gateway")


def build_alipay_checkout_url(*, base_url: str, token: str) -> str:
    _redis_key(token)
    parsed = urlparse(str(base_url or ""))
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("Alipay checkout base URL must use HTTPS")
    return f"{str(base_url).rstrip('/')}/pay/alipay/{token}"


async def save_alipay_checkout_session(
    token: str,
    session: AlipayCheckoutSession,
    *,
    redis=None,
    ttl_seconds: int | None = None,
) -> None:
    if redis is None:
        from src.services.redis_client import redis_client

        redis = redis_client.redis
    ttl = _checkout_ttl_seconds() if ttl_seconds is None else int(ttl_seconds)
    await redis.setex(
        _redis_key(token),
        max(1, ttl),
        json.dumps(asdict(session), ensure_ascii=False, separators=(",", ":")),
    )


async def load_alipay_checkout_session(
    token: str,
    *,
    redis=None,
) -> AlipayCheckoutSession | None:
    if redis is None:
        from src.services.redis_client import redis_client

        redis = redis_client.redis
    redis_key = _redis_key(token)
    try:
        raw_value = await redis.get(redis_key)
        if not raw_value:
            return None
        payload = json.loads(raw_value)
        return AlipayCheckoutSession(
            public_order_id=str(payload["public_order_id"]),
            out_trade_no=str(payload["out_trade_no"]),
            subject=str(payload["subject"]),
            amount=_format_amount(payload["amount"]),
            pay_url=str(payload["pay_url"]),
            created_at=str(payload["created_at"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


async def create_alipay_checkout_payment(
    *,
    alipay_service,
    out_trade_no: str,
    public_order_id: str,
    subject: str,
    amount: Decimal | str | int,
    redis=None,
    token_factory: Callable[[], str] = _new_checkout_token,
    ttl_seconds: int | None = None,
) -> dict:
    token = token_factory()
    checkout_url = build_alipay_checkout_url(
        base_url=alipay_service.config.return_base_url,
        token=token,
    )
    result = alipay_service.create_payment_url(
        out_trade_no=out_trade_no,
        subject=subject,
        amount=amount,
        product="wap",
        return_url=checkout_url,
    )
    if inspect.isawaitable(result):
        result = await result
    pay_url = _extract_pay_url(result)
    validate_alipay_launch_url(
        pay_url,
        gateway_url=alipay_service.config.gateway_url,
    )
    await save_alipay_checkout_session(
        token,
        AlipayCheckoutSession(
            public_order_id=str(public_order_id),
            out_trade_no=str(out_trade_no),
            subject=str(subject)[:256],
            amount=_format_amount(amount),
            pay_url=pay_url,
            created_at=datetime.now(timezone.utc).isoformat(),
        ),
        redis=redis,
        ttl_seconds=ttl_seconds,
    )
    return {"code": 1, "data": {"payurl": checkout_url}}
