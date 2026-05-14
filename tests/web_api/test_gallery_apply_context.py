from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.database.models import GalleryPost, History
from src.web_api.routers import gallery as gallery_router
from src.core import gallery_core


class _FakeResult:
    def __init__(self, *, single=None, many=None):
        self._single = single
        if many is None:
            self._many = [] if single is None else [single]
        else:
            self._many = list(many)

    def scalar_one_or_none(self):
        return self._single

    def scalars(self):
        return self

    def first(self):
        return self._many[0] if self._many else None

    def all(self):
        return list(self._many)


class _FakeSession:
    def __init__(self, results):
        self._results = iter(results)
        self.commit = AsyncMock()
        self.add = MagicMock()

    async def execute(self, _stmt):
        return next(self._results)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_build_post_responses_includes_billing_resolution_for_gallery_lists(
    monkeypatch,
):
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="custom_video",
        prompt="prompt",
        output_file="bot-data/history/task-1/output.mp4",
        width=640,
        height=800,
        duration=8,
    )
    post = GalleryPost(
        id=2,
        task_id="task-1",
        media_type="video",
        width=None,
        height=None,
        duration=None,
        tags="[]",
        likes_count=0,
        dislikes_count=0,
        applied_count=0,
        is_active=True,
        created_at=datetime.now(),
    )
    session = _FakeSession([_FakeResult(many=[history])])

    monkeypatch.setattr(
        gallery_router,
        "_pick_gallery_media_urls",
        AsyncMock(return_value=("media-url", "thumb-url")),
    )

    responses = await gallery_router._build_post_responses(session, [post], None)

    assert len(responses) == 1
    assert responses[0].billing_resolution == "720"
    assert responses[0].media_url == "media-url"
    assert responses[0].thumbnail_url == "thumb-url"


@pytest.mark.asyncio
async def test_get_apply_context_backfills_missing_portrait_video_billing_resolution(
    monkeypatch,
):
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="custom_video",
        prompt="prompt",
        width=640,
        height=800,
        duration=8,
    )
    post = GalleryPost(
        id=2,
        task_id="task-1",
        media_type="video",
        width=None,
        height=None,
        duration=None,
    )
    session = _FakeSession(
        [
            _FakeResult(single=post),
            _FakeResult(many=[history]),
        ]
    )

    monkeypatch.setattr(gallery_router, "AsyncSessionLocal", lambda: session)

    response = await gallery_router.get_apply_context(
        2,
        current_user=type("User", (), {"id": 123})(),
    )

    assert response.post_id == 2
    assert response.source_post_id == 2
    assert response.billing_resolution == "720"
    assert response.width == 640
    assert response.height == 800
    assert response.duration == 8
    assert history.billing_resolution is None
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_apply_context_clears_non_video_billing_resolution(monkeypatch):
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="image",
        prompt="prompt",
        billing_resolution="720",
        width=1024,
        height=1024,
    )
    post = GalleryPost(
        id=2,
        task_id="task-1",
        media_type="image",
        width=1024,
        height=1024,
        duration=None,
    )
    session = _FakeSession(
        [
            _FakeResult(single=post),
            _FakeResult(many=[history]),
        ]
    )

    monkeypatch.setattr(gallery_router, "AsyncSessionLocal", lambda: session)

    response = await gallery_router.get_apply_context(
        2,
        current_user=type("User", (), {"id": 123})(),
    )

    assert response.billing_resolution is None
    assert history.billing_resolution == "720"
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_pick_gallery_media_urls_prefers_existing_history_task_key(
    monkeypatch,
):
    monkeypatch.setattr(
        gallery_router.storage,
        "get_r2_public_url",
        lambda key: f"https://cdn.example/{key}",
    )
    async_exists_mock = AsyncMock(side_effect=[True, True])
    monkeypatch.setattr(gallery_router.storage, "async_r2_object_exists", async_exists_mock)

    media_url, thumbnail_url = await gallery_router._pick_gallery_media_urls(
        task_id="task-1",
        output_file="123/output_images/task-1.png",
        media_type="image",
    )

    assert media_url == "https://cdn.example/history/task-1/original.png"
    assert thumbnail_url == "https://cdn.example/history/task-1/thumb.webp"
    assert async_exists_mock.await_count == 2


