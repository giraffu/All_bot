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
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=7, username="dao"))
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
