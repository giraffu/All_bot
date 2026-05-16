from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from dashboard.backend.routers import gallery as dashboard_gallery_router
from src.database.models import GalleryComment, GalleryPost


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeDashboardDB:
    def __init__(self, comment, update_post_id=None):
        self.comment = comment
        self.update_post_id = update_post_id
        self.executed_stmts = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def get(self, model, ident):
        if model is GalleryComment and self.comment and ident == self.comment.id:
            return self.comment
        return None

    async def execute(self, stmt):
        self.executed_stmts.append(str(stmt))
        sql = str(stmt)
        if "UPDATE gallery_comments" in sql:
            return _ScalarResult(self.update_post_id)
        return _ScalarResult(None)


class _DashboardCommentsListDB:
    def __init__(self, post, comments, total=0, active_total=0):
        self.post = post
        self.comments = list(comments)
        self.total = total
        self.active_total = active_total
        self.scalar_calls = 0
        self.executed_stmts = []

    async def get(self, model, ident):
        if model is GalleryPost and self.post and ident == self.post.id:
            return self.post
        return None

    async def scalar(self, stmt):
        self.executed_stmts.append(str(stmt))
        self.scalar_calls += 1
        if self.scalar_calls == 1:
            return self.total
        return self.active_total

    async def execute(self, stmt):
        self.executed_stmts.append(str(stmt))
        return type(
            "_CommentResult",
            (),
            {
                "scalars": lambda _self: type(
                    "_Scalars",
                    (),
                    {"all": lambda __self: list(self.comments)},
                )()
            },
        )()


@pytest.mark.asyncio
async def test_update_gallery_comment_soft_delete_decrements_comments_count():
    comment = GalleryComment(id=10, post_id=7, user_id=123, content="hello", is_active=True)
    db = _FakeDashboardDB(comment, update_post_id=7)

    response = await dashboard_gallery_router.update_gallery_comment(
        10,
        dashboard_gallery_router.CommentUpdate(is_active=False),
        db=db,
    )

    assert response["success"] is True
    db.commit.assert_awaited_once()
    assert len(db.executed_stmts) == 2
    assert "UPDATE gallery_comments" in db.executed_stmts[0]
    assert "gallery_comments.is_active IS NOT false" in db.executed_stmts[0]
    assert "gallery_posts.comments_count - " in db.executed_stmts[1]
    assert "greatest" in db.executed_stmts[1].lower()


@pytest.mark.asyncio
async def test_update_gallery_comment_restore_increments_comments_count():
    comment = GalleryComment(id=11, post_id=8, user_id=123, content="hello", is_active=False)
    db = _FakeDashboardDB(comment, update_post_id=8)

    response = await dashboard_gallery_router.update_gallery_comment(
        11,
        dashboard_gallery_router.CommentUpdate(is_active=True),
        db=db,
    )

    assert response["success"] is True
    db.commit.assert_awaited_once()
    assert len(db.executed_stmts) == 2
    assert "UPDATE gallery_comments" in db.executed_stmts[0]
    assert "gallery_comments.is_active IS NOT true" in db.executed_stmts[0]
    assert "gallery_posts.comments_count + " in db.executed_stmts[1]


@pytest.mark.asyncio
async def test_update_gallery_comment_skips_count_update_when_status_unchanged():
    comment = GalleryComment(id=12, post_id=9, user_id=123, content="hello", is_active=True)
    db = _FakeDashboardDB(comment, update_post_id=None)

    response = await dashboard_gallery_router.update_gallery_comment(
        12,
        dashboard_gallery_router.CommentUpdate(is_active=True),
        db=db,
    )

    assert response["success"] is True
    assert response["message"] == "No change needed"
    assert len(db.executed_stmts) == 1
    assert "UPDATE gallery_comments" in db.executed_stmts[0]
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_gallery_comment_returns_404_when_comment_missing():
    db = _FakeDashboardDB(comment=None)

    with pytest.raises(HTTPException) as exc_info:
        await dashboard_gallery_router.update_gallery_comment(
            999,
            dashboard_gallery_router.CommentUpdate(is_active=False),
            db=db,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_gallery_comments_uses_stable_ordering():
    post = GalleryPost(id=7, task_id="task-7", media_type="image", is_active=True)
    db = _DashboardCommentsListDB(post=post, comments=[], total=0, active_total=0)

    await dashboard_gallery_router.get_gallery_comments(post_id=7, page=1, page_size=20, db=db)

    list_stmt = next(
        stmt for stmt in db.executed_stmts if "FROM gallery_comments" in stmt and "ORDER BY" in stmt
    )
    assert "gallery_comments.created_at DESC, gallery_comments.id DESC" in list_stmt
