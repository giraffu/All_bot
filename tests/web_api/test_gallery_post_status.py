from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.database.models import GalleryPost, History, User
from src.web_api.services.gallery_service_mutations import update_gallery_post_status


class _FakeScalarResult:
    def __init__(self, single=None):
        self._single = single

    def scalar_one_or_none(self):
        return self._single


class _FakeScalarsResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


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
            _FakeScalarsResult([history]),
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
            _FakeScalarsResult([history]),
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


@pytest.mark.asyncio
async def test_update_post_status_rejects_reactivation_for_submission_banned_user():
    post = GalleryPost(
        id=8,
        task_id="task-2",
        user_id=123,
        media_type="image",
        is_active=False,
    )
    session = _StatusSession([_FakeScalarResult(post)])

    with pytest.raises(HTTPException) as exc_info:
        await update_gallery_post_status(
            post_id=8,
            current_user=type(
                "User",
                (),
                {
                    "id": 123,
                    "is_submission_banned": True,
                    "submission_ban_reason": None,
                },
            )(),
            db=session,
            is_active=True,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "违禁被封，请联系管理员解封"
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_post_status_handles_duplicate_histories_when_off_shelf():
    post = GalleryPost(
        id=9,
        task_id="task-dup",
        user_id=123,
        media_type="image",
        is_active=True,
    )
    visible_history = History(
        id=21,
        user_id=123,
        task_id="task-dup",
        is_public=True,
        is_visible=True,
    )
    hidden_history = History(
        id=22,
        user_id=123,
        task_id="task-dup",
        is_public=False,
        is_visible=False,
    )
    user = User(id=123, total_contributions=3)
    session = _StatusSession(
        [
            _FakeScalarResult(post),
            _FakeScalarsResult([hidden_history, visible_history]),
            _FakeScalarResult(user),
        ]
    )

    response = await update_gallery_post_status(
        post_id=9,
        current_user=type("User", (), {"id": 123})(),
        db=session,
        is_active=False,
    )

    assert response == {"status": "success", "message": "已下架"}
    assert visible_history.is_public is False
    assert hidden_history.is_public is False
    assert user.total_contributions == 2
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_post_status_reactivates_only_primary_duplicate_history():
    post = GalleryPost(
        id=10,
        task_id="task-dup",
        user_id=123,
        media_type="image",
        is_active=False,
    )
    visible_history = History(
        id=21,
        user_id=123,
        task_id="task-dup",
        is_public=False,
        is_visible=True,
    )
    hidden_history = History(
        id=22,
        user_id=123,
        task_id="task-dup",
        is_public=False,
        is_visible=False,
    )
    user = User(id=123, total_contributions=2)
    session = _StatusSession(
        [
            _FakeScalarResult(post),
            _FakeScalarsResult([hidden_history, visible_history]),
            _FakeScalarResult(user),
        ]
    )

    response = await update_gallery_post_status(
        post_id=10,
        current_user=type("User", (), {"id": 123})(),
        db=session,
        is_active=True,
    )

    assert response == {"status": "success", "message": "已上架"}
    assert visible_history.is_public is True
    assert hidden_history.is_public is False
    assert user.total_contributions == 3
    session.commit.assert_awaited_once()
