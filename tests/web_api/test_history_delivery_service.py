from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.web_api.services import history_delivery_service


@pytest.mark.asyncio
async def test_send_history_record_to_telegram_requires_bound_telegram():
    with pytest.raises(HTTPException) as exc_info:
        await history_delivery_service.send_history_record_to_telegram(
            task_id="task-1",
            current_user=SimpleNamespace(id=1, telegram_id=None),
            db=SimpleNamespace(),
        )

    assert exc_info.value.status_code == 400
    assert "尚未绑定 Telegram" in exc_info.value.detail


@pytest.mark.asyncio
async def test_send_history_record_to_telegram_delegates_delivery_pipeline(monkeypatch):
    acquire_rate_limit = AsyncMock()
    load_history = AsyncMock(
        return_value=SimpleNamespace(
            output_file="bot-data/history/task-1/output.png",
            type="image",
            prompt="prompt",
        )
    )
    download_bytes = AsyncMock(return_value=("task-1/output.png", b"image-bytes"))
    post_upload = AsyncMock()

    monkeypatch.setattr(
        history_delivery_service,
        "_acquire_send_to_bot_rate_limit",
        acquire_rate_limit,
    )
    monkeypatch.setattr(
        history_delivery_service,
        "_load_owned_history_record",
        load_history,
    )
    monkeypatch.setattr(
        history_delivery_service,
        "_download_history_bytes",
        download_bytes,
    )
    monkeypatch.setattr(
        history_delivery_service,
        "_post_telegram_upload",
        post_upload,
    )

    result = await history_delivery_service.send_history_record_to_telegram(
        task_id="task-1",
        current_user=SimpleNamespace(id=1, telegram_id=10001),
        db=SimpleNamespace(),
    )

    assert result == {"status": "success", "message": "已发送至您的 Telegram 私聊"}
    acquire_rate_limit.assert_awaited_once_with(1)
    load_history.assert_awaited_once()
    download_bytes.assert_awaited_once_with("bot-data/history/task-1/output.png")
    post_upload.assert_awaited_once()
