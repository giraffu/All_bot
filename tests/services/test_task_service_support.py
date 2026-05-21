from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services import task_service_support


def test_normalize_custom_video_resolution_value_maps_known_options():
    assert task_service_support.normalize_custom_video_resolution_value("1024p") == 1024
    assert task_service_support.normalize_custom_video_resolution_value("720p") == 720
    assert task_service_support.normalize_custom_video_resolution_value("anything-else") == 512


def test_normalize_custom_video_duration_value_maps_known_options():
    assert task_service_support.normalize_custom_video_duration_value("10s") == 10
    assert task_service_support.normalize_custom_video_duration_value("8s") == 8
    assert task_service_support.normalize_custom_video_duration_value("anything-else") == 5


@pytest.mark.asyncio
async def test_resolve_custom_video_settings_warns_and_downgrades_invalid_combo():
    reply_text = AsyncMock()
    update = SimpleNamespace(effective_message=SimpleNamespace())
    context = SimpleNamespace(
        user_data={
            "custom_video_resolution": "1024p",
            "custom_video_duration": "10s",
        }
    )

    result = await task_service_support.resolve_custom_video_settings(
        context,
        update=update,
        warn_invalid_combo=True,
        reply_text_func=reply_text,
    )

    assert result == ("720p", "10s", 720, 10)
    assert context.user_data["custom_video_resolution"] == "720p"
    reply_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_custom_video_settings_keeps_defaults_without_warning():
    reply_text = AsyncMock()
    context = SimpleNamespace(user_data={})

    result = await task_service_support.resolve_custom_video_settings(
        context,
        warn_invalid_combo=False,
        reply_text_func=reply_text,
    )

    assert result == ("512p", "5s", 512, 5)
    reply_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_acceleration_notice_only_for_new_users():
    quota_manager = SimpleNamespace(
        get_user_stats=AsyncMock(side_effect=[{"generation_count": 1}, {"generation_count": 2}])
    )

    first_notice = await task_service_support.get_acceleration_notice(
        1,
        quota_manager=quota_manager,
    )
    second_notice = await task_service_support.get_acceleration_notice(
        2,
        quota_manager=quota_manager,
    )

    assert "新手特权" in first_notice
    assert second_notice == ""
