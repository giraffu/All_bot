from __future__ import annotations

import os
from dataclasses import dataclass

from pytoniq_core import Address


_TRUE_VALUES = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class TonPaymentAvailability:
    requested_enabled: bool
    enabled: bool
    merchant_address: str | None
    error_reason: str | None = None


def is_ton_payment_polling_requested() -> bool:
    return os.getenv("TON_PAYMENT_POLLING_ENABLED", "false").strip().lower() in (
        _TRUE_VALUES
    )


def validate_ton_merchant_address(value: str | None) -> str:
    raw_value = str(value or "").strip()
    if not raw_value:
        raise ValueError("TON merchant address is required")
    try:
        address = Address(raw_value)
    except Exception as exc:
        raise ValueError("TON merchant address is invalid") from exc
    return address.to_str(
        is_user_friendly=True,
        is_url_safe=True,
        is_bounceable=False,
    )


def resolve_ton_merchant_address() -> str:
    return validate_ton_merchant_address(os.getenv("VITE_MERCHANT_ADDRESS"))


def get_ton_payment_availability() -> TonPaymentAvailability:
    requested_enabled = is_ton_payment_polling_requested()
    if not requested_enabled:
        return TonPaymentAvailability(
            requested_enabled=False,
            enabled=False,
            merchant_address=None,
        )
    try:
        merchant_address = resolve_ton_merchant_address()
    except ValueError as exc:
        return TonPaymentAvailability(
            requested_enabled=True,
            enabled=False,
            merchant_address=None,
            error_reason=str(exc),
        )
    return TonPaymentAvailability(
        requested_enabled=True,
        enabled=True,
        merchant_address=merchant_address,
    )
