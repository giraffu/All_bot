from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.web_api.routers import payment as payment_router
from src.web_api.services import payment_api_service


VALID_TON_ADDRESS = "UQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAJKZ"


def _enable_ton(monkeypatch):
    monkeypatch.setattr(
        payment_api_service,
        "get_ton_payment_availability",
        lambda: SimpleNamespace(enabled=True, merchant_address=VALID_TON_ADDRESS),
    )


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        if isinstance(self._value, list):
            return self._value
        return [self._value]


class _FakeSession:
    def __init__(self, execute_results):
        self.execute_results = list(execute_results)
        self.added = []
        self.commit = AsyncMock()

    async def execute(self, _stmt):
        if not self.execute_results:
            raise AssertionError("unexpected execute call")
        return _ScalarResult(self.execute_results.pop(0))

    def add(self, obj):
        self.added.append(obj)


def _build_plan():
    return SimpleNamespace(
        id=1,
        name="RMB Plan",
        is_active=True,
        price_rmb=Decimal("19.90"),
        price_ton=Decimal("1.10"),
        duration_days=30,
        identity_name="内门弟子",
        reward_credits=100,
    )


@pytest.mark.asyncio
async def test_get_plans_preserves_frontend_contract_fields():
    db = _FakeSession([[_build_plan()]])

    result = await payment_api_service.get_payment_plans_payload(
        db=db,
        availability=SimpleNamespace(
            enabled=True,
            merchant_address=VALID_TON_ADDRESS,
        ),
    )

    assert result["code"] == 0
    assert result["message"] == "success"
    assert "ton_receiver_address" in result["data"]
    assert result["data"]["ton_payment_enabled"] is True
    assert len(result["data"]["plans"]) == 1
    assert result["data"]["plans"][0]["id"] == 1
    assert result["data"]["plans"][0]["price_rmb"] == 19.9
    assert result["data"]["plans"][0]["price_ton"] == 1.1
    assert result["data"]["plans"][0]["credits_granted"] == 100
    assert result["data"]["plans"][0]["type"] == "monthly"


@pytest.mark.asyncio
async def test_get_plans_uses_configured_ton_receiver(monkeypatch):
    db = _FakeSession([[_build_plan()]])
    _enable_ton(monkeypatch)

    result = await payment_router.get_plans(db=db)

    assert result["data"]["ton_receiver_address"] == VALID_TON_ADDRESS


@pytest.mark.asyncio
async def test_get_plans_disables_ton_when_merchant_is_unavailable():
    db = _FakeSession([[_build_plan()]])

    result = await payment_api_service.get_payment_plans_payload(
        db=db,
        availability=SimpleNamespace(enabled=False, merchant_address=None),
    )

    assert result["data"]["ton_payment_enabled"] is False
    assert result["data"]["ton_receiver_address"] is None


@pytest.mark.asyncio
async def test_create_order_dual_writes_business_order_id(monkeypatch):
    db = _FakeSession([_build_plan()])
    request = SimpleNamespace(headers={"origin": "https://test.example"})
    current_user = SimpleNamespace(id=2002)

    monkeypatch.setattr(
        payment_api_service.RMBPaymentService,
        "create_payment_url",
        AsyncMock(return_value={"code": 1, "payurl": "https://pay.example"}),
    )
    monkeypatch.setattr(
        payment_api_service, "generate_business_order_id", lambda: "bo_test_1"
    )

    result = await payment_router.create_order(
        payment_router.CreateOrderRequest(plan_id=1, pay_type="alipay"),
        request=request,
        current_user=current_user,
        db=db,
    )

    created_order = db.added[0]
    assert created_order.business_order_id == "bo_test_1"
    assert created_order.internal_user_id == 2002
    assert created_order.settlement_schema_version == "order_plan_v1"
    assert created_order.settlement_snapshot["plan_id"] == 1
    assert result["data"]["order_id"] == "bo_test_1"
    assert result["data"]["legacy_order_id"].startswith("WEB_")
    payment_api_service.RMBPaymentService.create_payment_url.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_order_supports_nested_gateway_payurl_payload(monkeypatch):
    db = _FakeSession([_build_plan()])
    request = SimpleNamespace(headers={"origin": "https://test.example"})
    current_user = SimpleNamespace(id=2002)

    monkeypatch.setattr(
        payment_api_service.RMBPaymentService,
        "create_payment_url",
        AsyncMock(
            return_value={
                "code": 1,
                "data": {
                    "payurl": "https://pay.example/submit.php?foo=bar baz&biz=value"
                },
            }
        ),
    )
    monkeypatch.setattr(
        payment_api_service, "generate_business_order_id", lambda: "bo_nested_1"
    )

    result = await payment_router.create_order(
        payment_router.CreateOrderRequest(plan_id=1, pay_type="alipay"),
        request=request,
        current_user=current_user,
        db=db,
    )

    assert result["data"]["order_id"] == "bo_nested_1"
    assert (
        result["data"]["pay_url"]
        == "https://pay.example/submit.php?foo=bar+baz&biz=value"
    )


