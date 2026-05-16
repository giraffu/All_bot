from unittest.mock import AsyncMock

import pytest

from dashboard.backend.routers import users as dashboard_users_router
from src.database.models import User


class _ScalarResult:
    def __init__(self, value=None, rows=None):
        self.value = value
        self.rows = list(rows or [])

    def scalar_one_or_none(self):
        return self.value

    def all(self):
        return list(self.rows)


class _FakeUsersDB:
    def __init__(self, user, comment_counts=None):
        self.user = user
        self.comment_counts = list(comment_counts or [])
        self.executed_stmts = []
        self.commit = AsyncMock()
        self.delete = AsyncMock()

    async def execute(self, stmt):
        sql = str(stmt)
        self.executed_stmts.append(sql)
        if "FROM users" in sql:
            return _ScalarResult(self.user)
        if "FROM gallery_comments" in sql and "GROUP BY gallery_comments.post_id" in sql:
            return _ScalarResult(rows=self.comment_counts)
        return _ScalarResult(None)


@pytest.mark.asyncio
async def test_delete_user_removes_gallery_comments_and_syncs_post_counts():
    user = User(id=123, username="tester")
    db = _FakeUsersDB(user, comment_counts=[(7, 2), (9, 1)])

    response = await dashboard_users_router.delete_user(123, db=db)

    assert "message" in response
    assert any("DELETE FROM gallery_comments" in stmt for stmt in db.executed_stmts)
    update_stmts = [stmt for stmt in db.executed_stmts if "UPDATE gallery_posts" in stmt]
    assert len(update_stmts) == 2
    assert all("greatest" in stmt.lower() for stmt in update_stmts)
    db.delete.assert_awaited_once_with(user)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_user_only_decrements_active_gallery_comments():
    user = User(id=123, username="tester")
    db = _FakeUsersDB(user, comment_counts=[(7, 1)])

    await dashboard_users_router.delete_user(123, db=db)

    gallery_count_stmt = next(
        stmt
        for stmt in db.executed_stmts
        if "FROM gallery_comments" in stmt and "GROUP BY gallery_comments.post_id" in stmt
    )
    assert "gallery_comments.is_active IS true" in gallery_count_stmt
    update_stmts = [stmt for stmt in db.executed_stmts if "UPDATE gallery_posts" in stmt]
    assert len(update_stmts) == 1
