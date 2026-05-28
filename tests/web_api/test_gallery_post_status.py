from unittest.mock import AsyncMock

import pytest

from src.database.models import GalleryPost, History, User
from src.web_api.services.gallery_service_mutations import update_gallery_post_status


class _FakeScalarResult:
    def __init__(self, single=None):
        self._single = single

    def scalar_one_or_none(self):
        return self._single


class _StatusSession:
    def __init__(self, results):
        self._results = iter(results)
        self.commit = AsyncMock()

    async def execute(self, _stmt):
        return next(self._results)


@pytest.mark.asyncio
async def test_update_post_status_puts_submission_off_shelf_and_syncs_history():
    post = GalleryPost(
        id=7,
        task_id="task-1",
        user_id=123,
        media_type="image",
        is_active=True,
    )
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        is_public=True,
    )
    user = User(id=123, total_contributions=3)
    session = _StatusSession(
        [
            _FakeScalarResult(post),
            _FakeScalarResult(history),
            _FakeScalarResult(user),
        ]
    )

    response = await update_gallery_post_status(
        post_id=7,
        current_user=type("User", (), {"id": 123})(),
        db=session,
        is_active=False,
    )

    assert response == {"status": "success", "message": "已下架"}
    assert post.is_active is False
    assert history.is_public is False
    assert user.total_contributions == 2
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_post_status_puts_submission_back_on_shelf_and_increments_total():
    post = GalleryPost(
        id=8,
        task_id="task-2",
        user_id=123,
        media_type="image",
        is_active=False,
    )
    history = History(
        id=12,
        user_id=123,
        task_id="task-2",
        is_public=False,
    )
    user = User(id=123, total_contributions=2)
    session = _StatusSession(
        [
            _FakeScalarResult(post),
            _FakeScalarResult(history),
            _FakeScalarResult(user),
        ]
    )

    response = await update_gallery_post_status(
        post_id=8,
        current_user=type("User", (), {"id": 123})(),
        db=session,
        is_active=True,
    )

    assert response == {"status": "success", "message": "已上架"}
    assert post.is_active is True
    assert history.is_public is True
    assert user.total_contributions == 3
    session.commit.assert_awaited_once()