@pytest.mark.asyncio
async def test_get_order_status_supports_business_order_id():
    order = SimpleNamespace(
        order_id="WEB_legacy",
        business_order_id="bo_status_1",
        internal_user_id=2002,
        status="PENDING",
    )
    db = _FakeSession([order])
    current_user = SimpleNamespace(id=2002)

    result = await payment_router.get_order_status(
        "bo_status_1",
        current_user=current_user,
        db=db,
    )

    assert result["data"]["order_id"] == "bo_status_1"
    assert result["data"]["legacy_order_id"] == "WEB_legacy"


@pytest.mark.asyncio
async def test_create_ton_order_returns_order_v2_comment_when_enabled(monkeypatch):
    db = _FakeSession([_build_plan()])
    current_user = SimpleNamespace(id=2002, telegram_id=12345)

    monkeypatch.setattr(
        payment_api_service, "generate_business_order_id", lambda: "bo_ton_1"
    )
    monkeypatch.setattr(payment_api_service, "is_order_v2_enabled", lambda: True)
    _enable_ton(monkeypatch)

    result = await payment_router.create_ton_order(
        payment_router.CreateTonOrderRequest(plan_id=1),
        current_user=current_user,
        db=db,
    )

    created_order = db.added[0]
    assert created_order.business_order_id == "bo_ton_1"
    assert created_order.internal_user_id == 2002
    assert created_order.payment_channel == "TON"
    assert result["data"]["order_id"] == "bo_ton_1"
    assert result["data"]["ton_comment"] == "ORDER_V2:bo_ton_1"
    assert result["data"]["amount_nanotons"] == "1100000000"


@pytest.mark.asyncio
async def test_create_ton_order_uses_configured_ton_receiver(monkeypatch):
    db = _FakeSession([_build_plan()])
    current_user = SimpleNamespace(id=2002, telegram_id=12345)

    monkeypatch.setattr(
        payment_api_service, "generate_business_order_id", lambda: "bo_ton_receiver"
    )
    monkeypatch.setattr(payment_api_service, "is_order_v2_enabled", lambda: True)
    _enable_ton(monkeypatch)

    result = await payment_router.create_ton_order(
        payment_router.CreateTonOrderRequest(plan_id=1),
        current_user=current_user,
        db=db,
    )

    assert result["data"]["ton_receiver_address"] == VALID_TON_ADDRESS


@pytest.mark.asyncio
async def test_create_ton_order_fails_before_query_or_pending_order_when_unavailable(
    monkeypatch,
):
    db = _FakeSession([])
    current_user = SimpleNamespace(id=2002, telegram_id=12345)
    monkeypatch.setattr(
        payment_api_service,
        "get_ton_payment_availability",
        lambda: SimpleNamespace(enabled=False, merchant_address=None),
    )

    with pytest.raises(Exception) as exc_info:
        await payment_router.create_ton_order(
            payment_router.CreateTonOrderRequest(plan_id=1),
            current_user=current_user,
            db=db,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["reason"] == "TON_PAYMENT_UNAVAILABLE"
    assert db.added == []
    db.commit.assert_not_awaited()
