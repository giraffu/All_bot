import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.services.alipay_checkout_service import (
    create_alipay_checkout_payment,
    load_alipay_checkout_session,
)


class _FakeRedis:
    def __init__(self):
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def setex(self, key: str, ttl: int, value: str):
        self.values[key] = value
        self.ttls[key] = ttl

    async def get(self, key: str):
        return self.values.get(key)


@pytest.mark.asyncio
async def test_direct_checkout_wraps_one_wap_trade_in_a_short_lived_session():
    redis = _FakeRedis()
    direct = SimpleNamespace(
        config=SimpleNamespace(
            gateway_url="https://openapi.alipay.test/gateway.do",
            return_base_url="https://web.test.example",
        ),
        create_payment_url=Mock(
            return_value={
                "code": 1,
                "data": {
                    "payurl": "https://openapi.alipay.test/gateway.do?signed=secret"
                },
            }
        ),
    )

    result = await create_alipay_checkout_payment(
        alipay_service=direct,
        redis=redis,
        out_trade_no="RMB_100_1_123",
        public_order_id="bo_public_1",
        subject="内门弟子（30天）",
        amount="30.00",
        token_factory=lambda: "checkout-token",
        ttl_seconds=1800,
    )

    assert result == {
        "code": 1,
        "data": {"payurl": "https://web.test.example/pay/alipay/checkout-token"},
    }
    direct.create_payment_url.assert_called_once_with(
        out_trade_no="RMB_100_1_123",
        subject="内门弟子（30天）",
        amount="30.00",
        product="wap",
        return_url="https://web.test.example/pay/alipay/checkout-token",
    )
    assert len(redis.values) == 1
    redis_key = next(iter(redis.values))
    assert "checkout-token" not in redis_key
    assert redis.ttls[redis_key] == 1800
    stored = json.loads(redis.values[redis_key])
    assert stored["pay_url"].startswith("https://openapi.alipay.test/")

    session = await load_alipay_checkout_session("checkout-token", redis=redis)
    assert session is not None
    assert session.public_order_id == "bo_public_1"
    assert session.out_trade_no == "RMB_100_1_123"
    assert session.amount == "30.00"
    assert session.subject == "内门弟子（30天）"


@pytest.mark.asyncio
async def test_direct_checkout_rejects_an_untrusted_launch_host():
    redis = _FakeRedis()
    direct = SimpleNamespace(
        config=SimpleNamespace(
            gateway_url="https://openapi.alipay.test/gateway.do",
            return_base_url="https://web.test.example",
        ),
        create_payment_url=Mock(
            return_value={
                "code": 1,
                "data": {"payurl": "https://attacker.example/pay"},
            }
        ),
    )

    with pytest.raises(ValueError, match="trusted Alipay gateway"):
        await create_alipay_checkout_payment(
            alipay_service=direct,
            redis=redis,
            out_trade_no="RMB_100_1_123",
            public_order_id="bo_public_1",
            subject="Plan",
            amount="30.00",
        )

    assert redis.values == {}


@pytest.mark.asyncio
async def test_checkout_loader_rejects_a_malformed_bearer_token():
    with pytest.raises(ValueError, match="Invalid Alipay checkout token"):
        await load_alipay_checkout_session("bad", redis=_FakeRedis())
