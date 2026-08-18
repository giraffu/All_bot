import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.media_paths import MINIO_BUCKET
from src.database.models import History
from src.web_api.presenters import media_presenter
from src.web_api.routers import users as users_router


class _FakeResult:
    def __init__(self, single=None):
        self._single = single

    def scalar(self):
        return self._single if isinstance(self._single, int) else 0

    def scalar_one_or_none(self):
        return self._single

    def scalars(self):
        return self

    def all(self):
        if self._single is None or isinstance(self._single, int):
            return []
        return [self._single]


class _FakeSession:
    def __init__(self, history):
        self._history = history
        self.commit = AsyncMock()

    async def execute(self, _stmt):
        return _FakeResult(single=self._history)


@pytest.mark.asyncio
async def test_history_list_lookup_uses_s3_cache_without_public_head(monkeypatch):
    public_probe = AsyncMock(side_effect=AssertionError("public HEAD is forbidden"))
    s3_exists = AsyncMock(return_value=True)
    presign = MagicMock(return_value="https://r2-s3.example/presigned.png")
    monkeypatch.setattr(media_presenter, "r2_public_url_exists", public_probe)
    monkeypatch.setattr(
        media_presenter.storage,
        "async_r2_object_exists",
        s3_exists,
    )
    monkeypatch.setattr(media_presenter, "build_r2_presigned_url", presign)

    results = await asyncio.gather(
        *(
            media_presenter.resolve_history_media_urls(
                task_id=f"task-{index}",
                output_file=f"123/output_images/task-{index}.png",
                history_type="image",
                r2_lookup_strategy="s3_cached",
            )
            for index in range(10)
        )
    )

    assert all(
        output_url == "https://r2-s3.example/presigned.png"
        for output_url, _thumbnail_url in results
    )
    public_probe.assert_not_awaited()


@pytest.mark.asyncio
async def test_history_extra_outputs_accept_explicit_list_lookup_strategy(monkeypatch):
    public_probe = AsyncMock(side_effect=AssertionError("public HEAD is forbidden"))
    monkeypatch.setattr(media_presenter, "r2_public_url_exists", public_probe)
    monkeypatch.setattr(
        media_presenter.storage,
        "async_r2_object_exists",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        media_presenter,
        "build_r2_presigned_url",
        MagicMock(return_value="https://r2-s3.example/last-frame.png"),
    )

    result = await media_presenter.resolve_history_extra_outputs(
        task_id="task-1",
        extra_outputs={"last_frame": {"path": "task-1_last.png"}},
        source="web",
        r2_lookup_strategy="s3_cached",
    )

    assert result["last_frame"]["url"] == "https://r2-s3.example/last-frame.png"
    public_probe.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_history_media_urls_prefers_r2_media_and_thumbnail(monkeypatch):
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

    output_url, thumbnail_url = await media_presenter.resolve_history_media_urls(
        task_id="task-1",
        output_file="123/output_images/task-1.mp4",
        history_type="custom_video",
        r2_lookup_strategy="public_probe",
    )

    assert output_url == "https://r2.example/original.mp4"
    assert thumbnail_url == "https://r2.example/thumb.jpg"
    get_presigned_url.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_history_media_urls_prefers_r2_thumbnail(monkeypatch):
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

    output_url, thumbnail_url = await media_presenter.resolve_history_media_urls(
        task_id="task-1",
        output_file="123/output_images/task-1.png",
        history_type="image",
        r2_lookup_strategy="public_probe",
    )

    assert output_url == "minio-original-url"
    assert thumbnail_url == "https://r2.example/thumb.webp"
    get_presigned_url.assert_called_once_with(
        "123/output_images/task-1.png",
        bucket=MINIO_BUCKET,
    )


@pytest.mark.asyncio
async def test_resolve_history_media_urls_uses_flat_r2_compatibility_key_when_history_key_misses(
    monkeypatch,
):
    get_presigned_url = MagicMock(return_value="minio-original-url")
    r2_probe_calls = []

    async def fake_get_first_r2_url_if_exists(*object_keys, **kwargs):
        r2_probe_calls.append((object_keys, kwargs))
        if object_keys == (
            "history/task-1/original.mp4",
            "123/output_images/task-1.mp4",
            "task-1.mp4",
        ):
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

    output_url, thumbnail_url = await media_presenter.resolve_history_media_urls(
        task_id="task-1",
        output_file="123/output_images/task-1.mp4",
        history_type="custom_video",
        r2_lookup_strategy="public_probe",
    )

    assert output_url == "https://r2.example/task-1.mp4"
    assert thumbnail_url == ""
    assert (
        (
            "history/task-1/original.mp4",
            "123/output_images/task-1.mp4",
            "task-1.mp4",
        ),
        {
            "timeout_seconds": media_presenter.HISTORY_R2_LOOKUP_TIMEOUT_SECONDS,
            "fallback_to_presigned": True,
        },
    ) in r2_probe_calls
    assert (
        (
            "history/task-1/thumb.jpg",
            "123/output_images/task-1_thumb.jpg",
            "task-1_thumb.jpg",
        ),
        {
            "timeout_seconds": media_presenter.HISTORY_R2_LOOKUP_TIMEOUT_SECONDS,
            "fallback_to_presigned": True,
        },
    ) in r2_probe_calls
    get_presigned_url.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_history_media_urls_falls_back_to_minio_thumbnail(monkeypatch):
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

    output_url, thumbnail_url = await media_presenter.resolve_history_media_urls(
        task_id="task-1",
        output_file="123/output_images/task-1.png",
        history_type="image",
        r2_lookup_strategy="public_probe",
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
        MINIO_BUCKET,
        "123/output_images/task-1.png",
        "history/task-1/original.png",
    )

    thumb_call = background_tasks.add_task.call_args_list[1]
    assert thumb_call.args[1:] == (
        "123/output_images/task-1.png",
        "image",
        "history/task-1/thumb.webp",
    )
