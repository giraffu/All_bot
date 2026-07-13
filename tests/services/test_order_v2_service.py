from types import SimpleNamespace

from src.services.order_v2_service import (
    build_legacy_order_payload,
    build_order_v2_payload,
    get_order_public_id,
    parse_order_payload,
)


def test_parse_order_payload_supports_legacy_and_v2():
    legacy = parse_order_payload("ORDER:12345:9:999")
    assert legacy.kind == "legacy"
    assert legacy.telegram_user_id == 12345
    assert legacy.plan_id == 9
    assert legacy.timestamp == 999

    v2 = parse_order_payload("ORDER_V2:bo_123")
    assert v2.kind == "v2"
    assert v2.business_order_id == "bo_123"


def test_order_payload_builders_and_public_id():
    assert build_legacy_order_payload(
        telegram_user_id=12345, plan_id=8, timestamp=777
    ) == "ORDER:12345:8:777"
    assert build_order_v2_payload("bo_abc") == "ORDER_V2:bo_abc"

    order = SimpleNamespace(order_id="legacy_1", business_order_id="bo_1")
    assert get_order_public_id(order) == "bo_1"

    legacy_only = SimpleNamespace(order_id="legacy_2", business_order_id=None)
    assert get_order_public_id(legacy_only) == "legacy_2"
