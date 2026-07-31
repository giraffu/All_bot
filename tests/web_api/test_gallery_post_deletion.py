from unittest.mock import AsyncMock

import pytest

from src.database.models import GalleryPost, History, User
from src.web_api.services.gallery_service_mutations import delete_gallery_post


class _FakeScalarResult:
    def __init__(self, single=None, rowcount=0):
        self._single = single
        self.rowcount = rowcount

    def scalar_one_or_none(self):
        return self._single


class _FakeScalarsResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class _DeletePostSession:
    def __init__(self, results):
        self._results = iter(results)
        self.commit = AsyncMock()
        self.executed = []
        self.executed_statements = []

    async def execute(self, stmt):
        self.executed.append(stmt)
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
            _FakeScalarsResult([history]),
            _FakeScalarResult(user),
            _FakeScalarResult(),
            _FakeScalarResult(),
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
    assert any("DELETE FROM gallery_prompt_unlocks" in stmt for stmt in session.executed_statements)
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


@pytest.mark.asyncio
async def test_delete_post_handles_duplicate_histories_and_uses_primary_for_cache():
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
        type="image",
        output_file="123/output_images/task-dup.png",
        is_public=True,
        is_visible=True,
    )
    hidden_history = History(
        id=22,
        user_id=123,
        task_id="task-dup",
        type="image",
        output_file="123/output_images/task-dup-copy.png",
        is_public=False,
        is_visible=False,
    )
    user = User(id=123, total_contributions=3)
    session = _DeletePostSession(
        [
            _FakeScalarResult(post),
            _FakeScalarsResult([hidden_history, visible_history]),
            _FakeScalarResult(user),
            _FakeScalarResult(),
            _FakeScalarResult(),
            _FakeScalarResult(),
            _FakeScalarResult(),
            _FakeScalarResult(),
        ]
    )
    cleanup_mock = AsyncMock(return_value=4)

    response = await delete_gallery_post(
        post_id=9,
        current_user=type("User", (), {"id": 123})(),
        db=session,
        storage_service=type("Storage", (), {"async_delete_r2_objects": cleanup_mock})(),
    )

    assert response == {"status": "success", "message": "删除成功"}
    assert visible_history.is_public is False
    assert hidden_history.is_public is False
    assert user.total_contributions == 2
    session.commit.assert_awaited_once()
    assert any("DELETE FROM gallery_prompt_unlocks" in stmt for stmt in session.executed_statements)
    cleanup_mock.assert_awaited_once()
    assert set(cleanup_mock.await_args.args[0]) == {
        "history/task-dup/original.png",
        "history/task-dup/thumb.webp",
        "task-dup.png",
        "task-dup_thumb.webp",
    }


@pytest.mark.asyncio
async def test_delete_inactive_post_cleans_prompt_unlocks_before_post_delete():
    post = GalleryPost(
        id=10,
        task_id="task-unlocked",
        user_id=123,
        media_type="image",
        is_active=False,
    )
    history = History(
        id=31,
        user_id=123,
        task_id="task-unlocked",
        type="image",
        output_file="123/output_images/task-unlocked.png",
        is_public=False,
    )
    session = _DeletePostSession(
        [
            _FakeScalarResult(post),
            _FakeScalarsResult([history]),
            _FakeScalarResult(),
            _FakeScalarResult(),
            _FakeScalarResult(),
            _FakeScalarResult(),
            _FakeScalarResult(),
        ]
    )
    cleanup_mock = AsyncMock(return_value=4)

    response = await delete_gallery_post(
        post_id=10,
        current_user=type("User", (), {"id": 123})(),
        db=session,
        storage_service=type("Storage", (), {"async_delete_r2_objects": cleanup_mock})(),
    )

    assert response == {"status": "success", "message": "删除成功"}
    assert history.is_public is False
    assert any("DELETE FROM gallery_prompt_unlocks" in stmt for stmt in session.executed_statements)
    assert any("DELETE FROM gallery_posts" in stmt for stmt in session.executed_statements)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_user_delete_resolves_pending_reports_and_keeps_them_for_dashboard():
    post = GalleryPost(
        id=11,
        task_id="task-reported",
        user_id=123,
        media_type="image",
        is_active=True,
    )
    history = History(
        id=41,
        user_id=123,
        task_id="task-reported",
        type="image",
        output_file="123/output_images/task-reported.png",
        is_public=True,
    )
    user = User(id=123, total_contributions=1)
    session = _DeletePostSession(
        [
            _FakeScalarResult(post),
            _FakeScalarsResult([history]),
            _FakeScalarResult(user),
            _FakeScalarResult(rowcount=2),
            _FakeScalarResult(),
            _FakeScalarResult(),
            _FakeScalarResult(),
            _FakeScalarResult(),
        ]
    )

    response = await delete_gallery_post(
        post_id=11,
        current_user=type("User", (), {"id": 123})(),
        db=session,
        storage_service=type(
            "Storage",
            (),
            {"async_delete_r2_objects": AsyncMock(return_value=4)},
        )(),
    )

    assert response == {"status": "success", "message": "删除成功"}
    report_update = next(
        stmt for stmt in session.executed if "UPDATE gallery_reports" in str(stmt)
    )
    update_params = report_update.compile().params
    assert update_params["status"] == "resolved"
    assert update_params["resolution_action"] == "user_deleted"
    assert update_params["resolved_at"] is not None
    assert 11 in update_params.values()
    assert "pending" in update_params.values()
    report_update_index = session.executed.index(report_update)
    post_delete_index = next(
        index
        for index, stmt in enumerate(session.executed)
        if "DELETE FROM gallery_posts" in str(stmt)
    )
    assert report_update_index < post_delete_index
    assert not any(
        "DELETE FROM gallery_reports" in stmt for stmt in session.executed_statements
    )
    session.commit.assert_awaited_once()
