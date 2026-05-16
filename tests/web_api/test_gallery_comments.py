from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from src.database.models import GalleryComment, GalleryPost, History, User
from src.services import redis_client as redis_module
from src.web_api.routers import gallery as gallery_router
from src.web_api.schemas.gallery_schema import CommentCreate


class _FakeResult:
    def __init__(self, many=None):
        self._many = list(many or [])

    def scalars(self):
        return self

    def all(self):
        return list(self._many)


class _BuildPostResponseSession:
    def __init__(self, histories):
        self._histories = list(histories)

    async def execute(self, _stmt):
        return _FakeResult(many=self._histories)


class _ExecuteResult:
    def __init__(self, rowcount: int = 1):
        self.rowcount = rowcount


class _CreateCommentSession:
    def __init__(
        self,
        post,
        flush_error: Exception | None = None,
        execute_rowcount: int = 1,
    ):
        self.post = post
        self.flush_error = flush_error
        self.execute_rowcount = execute_rowcount
        self.added = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.execute = AsyncMock(return_value=_ExecuteResult(rowcount=execute_rowcount))

    async def get(self, model, ident):
        if model is GalleryPost and ident == self.post.id:
            return self.post
        return None

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        if self.flush_error is not None:
            raise self.flush_error
        if self.added:
            self.added[-1].id = 99
            self.added[-1].created_at = datetime(2026, 5, 16, 12, 0, 0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _ListCommentsSession:
    def __init__(self, post, comments, total):
        self.post = post
        self.comments = list(comments)
        self.total = total
        self.scalar_stmt = None
        self.execute_stmt = None

    async def get(self, model, ident):
        if model is GalleryPost and ident == self.post.id:
            return self.post
        return None

    async def scalar(self, stmt):
        self.scalar_stmt = str(stmt)
        return self.total

    async def execute(self, stmt):
        self.execute_stmt = str(stmt)
        return _FakeResult(many=self.comments)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_build_post_responses_defaults_missing_comments_count_to_zero(monkeypatch):
    history = History(
        id=1,
        user_id=123,
        task_id="task-1",
        type="image",
        prompt="prompt",
        output_file="bot-data/history/task-1/output.png",
    )
    post = GalleryPost(
        id=2,
        task_id="task-1",
        media_type="image",
        tags="[]",
        likes_count=0,
        dislikes_count=0,
        applied_count=0,
        comments_count=None,
        is_active=True,
        created_at=datetime.now(),
    )
    session = _BuildPostResponseSession([history])

    monkeypatch.setattr(
        gallery_router,
        "_pick_gallery_media_urls",
        AsyncMock(return_value=("media-url", "thumb-url")),
    )

    responses = await gallery_router._build_post_responses(session, [post], None)

    assert len(responses) == 1
    assert responses[0].comments_count == 0


@pytest.mark.asyncio
async def test_create_gallery_comment_trims_content_and_updates_count(monkeypatch):
    post = GalleryPost(id=1, task_id="task-1", media_type="image", is_active=True)
    session = _CreateCommentSession(post)
    current_user = User(id=123, username="tester")

    monkeypatch.setattr(gallery_router, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(
        redis_module.redis_client,
        "set_comment_lock",
        AsyncMock(return_value=True),
    )

    response = await gallery_router.create_gallery_comment(
        1,
        CommentCreate(content="  修仙成功  "),
        current_user=current_user,
    )

    assert session.added
    assert session.added[0].content == "修仙成功"
    assert session.execute.await_count == 1
    session.commit.assert_awaited_once()
    assert response.content == "修仙成功"
    assert response.user.author_name == "tester"


@pytest.mark.asyncio
async def test_create_gallery_comment_returns_429_when_rate_limited(monkeypatch):
    post = GalleryPost(id=1, task_id="task-1", media_type="image", is_active=True)
    session = _CreateCommentSession(post)

    monkeypatch.setattr(gallery_router, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(
        redis_module.redis_client,
        "set_comment_lock",
        AsyncMock(return_value=False),
    )

    with pytest.raises(HTTPException) as exc_info:
        await gallery_router.create_gallery_comment(
            1,
            CommentCreate(content="test"),
            current_user=User(id=123, username="tester"),
        )

    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_create_gallery_comment_does_not_consume_lock_for_missing_post(monkeypatch):
    session = _CreateCommentSession(post=GalleryPost(id=1, task_id="task-1", media_type="image", is_active=True))
    lock_mock = AsyncMock(return_value=True)

    async def fake_get(_model, _ident):
        return None

    session.get = fake_get
    monkeypatch.setattr(gallery_router, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(redis_module.redis_client, "set_comment_lock", lock_mock)

    with pytest.raises(HTTPException) as exc_info:
        await gallery_router.create_gallery_comment(
            999,
            CommentCreate(content="test"),
            current_user=User(id=123, username="tester"),
        )

    assert exc_info.value.status_code == 404
    lock_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_gallery_comment_releases_lock_when_db_write_fails(monkeypatch):
    post = GalleryPost(id=1, task_id="task-1", media_type="image", is_active=True)
    session = _CreateCommentSession(post, flush_error=RuntimeError("db down"))
    delete_lock_mock = AsyncMock()

    monkeypatch.setattr(gallery_router, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(
        redis_module.redis_client,
        "set_comment_lock",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        redis_module.redis_client,
        "delete_comment_lock",
        delete_lock_mock,
    )

    with pytest.raises(HTTPException) as exc_info:
        await gallery_router.create_gallery_comment(
            1,
            CommentCreate(content="test"),
            current_user=User(id=123, username="tester"),
        )

    assert exc_info.value.status_code == 500
    session.rollback.assert_awaited_once()
    delete_lock_mock.assert_awaited_once_with(123)


@pytest.mark.asyncio
async def test_create_gallery_comment_rolls_back_when_post_becomes_inactive(monkeypatch):
    post = GalleryPost(id=1, task_id="task-1", media_type="image", is_active=True)
    session = _CreateCommentSession(post, execute_rowcount=0)
    delete_lock_mock = AsyncMock()

    monkeypatch.setattr(gallery_router, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(
        redis_module.redis_client,
        "set_comment_lock",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        redis_module.redis_client,
        "delete_comment_lock",
        delete_lock_mock,
    )

    with pytest.raises(HTTPException) as exc_info:
        await gallery_router.create_gallery_comment(
            1,
            CommentCreate(content="test"),
            current_user=User(id=123, username="tester"),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "帖子已下架或已删除，无法发布评论"
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
    delete_lock_mock.assert_awaited_once_with(123)


@pytest.mark.asyncio
async def test_create_gallery_comment_maps_integrity_error_to_not_found(monkeypatch):
    post = GalleryPost(id=1, task_id="task-1", media_type="image", is_active=True)
    session = _CreateCommentSession(
        post,
        flush_error=IntegrityError("insert into gallery_comments", {}, Exception("fk")),
    )
    delete_lock_mock = AsyncMock()

    monkeypatch.setattr(gallery_router, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(
        redis_module.redis_client,
        "set_comment_lock",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        redis_module.redis_client,
        "delete_comment_lock",
        delete_lock_mock,
    )

    with pytest.raises(HTTPException) as exc_info:
        await gallery_router.create_gallery_comment(
            1,
            CommentCreate(content="test"),
            current_user=User(id=123, username="tester"),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "帖子已下架或已删除，无法发布评论"
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
    delete_lock_mock.assert_awaited_once_with(123)


@pytest.mark.asyncio
async def test_get_gallery_comments_filters_active_and_formats_author_name(monkeypatch):
    post = GalleryPost(id=1, task_id="task-1", media_type="image", is_active=True)
    comment = GalleryComment(
        id=10,
        post_id=1,
        user_id=123,
        content="hello",
        is_active=True,
        created_at=datetime(2026, 5, 16, 12, 0, 0),
    )
    comment.user = User(id=123, full_name="测试用户")
    session = _ListCommentsSession(post=post, comments=[comment], total=1)

    monkeypatch.setattr(gallery_router, "AsyncSessionLocal", lambda: session)

    response = await gallery_router.get_gallery_comments(1, page=1, size=20)

    assert response.total == 1
    assert response.items[0].user.author_name == "测试用户"
    assert "gallery_comments.is_active IS true" in session.scalar_stmt
    assert "gallery_comments.is_active IS true" in session.execute_stmt
    assert "gallery_comments.created_at DESC, gallery_comments.id DESC" in session.execute_stmt
