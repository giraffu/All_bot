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

    dependencies = history_delivery_service.HistoryDeliveryDependencies(
        acquire_rate_limit_func=acquire_rate_limit,
        load_history_record_func=load_history,
        download_history_bytes_func=download_bytes,
        build_upload_request_func=history_delivery_service._build_telegram_upload_request,
        post_upload_func=post_upload,
    )

    result = await history_delivery_service.send_history_record_to_telegram(
        task_id="task-1",
        current_user=SimpleNamespace(id=1, telegram_id=10001),
        db=SimpleNamespace(),
        dependencies=dependencies,
    )

    assert result == {"status": "success", "message": "已发送至您的 Telegram 私聊"}
    acquire_rate_limit.assert_awaited_once_with(1)
    load_history.assert_awaited_once()
    download_bytes.assert_awaited_once_with("bot-data/history/task-1/output.png")
    post_upload.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_current_user_history_record_to_telegram_routes_to_delivery_service():
    service_fn = AsyncMock(return_value={"status": "success"})
    current_user = SimpleNamespace(id=1, telegram_id=10001)
    db = SimpleNamespace()

    result = await history_delivery_service.send_current_user_history_record_to_telegram(
        task_id="task-1",
        current_user=current_user,
        db=db,
        service_fn=service_fn,
    )

    assert result == {"status": "success"}
    service_fn.assert_awaited_once_with(
        task_id="task-1",
        current_user=current_user,
        db=db,
    )
