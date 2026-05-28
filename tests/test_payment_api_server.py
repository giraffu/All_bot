from unittest.mock import Mock

import pytest

from src import payment_api_server


@pytest.mark.asyncio
async def test_register_payment_api_providers_invokes_provider_setup(monkeypatch):
    ensure_mock = Mock()
    monkeypatch.setattr(
        payment_api_server,
        "ensure_billing_core_providers_registered",
        ensure_mock,
    )

    await payment_api_server.register_payment_api_providers()

    ensure_mock.assert_called_once_with()
