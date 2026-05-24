from unittest.mock import AsyncMock

import pytest

from src.database.models import GalleryPost, History, User
from src.web_api.services.gallery_service_mutations import delete_gallery_post


class _FakeScalarResult:
    def __init__(self, single=None):
        self._single = single

    def scalar_one_or_none(self):
        return self._single


class _DeletePostSession:
    def __init__(self, results):
        self._results = iter(results)
        self.commit = AsyncMock()
        self.executed_statements = []

    async def execute(self, stmt):
        self.executed_statements.append(str(stmt))
        return next(self._results)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_delete_post_hard_deletes_record_and_cleans_r2_cache():
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
        type="image",
        output_file="123/output_images/task-1.png",
        is_public=True,
    )
    user = User(id=123, total_contributions=3)
    session = _DeletePostSession(
        [
            _FakeScalarResult(post),
            _FakeScalarResult(history),
            _FakeScalarResult(user),
            _FakeScalarResult(),
            _FakeScalarResult(),
            _FakeScalarResult(),
        ]
    )
    cleanup_mock = AsyncMock(return_value=4)

    response = await delete_gallery_post(
        post_id=7,
        current_user=type("User", (), {"id": 123})(),
        db=session,
        storage_service=type("Storage", (), {"async_delete_r2_objects": cleanup_mock})(),
    )

    assert response == {"status": "success", "message": "删除成功"}
    assert history.is_public is False
    assert user.total_contributions == 2
    session.commit.assert_awaited_once()
    assert any("DELETE FROM user_interactions" in stmt for stmt in session.executed_statements)
    assert any("DELETE FROM gallery_comments" in stmt for stmt in session.executed_statements)
    assert any("DELETE FROM gallery_posts" in stmt for stmt in session.executed_statements)
    cleanup_mock.assert_awaited_once()
    assert set(cleanup_mock.await_args.args[0]) == {
        "history/task-1/original.png",
        "history/task-1/thumb.webp",
        "task-1.png",
        "task-1_thumb.webp",
    }


@pytest.mark.asyncio
async def test_delete_post_without_history_cache_still_returns_success():
    post = GalleryPost(
        id=8,
        task_id=None,
        user_id=123,
        media_type="image",
        is_active=False,
    )
    session = _DeletePostSession(
        [
            _FakeScalarResult(post),
            _FakeScalarResult(),
            _FakeScalarResult(),
            _FakeScalarResult(),
        ]
    )
    cleanup_mock = AsyncMock()

    response = await delete_gallery_post(
        post_id=8,
        current_user=type("User", (), {"id": 123})(),
        db=session,
        storage_service=type("Storage", (), {"async_delete_r2_objects": cleanup_mock})(),
    )

    assert response == {"status": "success", "message": "删除成功"}
    session.commit.assert_awaited_once()
    cleanup_mock.assert_not_awaited()
