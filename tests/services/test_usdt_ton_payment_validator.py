import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pytoniq_core import begin_cell

from src.services import usdt_ton_payment_validator
from src.services.usdt_ton_payment_config import USDT_TON_JETTON_MASTER_ADDRESS


VALID_TON_ADDRESS = "UQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAJKZ"


def _comment_boc(text: str) -> str:
    cell = begin_cell().store_uint(0, 32).store_snake_string(text).end_cell()
    return base64.b64encode(cell.to_boc()).decode()


class _FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self.payload


class _FakeSession:
    def __init__(self, response, calls):
        self.response = response
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get(self, url, *, params=None, headers=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        return self.response


@pytest.mark.asyncio
async def test_verified_usdt_transfer_fulfills_order_and_advances_checkpoint(
    monkeypatch,
):
    calls = []
    validator = usdt_ton_payment_validator.UsdtTonPaymentValidator(
        SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock())),
        merchant_address=VALID_TON_ADDRESS,
        api_key="secret-key",
    )
    validator._last_lt_loaded = True
    process_order = AsyncMock(return_value=True)
    advance = AsyncMock()
    monkeypatch.setattr(validator, "_process_order", process_order)
    monkeypatch.setattr(validator, "_advance_last_lt", advance)
    monkeypatch.setattr(
        usdt_ton_payment_validator.aiohttp,
        "ClientSession",
        lambda: _FakeSession(
            _FakeResponse(
                {
                    "jetton_transfers": [
                        {
                            "amount": "4500000",
                            "destination": "0:" + "0" * 64,
                            "forward_payload": _comment_boc(
                                "ORDER_V2:bo_usdt_ton_1"
                            ),
                            "forward_ton_amount": "1",
                            "jetton_master": USDT_TON_JETTON_MASTER_ADDRESS,
                            "transaction_aborted": False,
                            "transaction_hash": "usdt-tx-1",
                            "transaction_lt": "42",
                        }
                    ]
                }
            ),
            calls,
        ),
    )

    await validator._check_new_transfers()

    process_order.assert_awaited_once_with(
        "ORDER_V2:bo_usdt_ton_1",
        4_500_000,
        "usdt-tx-1",
    )
    advance.assert_awaited_once_with(42)
    assert calls[0]["params"]["owner_address"] == VALID_TON_ADDRESS
    assert calls[0]["params"]["jetton_master"] == USDT_TON_JETTON_MASTER_ADDRESS
    assert calls[0]["params"]["direction"] == "in"
    assert calls[0]["headers"] == {"X-API-Key": "secret-key"}


@pytest.mark.asyncio
async def test_aborted_or_wrong_master_transfer_never_fulfills(monkeypatch):
    validator = usdt_ton_payment_validator.UsdtTonPaymentValidator(
        SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock())),
        merchant_address=VALID_TON_ADDRESS,
    )
    validator._last_lt_loaded = True
    process_order = AsyncMock()
    advance = AsyncMock()
    monkeypatch.setattr(validator, "_process_order", process_order)
    monkeypatch.setattr(validator, "_advance_last_lt", advance)
    monkeypatch.setattr(
        usdt_ton_payment_validator.aiohttp,
        "ClientSession",
        lambda: _FakeSession(
            _FakeResponse(
                {
                    "jetton_transfers": [
                        {
                            "amount": "4500000",
                            "destination": VALID_TON_ADDRESS,
                            "forward_payload": _comment_boc(
                                "ORDER_V2:bo_usdt_ton_1"
                            ),
                            "forward_ton_amount": "1",
                            "jetton_master": "0:" + "1" * 64,
                            "transaction_aborted": True,
                            "transaction_hash": "fake-usdt-tx",
                            "transaction_lt": "42",
                        }
                    ]
                }
            ),
            [],
        ),
    )

    await validator._check_new_transfers()

    process_order.assert_not_awaited()
    advance.assert_awaited_once_with(42)


def test_usdt_checkpoint_is_scoped_to_merchant_and_official_master():
    validator = usdt_ton_payment_validator.UsdtTonPaymentValidator(
        SimpleNamespace(),
        merchant_address=VALID_TON_ADDRESS,
    )

    assert validator._last_lt_checkpoint_key == (
        f"usdt_ton:{VALID_TON_ADDRESS}:{USDT_TON_JETTON_MASTER_ADDRESS}:last_lt"
    )
