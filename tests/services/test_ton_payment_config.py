import pytest

from src.services import ton_payment_config, usdt_ton_payment_config


VALID_TON_ADDRESS = "UQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAJKZ"


@pytest.mark.parametrize("value", [None, "", "not-a-ton-address"])
def test_enabled_ton_fails_closed_for_missing_or_invalid_merchant(monkeypatch, value):
    monkeypatch.setenv("TON_PAYMENT_POLLING_ENABLED", "true")
    if value is None:
        monkeypatch.delenv("VITE_MERCHANT_ADDRESS", raising=False)
    else:
        monkeypatch.setenv("VITE_MERCHANT_ADDRESS", value)

    availability = ton_payment_config.get_ton_payment_availability()

    assert availability.requested_enabled is True
    assert availability.enabled is False
    assert availability.merchant_address is None


def test_disabled_ton_ignores_merchant_and_exposes_no_receiver(monkeypatch):
    monkeypatch.setenv("TON_PAYMENT_POLLING_ENABLED", "false")
    monkeypatch.setenv("VITE_MERCHANT_ADDRESS", VALID_TON_ADDRESS)

    availability = ton_payment_config.get_ton_payment_availability()

    assert availability.enabled is False
    assert availability.merchant_address is None


def test_enabled_ton_returns_validated_canonical_merchant(monkeypatch):
    monkeypatch.setenv("TON_PAYMENT_POLLING_ENABLED", "true")
    monkeypatch.setenv("VITE_MERCHANT_ADDRESS", "0:" + "0" * 64)

    availability = ton_payment_config.get_ton_payment_availability()

    assert availability.enabled is True
    assert availability.merchant_address == VALID_TON_ADDRESS


def test_enabled_usdt_ton_uses_official_master_and_validated_merchant(monkeypatch):
    monkeypatch.setenv("USDT_TON_PAYMENT_ENABLED", "true")
    monkeypatch.setenv("VITE_MERCHANT_ADDRESS", "0:" + "0" * 64)

    availability = usdt_ton_payment_config.get_usdt_ton_payment_availability()

    assert availability.enabled is True
    assert availability.merchant_address == VALID_TON_ADDRESS
    assert (
        availability.jetton_master_address
        == "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs"
    )


def test_enabled_usdt_ton_fails_closed_without_merchant(monkeypatch):
    monkeypatch.setenv("USDT_TON_PAYMENT_ENABLED", "true")
    monkeypatch.delenv("VITE_MERCHANT_ADDRESS", raising=False)

    availability = usdt_ton_payment_config.get_usdt_ton_payment_availability()

    assert availability.requested_enabled is True
    assert availability.enabled is False
    assert availability.merchant_address is None
