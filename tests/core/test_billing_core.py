from unittest.mock import AsyncMock, patch

import pytest

from src.core import billing_core
from src.core.exceptions import InsufficientCreditsError


@pytest.mark.asyncio
async def test_check_and_deduct_credits_uses_atomic_deduct_without_precheck():
    with (
        patch.object(
            billing_core.quota_manager, "deduct_credits", new=AsyncMock()
        ) as mock_deduct,
        patch.object(
            billing_core.quota_manager, "check_credits", new=AsyncMock()
        ) as mock_check,
        patch.object(
            billing_core.quota_manager, "get_credits", new=AsyncMock()
        ) as mock_get,
    ):
        success, message = await billing_core.check_and_deduct_credits(
            123, 5, "test_task", "tester"
        )

        assert success is True
        assert message == ""
        mock_deduct.assert_awaited_once_with(
            123, 5, username="tester", task_type="test_task"
        )
        mock_check.assert_not_called()
        mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_check_and_deduct_credits_returns_atomic_insufficient_message():
    with (
        patch.object(
            billing_core.quota_manager,
            "deduct_credits",
            new=AsyncMock(
                side_effect=InsufficientCreditsError(current=3, cost=5)
            ),
        ) as mock_deduct,
        patch.object(
            billing_core.quota_manager, "check_credits", new=AsyncMock()
        ) as mock_check,
        patch.object(
            billing_core.quota_manager, "get_credits", new=AsyncMock()
        ) as mock_get,
    ):
        success, message = await billing_core.check_and_deduct_credits(
            123, 5, "test_task", "tester"
        )

        assert success is False
        assert "当前余额: `3` 灵石" in message
        assert "本次需要: `5` 灵石" in message
        mock_deduct.assert_awaited_once()
        mock_check.assert_not_called()
        mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_refund_credits_uses_explicit_add_credits():
    with patch.object(
        billing_core.quota_manager, "add_credits", new=AsyncMock()
    ) as mock_add:
        await billing_core.refund_credits(
            123, 5, task_type="refund_case", username="tester"
        )

        mock_add.assert_awaited_once_with(
            123, 5, username="tester", task_type="refund_case"
        )
