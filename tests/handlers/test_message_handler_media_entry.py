from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.handlers.message_handler_media_entry import (
    UNSUPPORTED_DOCUMENT_MESSAGE,
    UNSUPPORTED_VIDEO_MESSAGE,
    build_media_update_handler,
    handle_media_update_impl,
)


@pytest.mark.asyncio
async def test_handle_media_update_impl_forwards_common_dependencies():
    handle_media_entry = AsyncMock(return_value="handled")
    update = SimpleNamespace(message=SimpleNamespace())
    context = SimpleNamespace(user_data={})
    template_handler = AsyncMock()
    photo_idle_handler = AsyncMock()
    media_message_handler = AsyncMock()
    is_mentioned = MagicMock(return_value=True)
    ensure_access = AsyncMock(return_value=True)

    result = await handle_media_update_impl(
        update,
        context,
        handle_media_entry=handle_media_entry,
        is_mentioned=is_mentioned,
        ensure_access_and_reward=ensure_access,
        on_template_contribution=template_handler,
        on_photo_idle=photo_idle_handler,
        handle_media_message_fn=media_message_handler,
        unsupported_message=UNSUPPORTED_VIDEO_MESSAGE,
    )

    assert result == "handled"
    handle_media_entry.assert_awaited_once_with(
        update,
        context,
        unsupported_message=UNSUPPORTED_VIDEO_MESSAGE,
        is_mentioned=is_mentioned,
        ensure_access_and_reward=ensure_access,
        on_template_contribution=template_handler,
        on_photo_idle=photo_idle_handler,
        handle_media_message_fn=media_message_handler,
    )


def test_media_entry_unsupported_messages_are_stable():
    assert UNSUPPORTED_VIDEO_MESSAGE == "⚠️ 当前模式不支持视频处理。"
    assert (
        UNSUPPORTED_DOCUMENT_MESSAGE
        == "⚠️ 请发送压缩后的图片或视频格式，不要发送原图/文件。"
    )


@pytest.mark.asyncio
async def test_build_media_update_handler_binds_impl_and_preserves_name():
    handle_media_entry = AsyncMock(return_value="handled")
    update = SimpleNamespace(message=SimpleNamespace())
    context = SimpleNamespace(user_data={})
    template_handler = AsyncMock()
    photo_idle_handler = AsyncMock()
    media_message_handler = AsyncMock()
    is_mentioned = MagicMock(return_value=True)
    ensure_access = AsyncMock(return_value=True)

    handler = build_media_update_handler(
        handler_name="handle_video",
        handle_media_entry=handle_media_entry,
        unsupported_message=UNSUPPORTED_VIDEO_MESSAGE,
        is_mentioned=is_mentioned,
        ensure_access_and_reward=ensure_access,
        on_template_contribution=template_handler,
        on_photo_idle=photo_idle_handler,
        handle_media_message_fn=media_message_handler,
    )

    result = await handler(update, context)

    assert handler.__name__ == "handle_video"
    assert result == "handled"
    handle_media_entry.assert_awaited_once_with(
        update,
        context,
        unsupported_message=UNSUPPORTED_VIDEO_MESSAGE,
        is_mentioned=is_mentioned,
        ensure_access_and_reward=ensure_access,
        on_template_contribution=template_handler,
        on_photo_idle=photo_idle_handler,
        handle_media_message_fn=media_message_handler,
    )