@pytest.mark.asyncio
async def test_pick_gallery_media_urls_falls_back_to_legacy_keys_when_history_keys_missing(
    monkeypatch,
):
    monkeypatch.setattr(
        gallery_router.storage,
        "get_r2_public_url",
        lambda key: f"https://cdn.example/{key}",
    )
    async_exists_mock = AsyncMock(side_effect=[False, True, False, True])
    monkeypatch.setattr(gallery_router.storage, "async_r2_object_exists", async_exists_mock)

    media_url, thumbnail_url = await gallery_router._pick_gallery_media_urls(
        task_id="task-1",
        output_file="123/output_images/task-1.png",
        media_type="image",
    )

    assert media_url == "https://cdn.example/task-1.png"
    assert thumbnail_url == "https://cdn.example/task-1_thumb.webp"
    assert async_exists_mock.await_count == 4


@pytest.mark.asyncio
async def test_pick_gallery_media_urls_falls_back_to_storage_paths_when_r2_missing(
    monkeypatch,
):
    monkeypatch.setattr(
        gallery_router.storage,
        "get_r2_public_url",
        lambda key: f"https://cdn.example/{key}",
    )
    async_exists_mock = AsyncMock(return_value=False)
    monkeypatch.setattr(gallery_router.storage, "async_r2_object_exists", async_exists_mock)

    media_url, thumbnail_url = await gallery_router._pick_gallery_media_urls(
        task_id="task-1",
        output_file="123/output_images/task-1.png",
        media_type="image",
    )

    assert media_url == "123/output_images/task-1.png"
    assert thumbnail_url == "123/output_images/task-1_thumb.webp"
    assert async_exists_mock.await_count == 4


@pytest.mark.asyncio
async def test_build_post_responses_uses_r2_fallback_chain(monkeypatch):
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="image",
        prompt="prompt",
        output_file="123/output_images/task-1.png",
        width=1024,
        height=1024,
    )
    post = GalleryPost(
        id=2,
        task_id="task-1",
        media_type="image",
        width=1024,
        height=1024,
        duration=None,
        tags="[]",
        likes_count=0,
        dislikes_count=0,
        applied_count=0,
        is_active=True,
        created_at=datetime.now(),
    )
    session = _FakeSession([_FakeResult(many=[history])])

    monkeypatch.setattr(
        gallery_router.storage,
        "get_r2_public_url",
        lambda key: f"https://cdn.example/{key}",
    )
    monkeypatch.setattr(
        gallery_router.storage,
        "async_r2_object_exists",
        AsyncMock(side_effect=[False, True, False, True]),
    )

    responses = await gallery_router._build_post_responses(session, [post], None)

    assert len(responses) == 1
    assert responses[0].media_url == "https://cdn.example/task-1.png"
    assert responses[0].thumbnail_url == "https://cdn.example/task-1_thumb.webp"


@pytest.mark.asyncio
async def test_process_submit_to_gallery_uses_history_r2_keys(monkeypatch):
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="i2i_pro",
        prompt="prompt",
        output_file="123/output_images/task-1.png",
        allow_contribute=True,
    )
    user = type("User", (), {"id": 123, "total_contributions": 0})()

    existing_result = _FakeResult(many=[])
    history_result = _FakeResult(many=[history])
    user_result = _FakeResult(single=user)
    session = _FakeSession([existing_result, history_result, user_result])
    background_tasks = MagicMock()

    monkeypatch.setattr(gallery_core, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(
        gallery_core.redis_client,
        "check_gallery_submit_limit",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        gallery_core.redis_client,
        "increment_gallery_submit",
        AsyncMock(),
    )

    result = await gallery_core.process_submit_to_gallery(
        user_id=123,
        task_id="task-1",
        background_tasks=background_tasks,
    )

    assert result["status"] == "success"
    assert background_tasks.add_task.call_count == 2

    copy_call = background_tasks.add_task.call_args_list[0]
    assert copy_call.args[2] == "123/output_images/task-1.png"
    assert copy_call.args[3] == "history/task-1/original.png"

    thumb_call = background_tasks.add_task.call_args_list[1]
    assert thumb_call.args[1] == "123/output_images/task-1.png"
    assert thumb_call.args[2] == "image"
    assert thumb_call.args[3] == "history/task-1/thumb.webp"
