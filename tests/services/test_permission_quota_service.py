from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.permission_quota_service import PermissionQuotaService


@pytest.mark.asyncio
async def test_bot_quota_precheck_uses_the_same_runtime_task_price(monkeypatch):
    quota = SimpleNamespace(
        check_credits=AsyncMock(return_value=True),
        get_credits=AsyncMock(return_value=99),
    )
    resolve_price = AsyncMock(return_value=0)
    service = PermissionQuotaService(
        quota,
        resolve_task_cost_func=resolve_price,
    )
    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=77), False)),
    )

    assert await service.check_quota(
        123,
        "tester",
        "Tester",
        cost=9,
        task_type="txt2img",
        client_type="bot",
    ) is True

    resolve_price.assert_awaited_once_with(
        task_type="txt2img",
        inputs={},
        client_type="bot",
        default_cost=9,
    )
    quota.check_credits.assert_awaited_once_with(77, 0)
