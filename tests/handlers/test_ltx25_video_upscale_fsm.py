from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telegram.ext import ConversationHandler

from src.handlers.conversation_states import Ltx25VideoUpscaleState
from src.handlers.fsm import ltx25_video_upscale_fsm as fsm


def _context(**user_data):
    return SimpleNamespace(
        user_data=user_data,
        lang="zh",
        bot=SimpleNamespace(get_file=AsyncMock(return_value=object())),
    )


@pytest.mark.asyncio
async def test_ltx25_upscale_entry_fails_closed(monkeypatch):
    reply = AsyncMock()
    context = _context()
    update = SimpleNamespace(message=SimpleNamespace())
    monkeypatch.setenv("LTX25_VIDEO_UPSCALE_ENABLED", "false")
    monkeypatch.setattr(fsm, "robust_reply_text", reply)

    result = await fsm.start_upscale(update, context)

    assert result == ConversationHandler.END
    assert "in_conversation" not in context.user_data
    reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_ltx25_upscale_rejects_oversized_video_before_download(monkeypatch):
    reply = AsyncMock()
    context = _context(ltx25_video_upscale_data={})
    message = SimpleNamespace(
        video=SimpleNamespace(
            file_id="video-file",
            file_size=fsm.LTX25_VIDEO_UPSCALE_MAX_BYTES + 1,
            duration=5,
        ),
        document=None,
    )
    update = SimpleNamespace(message=message)
    monkeypatch.setattr(fsm, "robust_reply_text", reply)

    result = await fsm.receive_video(update, context)

    assert result == Ltx25VideoUpscaleState.WAIT_VIDEO
    context.bot.get_file.assert_not_awaited()
    reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_ltx25_upscale_rejects_over_twenty_seconds_before_download(monkeypatch):
    reply = AsyncMock()
    context = _context(ltx25_video_upscale_data={})
    message = SimpleNamespace(
        video=SimpleNamespace(file_id="video-file", file_size=1024, duration=21),
        document=None,
    )
    update = SimpleNamespace(message=message)
    monkeypatch.setattr(fsm, "robust_reply_text", reply)

    result = await fsm.receive_video(update, context)

    assert result == Ltx25VideoUpscaleState.WAIT_VIDEO
    context.bot.get_file.assert_not_awaited()
    reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_ltx25_upscale_transfers_temp_file_ownership_to_background_task(
    monkeypatch,
):
    reply = AsyncMock()
    schedule = Mock()
    cleanup = Mock()
    context = _context(
        in_conversation=fsm.LOCK,
        ltx25_video_upscale_data={},
    )
    message = SimpleNamespace(
        video=SimpleNamespace(
            file_id="video-file",
            file_size=1024,
            duration=5,
        ),
        document=None,
        chat_id=456,
        message_id=789,
    )
    update = SimpleNamespace(
        message=message,
        effective_user=SimpleNamespace(id=123, username="tester"),
    )
    monkeypatch.setattr(fsm, "robust_reply_text", reply)
    monkeypatch.setattr(
        fsm,
        "download_telegram_file_to_fsm_temp",
        AsyncMock(return_value="/tmp/ltx25-source.mp4"),
    )
    monkeypatch.setattr(fsm.os.path, "getsize", lambda _path: 1024)
    monkeypatch.setattr(
        fsm, "_probe_video_metadata", lambda _path: (768, 448, 10.125)
    )
    monkeypatch.setattr(
        fsm,
        "process_ltx25_video_upscale_task",
        lambda **kwargs: ("background", kwargs),
    )
    monkeypatch.setattr(fsm, "create_background_task", schedule)
    monkeypatch.setattr(fsm, "cleanup_fsm_temp_files", cleanup)

    result = await fsm.receive_video(update, context)

    assert result == ConversationHandler.END
    scheduled = schedule.call_args.args[1]
    assert scheduled[0] == "background"
    assert scheduled[1]["video_path"] == "/tmp/ltx25-source.mp4"
    assert scheduled[1]["duration_seconds"] == 10
    assert scheduled[1]["resolution"] == "720p"
    assert scheduled[1]["cleanup"] is True
    assert "in_conversation" not in context.user_data
    assert fsm.DATA_KEY not in context.user_data
    cleanup.assert_not_called()
