from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException

from src.web_api.services import history_delivery_service


class _FakeResult:
    def __init__(self, many):
        self._many = list(many)

    def scalars(self):
        return self

    def all(self):
        return list(self._many)


class _FakeSession:
    def __init__(self, *results):
        self._results = iter(results)

    async def execute(self, _stmt):
        return next(self._results)


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
async def test_load_owned_history_record_prefers_duplicate_row_with_output_file():
    older_history = SimpleNamespace(
        id=11,
        task_id="task-1",
        user_id=1,
        output_file=None,
        is_visible=False,
        is_favorited=False,
    )
    newer_history = SimpleNamespace(
        id=12,
        task_id="task-1",
        user_id=1,
        output_file="bot-data/history/task-1/output.png",
        is_visible=True,
        is_favorited=False,
    )
    db = _FakeSession(_FakeResult([older_history, newer_history]))

    history = await history_delivery_service._load_owned_history_record("task-1", 1, db)

    assert history is newer_history


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


def test_build_telegram_upload_request_uses_test_token_in_test_mode(monkeypatch):
    monkeypatch.setenv("BOT_TYPE", "TEST")
    monkeypatch.setattr(history_delivery_service, "BOT_TOKEN_TEST", "test-token")
    monkeypatch.setattr(history_delivery_service, "BOT_TOKEN", "prod-token")
    monkeypatch.setattr(
        history_delivery_service,
        "TELEGRAM_API_BASE_URL",
        "https://telegram.example.com",
    )

    url, payload, files = history_delivery_service._build_telegram_upload_request(
        telegram_id=10001,
        history_type="wan22_video_v2",
        history_prompt="prompt",
        object_name="task-1/output.mp4",
        file_bytes=b"video-bytes",
    )

    assert url == "https://telegram.example.com/bottest-token/sendVideo"
    assert payload["chat_id"] == "10001"
    assert files["video"][0] == "output.mp4"


@pytest.mark.parametrize(
    "history_type",
    ["scail2_action_transfer", "scail2_video_replacement"],
)
def test_build_telegram_upload_request_sends_scail2_results_as_video(
    monkeypatch,
    history_type,
):
    monkeypatch.setenv("BOT_TYPE", "PROD")
    monkeypatch.setattr(history_delivery_service, "BOT_TOKEN", "prod-token")
    monkeypatch.setattr(
        history_delivery_service,
        "TELEGRAM_API_BASE_URL",
        "https://telegram.example.com",
    )

    url, _payload, files = history_delivery_service._build_telegram_upload_request(
        telegram_id=10001,
        history_type=history_type,
        history_prompt=None,
        object_name=f"task-1/{history_type}.mp4",
        file_bytes=b"video-bytes",
    )

    assert url == "https://telegram.example.com/botprod-token/sendVideo"
    assert "video" in files
    assert "photo" not in files
    assert files["video"][2] == "video/mp4"


@pytest.mark.asyncio
async def test_post_telegram_upload_returns_clear_error_for_invalid_token():
    request = httpx.Request(
        "POST", "https://telegram.example.com/botinvalid-token/sendPhoto"
    )
    response = httpx.Response(
        401,
        request=request,
        text='{"ok":false,"error_code":401,"description":"Unauthorized: invalid token specified"}',
    )

    async def _raise(*args, **kwargs):
        raise httpx.HTTPStatusError(
            "Unauthorized: invalid token specified",
            request=request,
            response=response,
        )

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        post = _raise

    original_client = history_delivery_service.httpx.AsyncClient
    history_delivery_service.httpx.AsyncClient = _FakeClient
    try:
        with pytest.raises(HTTPException) as exc_info:
            await history_delivery_service._post_telegram_upload(
                "https://telegram.example.com/botinvalid-token/sendPhoto",
                {"chat_id": "10001"},
                {"photo": ("output.png", b"image-bytes", "image/png")},
            )
    finally:
        history_delivery_service.httpx.AsyncClient = original_client

    assert exc_info.value.status_code == 500
    assert "Token" in exc_info.value.detail
