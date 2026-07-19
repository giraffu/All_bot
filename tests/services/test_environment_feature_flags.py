from src.services import affiliate_redeem_rules, order_v2_service


def test_order_v2_ignores_legacy_test_specific_override(monkeypatch):
    monkeypatch.setenv("ORDER_V2_ENABLED", "false")
    monkeypatch.setenv("ORDER_V2_ENABLED_TEST", "true")

    assert order_v2_service.is_order_v2_enabled() is False


def test_affiliate_flags_only_use_canonical_environment_keys(monkeypatch):
    monkeypatch.setenv("AFFILIATE_MEMBERSHIP_REDEEM_ENABLED", "false")
    monkeypatch.setenv("AFFILIATE_MEMBERSHIP_REDEEM_ENABLED_TEST", "true")
    monkeypatch.setenv("MEMBERSHIP_SETTLEMENT_V2_ENABLED", "true")
    monkeypatch.setenv("MEMBERSHIP_SETTLEMENT_V2_ENABLED_TEST", "false")

    assert affiliate_redeem_rules.is_affiliate_membership_redeem_enabled() is False
    assert affiliate_redeem_rules.is_membership_settlement_v2_enabled() is True
