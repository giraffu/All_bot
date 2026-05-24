from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import BackgroundTasks, HTTPException

from src.database.models import History
from src.web_api.services import users_history_mutation_service as mutation_service


class _FakeResult:
    def __init__(self, *, single=None):
        self._single = single

    def scalar_one_or_none(self):
        return self._single


class _ExecuteResult:
    def __init__(self, rowcount: int = 1):
        self.rowcount = rowcount


class _FakeSession:
    def __init__(self, *results):
        self._results = iter(results)
        self.commit = AsyncMock()

    async def execute(self, _stmt):
        return next(self._results)


@pytest.mark.asyncio
async def test_favorite_user_history_is_idempotent_when_already_favorited():
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="image",
        output_file="123/output_images/task-1.png",
        is_favorited=True,
    )
    db = _FakeSession(_FakeResult(single=history))
    background_tasks = MagicMock(spec=BackgroundTasks)
    current_user = type("User", (), {"id": 123})()

    response = await mutation_service.favorite_user_history(
        task_id="task-1",
        current_user=current_user,
        db=db,
        schedule_background_task=background_tasks.add_task,
    )

    assert response == {"status": "success", "message": "收藏成功"}
    db.commit.assert_not_awaited()
    background_tasks.add_task.assert_not_called()


@pytest.mark.asyncio
async def test_unfavorite_user_history_updates_flag_and_commits():
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="image",
        is_favorited=True,
    )
    db = _FakeSession(_FakeResult(single=history))
    current_user = type("User", (), {"id": 123})()

    response = await mutation_service.unfavorite_user_history(
        task_id="task-1",
        current_user=current_user,
        db=db,
    )

    assert response == {"status": "success", "message": "已取消收藏"}
    assert history.is_favorited is False
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_soft_delete_user_history_hides_record_and_deactivates_gallery_post():
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        is_visible=True,
        is_public=True,
    )
    db = _FakeSession(
        _FakeResult(single=history),
        _ExecuteResult(rowcount=1),
    )
    current_user = type("User", (), {"id": 123, "total_contributions": 3})()

    response = await mutation_service.soft_delete_user_history(
        history_id=11,
        current_user=current_user,
        db=db,
    )

    assert response == {"status": "success", "message": "记录已删除"}
    assert history.is_visible is False
    assert current_user.total_contributions == 2
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_soft_delete_user_history_is_idempotent_when_already_hidden():
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        is_visible=False,
        is_public=False,
    )
    db = _FakeSession(_FakeResult(single=history))
    current_user = type("User", (), {"id": 123, "total_contributions": 3})()

    response = await mutation_service.soft_delete_user_history(
        history_id=11,
        current_user=current_user,
        db=db,
    )

    assert response == {"status": "success", "message": "记录已删除"}
    db.commit.assert_not_awaited()
    assert current_user.total_contributions == 3


@pytest.mark.asyncio
async def test_favorite_user_history_raises_when_task_not_found():
    db = _FakeSession(_FakeResult(single=None))
    background_tasks = MagicMock(spec=BackgroundTasks)
    current_user = type("User", (), {"id": 123})()

    with pytest.raises(HTTPException) as exc_info:
        await mutation_service.favorite_user_history(
            task_id="missing-task",
            current_user=current_user,
            db=db,
            schedule_background_task=background_tasks.add_task,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "未找到原任务详情"
    db.commit.assert_not_awaited()
    background_tasks.add_task.assert_not_called()
