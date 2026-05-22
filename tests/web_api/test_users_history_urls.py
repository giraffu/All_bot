from unittest.mock import AsyncMock, MagicMock

import pytest

from src.database.models import History
from src.web_api.presenters import media_presenter
from src.web_api.services import users_history_service
from src.web_api.routers import users as users_router


class _FakeResult:
    def __init__(self, single=None):
        self._single = single

    def scalar_one_or_none(self):
        return self._single


class _FakeSession:
    def __init__(self, history):
        self._history = history
        self.commit = AsyncMock()

    async def execute(self, _stmt):
        return _FakeResult(single=self._history)


@pytest.mark.asyncio
async def test_pick_history_media_urls_prefers_r2_media_and_thumbnail(monkeypatch):
    get_presigned_url = MagicMock(return_value="minio-original-url")

    monkeypatch.setattr(media_presenter.storage, "get_presigned_url", get_presigned_url)
    monkeypatch.setattr(
        media_presenter,
        "get_first_r2_url_if_exists",
        AsyncMock(
            side_effect=[
                "https://r2.example/original.mp4",
                "https://r2.example/thumb.jpg",
            ]
        ),
    )
    monkeypatch.setattr(
        media_presenter.storage,
        "async_object_exists",
        AsyncMock(return_value=True),
    )

    output_url, thumbnail_url = await users_history_service.pick_history_media_urls(
        resolve_history_media_urls=media_presenter.resolve_history_media_urls,
        task_id="task-1",
        output_file="123/output_images/task-1.mp4",
        history_type="custom_video",
    )

    assert output_url == "https://r2.example/original.mp4"
    assert thumbnail_url == "https://r2.example/thumb.jpg"
    get_presigned_url.assert_not_called()


@pytest.mark.asyncio
async def test_pick_history_media_urls_prefers_r2_thumbnail(monkeypatch):
    get_presigned_url = MagicMock(return_value="minio-original-url")

    monkeypatch.setattr(media_presenter.storage, "get_presigned_url", get_presigned_url)
    monkeypatch.setattr(
        media_presenter,
        "get_first_r2_url_if_exists",
        AsyncMock(
            side_effect=[
                "",
                "https://r2.example/thumb.webp",
            ]
        ),
    )
    monkeypatch.setattr(
        media_presenter.storage,
        "async_object_exists",
        AsyncMock(return_value=True),
    )

    output_url, thumbnail_url = await users_history_service.pick_history_media_urls(
        resolve_history_media_urls=media_presenter.resolve_history_media_urls,
        task_id="task-1",
        output_file="123/output_images/task-1.png",
        history_type="image",
    )

    assert output_url == "minio-original-url"
    assert thumbnail_url == "https://r2.example/thumb.webp"
    get_presigned_url.assert_called_once_with(
        "123/output_images/task-1.png",
        bucket="bot-data",
    )


@pytest.mark.asyncio
async def test_pick_history_media_urls_uses_legacy_r2_media_key_when_history_key_misses(
    monkeypatch,
):
    get_presigned_url = MagicMock(return_value="minio-original-url")
    r2_probe_calls = []

    async def fake_get_first_r2_url_if_exists(*object_keys):
        r2_probe_calls.append(object_keys)
        if object_keys == ("history/task-1/original.mp4", "task-1.mp4"):
            return "https://r2.example/task-1.mp4"
        return ""

    monkeypatch.setattr(media_presenter.storage, "get_presigned_url", get_presigned_url)
    monkeypatch.setattr(
        media_presenter,
        "get_first_r2_url_if_exists",
        fake_get_first_r2_url_if_exists,
    )
    monkeypatch.setattr(
        media_presenter.storage,
        "async_object_exists",
        AsyncMock(return_value=False),
    )

    output_url, thumbnail_url = await users_history_service.pick_history_media_urls(
        resolve_history_media_urls=media_presenter.resolve_history_media_urls,
        task_id="task-1",
        output_file="123/output_images/task-1.mp4",
        history_type="custom_video",
    )

    assert output_url == "https://r2.example/task-1.mp4"
    assert thumbnail_url == ""
    assert ("history/task-1/original.mp4", "task-1.mp4") in r2_probe_calls
    assert ("history/task-1/thumb.jpg", "task-1_thumb.jpg") in r2_probe_calls
    get_presigned_url.assert_not_called()


@pytest.mark.asyncio
async def test_pick_history_media_urls_falls_back_to_minio_thumbnail(monkeypatch):
    get_presigned_url = MagicMock(
        side_effect=["minio-original-url", "minio-thumb-url"]
    )

    monkeypatch.setattr(media_presenter.storage, "get_presigned_url", get_presigned_url)
    monkeypatch.setattr(
        media_presenter,
        "get_first_r2_url_if_exists",
        AsyncMock(side_effect=["", ""]),
    )
    monkeypatch.setattr(
        media_presenter.storage,
        "async_object_exists",
        AsyncMock(return_value=True),
    )

    output_url, thumbnail_url = await users_history_service.pick_history_media_urls(
        resolve_history_media_urls=media_presenter.resolve_history_media_urls,
        task_id="task-1",
        output_file="123/output_images/task-1.png",
        history_type="image",
    )

    assert output_url == "minio-original-url"
    assert thumbnail_url == "minio-thumb-url"
    assert get_presigned_url.call_count == 2


@pytest.mark.asyncio
async def test_favorite_history_schedules_media_and_thumbnail_background_tasks():
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="image",
        output_file="123/output_images/task-1.png",
        is_favorited=False,
    )
    db = _FakeSession(history)
    background_tasks = MagicMock()
    current_user = type("User", (), {"id": 123})()

    response = await users_router.favorite_history(
        "task-1",
        background_tasks,
        current_user=current_user,
        db=db,
    )

    assert response["status"] == "success"
    assert history.is_favorited is True
    db.commit.assert_awaited_once()
    assert background_tasks.add_task.call_count == 2

    copy_call = background_tasks.add_task.call_args_list[0]
    assert copy_call.args[1:] == (
        "bot-data",
        "123/output_images/task-1.png",
        "history/task-1/original.png",
    )

    thumb_call = background_tasks.add_task.call_args_list[1]
    assert thumb_call.args[1:] == (
        "123/output_images/task-1.png",
        "image",
        "history/task-1/thumb.webp",
    )
