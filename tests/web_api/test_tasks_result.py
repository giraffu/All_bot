from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from src.database.models import History
from src.web_api.routers import tasks as tasks_router


class _FakeResult:
    def __init__(self, *, single=None):
        self._single = single

    def scalars(self):
        return self

    def first(self):
        return self._single


class _FakeDB:
    def __init__(self, results):
        self._results = iter(results)

    async def execute(self, _stmt):
        return next(self._results)


@pytest.mark.asyncio
async def test_get_task_result_returns_pending_while_history_is_not_written():
    response = await tasks_router.get_task_result(
        "task-1",
        current_user=type("User", (), {"id": 123})(),
        db=_FakeDB([_FakeResult(single=None)]),
    )

    assert response == {
        "status": "pending_result",
        "task_id": "task-1",
        "task_type": None,
        "media_type": None,
    }


@pytest.mark.asyncio
async def test_get_task_result_returns_pending_when_output_file_is_not_ready():
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="custom_video",
        output_file=None,
    )

    response = await tasks_router.get_task_result(
        "task-1",
        current_user=type("User", (), {"id": 123})(),
        db=_FakeDB([_FakeResult(single=history)]),
    )

    assert response == {
        "status": "pending_result",
        "task_id": "task-1",
        "task_type": "custom_video",
        "media_type": "video",
    }


@pytest.mark.asyncio
async def test_get_task_result_uses_resolved_storage_object_for_bucket_prefixed_keys(
    monkeypatch,
):
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="image",
        output_file="bot-data/history/task-1/output.png",
    )
    presign_mock = MagicMock(return_value="https://cdn.example/task-1.png")
    monkeypatch.setattr(tasks_router.storage, "get_presigned_url", presign_mock)

    response = await tasks_router.get_task_result(
        "task-1",
        current_user=type("User", (), {"id": 123})(),
        db=_FakeDB([_FakeResult(single=history)]),
    )

    assert response == {
        "status": "success",
        "task_id": "task-1",
        "task_type": "image",
        "media_type": "image",
        "result_url": "https://cdn.example/task-1.png",
    }
    presign_mock.assert_called_once_with(
        "history/task-1/output.png",
        expires_hours=24,
        bucket="bot-data",
    )


@pytest.mark.asyncio
async def test_get_task_result_rejects_history_owned_by_another_user():
    history = History(
        id=11,
        user_id=999,
        task_id="task-1",
        type="image",
        output_file="999/output_images/task-1.png",
    )

    with pytest.raises(HTTPException) as exc_info:
        await tasks_router.get_task_result(
            "task-1",
            current_user=type("User", (), {"id": 123})(),
            db=_FakeDB([_FakeResult(single=history)]),
        )

    assert exc_info.value.status_code == 403
