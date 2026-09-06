from datetime import datetime, timedelta

import pytest

from src.database.models import GalleryPost, History
from src.web_api.services import history_query_service


class _FakeResult:
    def __init__(self, many):
        self._many = list(many)

    def scalars(self):
        return self

    def all(self):
        return list(self._many)


class _FakeSession:
    def __init__(self, *results):
        self._results = iter(results)
        self.statements = []

    async def execute(self, _stmt):
        self.statements.append(_stmt)
        return next(self._results)


def test_pick_preferred_history_prefers_visible_row_with_output_file():
    now = datetime.now()
    invisible_newer = History(
        id=12,
        user_id=1,
        task_id="task-1",
        output_file=None,
        is_visible=False,
        created_at=now + timedelta(minutes=1),
    )
    visible_older = History(
        id=11,
        user_id=1,
        task_id="task-1",
        output_file="bot-data/history/task-1/output.png",
        is_visible=True,
        created_at=now,
    )

    preferred = history_query_service.pick_preferred_history(
        [invisible_newer, visible_older]
    )

    assert preferred is visible_older


@pytest.mark.asyncio
async def test_fetch_history_apply_context_entities_prefers_duplicate_history_row():
    older_history = History(
        id=11,
        user_id=1,
        task_id="task-1",
        output_file=None,
        is_visible=False,
    )
    newer_history = History(
        id=12,
        user_id=1,
        task_id="task-1",
        output_file="bot-data/history/task-1/output.png",
        is_visible=True,
    )
    gallery_post = GalleryPost(id=7, task_id="task-1", user_id=1, is_active=True)
    db = _FakeSession(
        _FakeResult([older_history, newer_history]),
        _FakeResult([gallery_post]),
    )

    history, post = await history_query_service.fetch_history_apply_context_entities(
        db=db,
        task_id="task-1",
        current_user_id=1,
    )

    assert history is newer_history
    assert post is gallery_post
    post_sql = str(db.statements[1].compile()).lower()
    assert "gallery_posts.user_id =" in post_sql


@pytest.mark.asyncio
async def test_active_public_gallery_lookup_is_scoped_to_history_owner():
    db = _FakeSession(_FakeResult(["task-1"]))

    result = await history_query_service.fetch_active_public_gallery_task_ids(
        db=db,
        task_ids=["task-1"],
        current_user_id=123,
    )

    assert result == {"task-1"}
    sql = str(db.statements[0].compile()).lower()
    assert "gallery_posts.user_id" in sql
