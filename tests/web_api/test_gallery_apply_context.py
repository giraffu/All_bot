from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from src.database.models import GalleryPost, History
from src.web_api.routers import gallery as gallery_router


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
        "get_media_url",
        lambda *_args, **_kwargs: "media-url",
    )
    monkeypatch.setattr(
        gallery_router,
        "generate_thumbnail_url",
        lambda *_args, **_kwargs: "thumb-url",
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
    assert history.billing_resolution == "720"
    session.commit.assert_awaited_once()


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
    assert history.billing_resolution is None
    session.commit.assert_awaited_once()
