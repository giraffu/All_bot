from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.telegram_identity_service import (
    resolve_internal_user_id_for_telegram,
)


@pytest.mark.asyncio
async def test_resolve_internal_user_id_uses_one_explicit_telegram_identity_seam():
    get_or_create = AsyncMock(return_value=(SimpleNamespace(id=987), False))

    internal_user_id = await resolve_internal_user_id_for_telegram(
        123456,
        "alice",
        "Alice",
        "zh-hans",
        get_or_create_user_func=get_or_create,
    )

    assert internal_user_id == 987
    get_or_create.assert_awaited_once_with(
        123456,
        "alice",
        "Alice",
        "zh-hans",
    )
