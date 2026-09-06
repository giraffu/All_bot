from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.telegram_video_permission_service import (
    resolve_telegram_video_permissions,
)


@pytest.mark.asyncio
async def test_resolve_telegram_video_permissions_uses_explicit_dependencies():
    get_user = AsyncMock(return_value=(SimpleNamespace(id=42), False))
    permission_provider = SimpleNamespace(
        get_user_group=AsyncMock(return_value="foundation"),
        get_user_identity=AsyncMock(return_value="vip"),
        get_video_permissions=AsyncMock(return_value=(["512p", "720p"], ["5s", "8s"])),
    )

    permissions = await resolve_telegram_video_permissions(
        12345,
        get_or_create_user_func=get_user,
        permission_provider=permission_provider,
    )

    assert permissions.internal_user_id == 42
    assert permissions.user_group == "foundation"
    assert permissions.user_identity == "vip"
    assert permissions.allowed_resolutions == ("512p", "720p")
    assert permissions.allowed_durations == ("5s", "8s")
    get_user.assert_awaited_once_with(12345)
    permission_provider.get_video_permissions.assert_awaited_once_with(
        42,
        user_group="foundation",
        user_identity="vip",
    )
