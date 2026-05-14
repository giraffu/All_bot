from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from src.database.models import GalleryPost, History
from src.web_api.routers import users as users_router


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

    def all(self):
        return list(self._many)


class _FakeDB:
    def __init__(self, results):
        self._results = iter(results)
        self.commit = AsyncMock()

    async def execute(self, _stmt):
        return next(self._results)


def test_pick_preferred_gallery_post_prefers_active_and_newer_post():
    now = datetime.now()
    inactive_newest = GalleryPost(
        id=3,
        task_id="task-1",
        is_active=False,
        created_at=now + timedelta(minutes=2),
    )
    active_oldest = GalleryPost(
        id=1,
        task_id="task-1",
        is_active=True,
        created_at=now,
    )
    active_newest = GalleryPost(
        id=2,
        task_id="task-1",
        is_active=True,
        created_at=now + timedelta(minutes=1),
    )

    preferred = users_router._pick_preferred_gallery_post(
        [inactive_newest, active_oldest, active_newest]
    )

    assert preferred is active_newest


@pytest.mark.asyncio
async def test_get_favorite_apply_context_backfills_missing_video_metadata(
    monkeypatch,
):
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="custom_video",
        prompt="prompt",
        output_file="bot-data/history/task-1/output.mp4",
    )
    db = _FakeDB(
        [
            _FakeResult(single=history),
            _FakeResult(many=[]),
        ]
    )

    monkeypatch.setattr(
        users_router,
        "extract_media_metadata_from_storage",
        AsyncMock(return_value=(1024, 1024, 8)),
    )

    response = await users_router.get_favorite_apply_context(
        "task-1",
        current_user=type("User", (), {"id": 123})(),
        db=db,
    )

    assert response.task_id == "task-1"
    assert response.width == 1024
    assert response.height == 1024
    assert response.duration == 8
    assert history.width == 1024
    assert history.height == 1024
    assert history.duration == 8
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_favorite_apply_context_prefers_active_newer_gallery_post_metadata():
    now = datetime.now()
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="custom_video",
        prompt="prompt",
        output_file="bot-data/history/task-1/output.mp4",
    )
    inactive_newer = GalleryPost(
        id=3,
        task_id="task-1",
        is_active=False,
        created_at=now + timedelta(minutes=2),
        width=512,
        height=512,
        duration=5,
    )
    active_older = GalleryPost(
        id=1,
        task_id="task-1",
        is_active=True,
        created_at=now,
        width=720,
        height=720,
        duration=8,
    )
    active_newer = GalleryPost(
        id=2,
        task_id="task-1",
        is_active=True,
        created_at=now + timedelta(minutes=1),
        width=1024,
        height=1024,
        duration=10,
    )
    db = _FakeDB(
        [
            _FakeResult(single=history),
            _FakeResult(many=[inactive_newer, active_older, active_newer]),
        ]
    )

    response = await users_router.get_favorite_apply_context(
        "task-1",
        current_user=type("User", (), {"id": 123})(),
        db=db,
    )

    assert response.post_id == 2
    assert response.source_post_id == 2
    assert response.width == 1024
    assert response.height == 1024
    assert response.duration == 10
    db.commit.assert_not_awaited()
