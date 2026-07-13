from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.qqcc_runtime_context import (
    get_private_qqcc_bot_id,
    is_qqcc_bot_context,
    is_private_qqcc_bot_context,
    load_qqcc_config_for_context,
)


@pytest.mark.asyncio
async def test_private_qqcc_context_uses_injected_tenant_config_loader():
    loader = AsyncMock(return_value={"global_enabled": False})
    context = SimpleNamespace(
        bot_data={
            "bot_client_type": "bot:qqcc-private:7",
            "private_qqcc_bot_id": 7,
            "qqcc_config_loader": loader,
        }
    )

    config = await load_qqcc_config_for_context(context)

    assert config == {"global_enabled": False}
    assert is_qqcc_bot_context(context) is True
    assert is_private_qqcc_bot_context(context) is True
    assert get_private_qqcc_bot_id(context) == 7
    loader.assert_awaited_once_with()


def test_private_qqcc_context_rejects_mismatched_instance_identity():
    context = SimpleNamespace(
        bot_data={
            "bot_client_type": "bot:qqcc-private:8",
            "private_qqcc_bot_id": 7,
        }
    )

    assert get_private_qqcc_bot_id(context) is None
    assert is_qqcc_bot_context(context) is False


@pytest.mark.asyncio
async def test_private_qqcc_context_fails_closed_when_tenant_config_is_unavailable():
    context = SimpleNamespace(
        bot_data={
            "bot_client_type": "bot:qqcc-private:7",
            "private_qqcc_bot_id": 7,
            "qqcc_config_loader": AsyncMock(side_effect=RuntimeError("db down")),
        }
    )

    with pytest.raises(RuntimeError, match="db down"):
        await load_qqcc_config_for_context(context)
