from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.constants import MODE_NONE, MODE_TEMPLATE_CONTRIBUTE
from src.handlers import message_handler_media


def test_resolve_template_upload_meta_handles_photo_video_and_document():
    photo_message = SimpleNamespace(photo=[SimpleNamespace(file_id="photo-1")], video=None, document=None)
    video_message = SimpleNamespace(
        photo=None,
        video=SimpleNamespace(file_id="video-1", file_name="clip.mp4"),
        document=None,
    )
    document_message = SimpleNamespace(
        photo=None,
        video=None,
        document=SimpleNamespace(file_id="doc-1", file_name="archive.zip"),
    )

    assert message_handler_media.resolve_template_upload_meta(photo_message) == (
        "photo-1",
        ".png",
        "图片",
    )
    assert message_handler_media.resolve_template_upload_meta(video_message) == (
        "video-1",
        ".mp4",
        "视频",
    )
    assert message_handler_media.resolve_template_upload_meta(document_message) == (
        "doc-1",
        ".zip",
        "文件",
    )


def test_resolve_template_db_file_type_matches_message_kind():
    assert message_handler_media.resolve_template_db_file_type(
        SimpleNamespace(video=object(), document=None)
    ) == "video"
    assert message_handler_media.resolve_template_db_file_type(
        SimpleNamespace(video=None, document=object())
    ) == "document"
    assert message_handler_media.resolve_template_db_file_type(
        SimpleNamespace(video=None, document=None)
    ) == "photo"


@pytest.mark.asyncio
async def test_handle_media_message_routes_by_mode():
    template_handler = AsyncMock(return_value="template")
    photo_idle_handler = AsyncMock(return_value="idle")
    update = SimpleNamespace(message=SimpleNamespace())

    template_result = await message_handler_media.handle_media_message(
        update,
        SimpleNamespace(user_data={"mode": MODE_TEMPLATE_CONTRIBUTE}),
        on_template_contribution=template_handler,
        on_photo_idle=photo_idle_handler,
    )
    idle_result = await message_handler_media.handle_media_message(
        update,
        SimpleNamespace(user_data={"mode": MODE_NONE}),
        on_template_contribution=template_handler,
        on_photo_idle=photo_idle_handler,
    )

    assert template_result == "template"
    assert idle_result == "idle"
    template_handler.assert_awaited_once()
    photo_idle_handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_media_entry_short_circuits_when_not_mentioned():
    is_mentioned = MagicMock(return_value=False)
    ensure_access = AsyncMock(return_value=True)
    handle_media = AsyncMock()

    result = await message_handler_media.handle_media_entry(
        SimpleNamespace(message=SimpleNamespace()),
        SimpleNamespace(user_data={}),
        is_mentioned=is_mentioned,
        ensure_access_and_reward=ensure_access,
        on_template_contribution=AsyncMock(),
        on_photo_idle=AsyncMock(),
        handle_media_message_fn=handle_media,
    )

    assert result is None
    is_mentioned.assert_called_once()
    ensure_access.assert_not_awaited()
    handle_media.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_media_entry_short_circuits_when_access_denied():
    is_mentioned = MagicMock(return_value=True)
    ensure_access = AsyncMock(return_value=False)
    handle_media = AsyncMock()
    update = SimpleNamespace(message=SimpleNamespace())
    context = SimpleNamespace(user_data={})

    result = await message_handler_media.handle_media_entry(
        update,
        context,
        is_mentioned=is_mentioned,
        ensure_access_and_reward=ensure_access,
        on_template_contribution=AsyncMock(),
        on_photo_idle=AsyncMock(),
        handle_media_message_fn=handle_media,
    )

    assert result is None
    ensure_access.assert_awaited_once_with(update, context)
    handle_media.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_media_entry_forwards_unsupported_message_and_handlers():
    is_mentioned = MagicMock(return_value=True)
    ensure_access = AsyncMock(return_value=True)
    template_handler = AsyncMock()
    photo_idle_handler = AsyncMock()
    handle_media = AsyncMock(return_value="handled")
    update = SimpleNamespace(message=SimpleNamespace())
    context = SimpleNamespace(user_data={})

    result = await message_handler_media.handle_media_entry(
        update,
        context,
        unsupported_message="unsupported",
        is_mentioned=is_mentioned,
        ensure_access_and_reward=ensure_access,
        on_template_contribution=template_handler,
        on_photo_idle=photo_idle_handler,
        handle_media_message_fn=handle_media,
    )

    assert result == "handled"
    handle_media.assert_awaited_once_with(
        update,
        context,
        unsupported_message="unsupported",
        on_template_contribution=template_handler,
        on_photo_idle=photo_idle_handler,
    )


@pytest.mark.asyncio
async def test_handle_template_contribution_saves_upload_and_updates_counter(monkeypatch):
    reply_mock = AsyncMock()
    upload_mock = MagicMock()
    record_mock = AsyncMock()
    logger = MagicMock()
    file_mock = SimpleNamespace(download_to_drive=AsyncMock())
    bot = SimpleNamespace(get_file=AsyncMock(return_value=file_mock))
    message = SimpleNamespace(
        photo=[SimpleNamespace(file_id="photo-1")],
        video=None,
        document=None,
    )
    update = SimpleNamespace(
        message=message,
        effective_user=SimpleNamespace(id=7, username="dao", full_name="Dao User"),
    )
    context = SimpleNamespace(bot=bot, user_data={})

    monkeypatch.setattr(message_handler_media, "robust_reply_text", reply_mock)
    monkeypatch.setattr(message_handler_media.storage, "upload_file", upload_mock)
    monkeypatch.setattr(
        message_handler_media.permission_service,
        "record_contribution",
        record_mock,
    )

    await message_handler_media.handle_template_contribution(update, context, logger)

    bot.get_file.assert_awaited_once_with("photo-1")
    upload_mock.assert_called_once()
    record_mock.assert_awaited_once()
    assert context.user_data["contributed_count"] == 1
    reply_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_template_contribution_blocks_submission_banned_user(monkeypatch):
    reply_mock = AsyncMock()
    logger = MagicMock()
    get_user_mock = AsyncMock(
        return_value=(
            SimpleNamespace(
                id=7,
                is_submission_banned=True,
                submission_ban_reason=None,
            ),
            False,
        )
    )
    update = SimpleNamespace(
        message=SimpleNamespace(photo=[SimpleNamespace(file_id="photo-1")], video=None, document=None),
        effective_user=SimpleNamespace(id=7, username="dao", full_name="Dao"),
    )
    context = SimpleNamespace(bot=SimpleNamespace(), user_data={})

    monkeypatch.setattr(message_handler_media, "robust_reply_text", reply_mock)
    monkeypatch.setattr(message_handler_media, "get_or_create_user_by_telegram", get_user_mock)

    await message_handler_media.handle_template_contribution(update, context, logger)

    get_user_mock.assert_awaited_once_with(7, "dao", "Dao")
    reply_mock.assert_awaited_once_with(
        update.message,
        "⚠️ 违禁被封，请联系管理员解封",
    )
