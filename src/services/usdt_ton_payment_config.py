from __future__ import annotations

import os
from dataclasses import dataclass

from src.services.ton_payment_config import validate_ton_merchant_address


_TRUE_VALUES = {"1", "true", "yes", "on"}
USDT_TON_JETTON_MASTER_ADDRESS = (
    "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs"
)
USDT_TON_DECIMALS = 6
USDT_TON_SCALE = 10**USDT_TON_DECIMALS


@dataclass(frozen=True)
class UsdtTonPaymentAvailability:
    requested_enabled: bool
    enabled: bool
    merchant_address: str | None
    jetton_master_address: str
    error_reason: str | None = None


def is_usdt_ton_payment_requested() -> bool:
    return os.getenv("USDT_TON_PAYMENT_ENABLED", "false").strip().lower() in (
        _TRUE_VALUES
    )


def get_usdt_ton_payment_availability() -> UsdtTonPaymentAvailability:
    requested_enabled = is_usdt_ton_payment_requested()
    if not requested_enabled:
        return UsdtTonPaymentAvailability(
            requested_enabled=False,
            enabled=False,
            merchant_address=None,
            jetton_master_address=USDT_TON_JETTON_MASTER_ADDRESS,
        )
    try:
        merchant_address = validate_ton_merchant_address(
            os.getenv("VITE_MERCHANT_ADDRESS")
        )
    except ValueError as exc:
        return UsdtTonPaymentAvailability(
            requested_enabled=True,
            enabled=False,
            merchant_address=None,
            jetton_master_address=USDT_TON_JETTON_MASTER_ADDRESS,
            error_reason=str(exc),
        )
    return UsdtTonPaymentAvailability(
        requested_enabled=True,
        enabled=True,
        merchant_address=merchant_address,
        jetton_master_address=USDT_TON_JETTON_MASTER_ADDRESS,
    )
