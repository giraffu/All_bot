from unittest.mock import AsyncMock, patch

import pytest

from src.database.models import User
from src.web_api.routers.users import get_current_user_credit_ledger
from src.web_api.schemas.user_credit_ledger_schema import (
    CreditLedgerItem,
    CreditLedgerResponse,
)


@pytest.mark.asyncio
async def test_get_current_user_credit_ledger_routes_to_service():
    current_user = User(id=123, username="tester")
    db = AsyncMock()
    expected = CreditLedgerResponse(
        items=[
            CreditLedgerItem(
                id=1,
                operation_type="checkin",
                direction="income",
                credit_change=10,
                current_balance=110,
                created_at="2026-07-03T12:00:00",
                display_context={"reward": 10},
            )
        ],
        total=1,
        page=2,
        page_size=5,
        total_pages=1,
    )

    with patch(
        "src.web_api.routers.users.get_current_user_credit_ledger_payload",
        new=AsyncMock(return_value=expected),
    ) as mock_service:
        response = await get_current_user_credit_ledger(
            current_user=current_user,
            db=db,
            page=2,
            page_size=5,
        )

    assert response == expected
    mock_service.assert_awaited_once_with(
        current_user=current_user,
        db=db,
        page=2,
        page_size=5,
    )
