from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.database.models import History
from src.core.media_paths import MINIO_BUCKET
from src.web_api.presenters import media_presenter
from src.web_api.routers import tasks as tasks_router
from src.web_api.services import task_result_service


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
        "extra_outputs": {},
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
        "extra_outputs": {},
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
    monkeypatch.setattr(media_presenter.storage, "get_presigned_url", presign_mock)

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
        "extra_outputs": {},
    }
    presign_mock.assert_called_once_with(
        "history/task-1/output.png",
        expires_hours=24,
        bucket=MINIO_BUCKET,
    )


@pytest.mark.asyncio
async def test_get_task_result_uses_primary_bucket_for_unprefixed_history_video_path(
    monkeypatch,
):
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="custom_video",
        output_file="123/output_images/task-1.mp4",
    )
    presign_mock = MagicMock(return_value="https://cdn.example/task-1.mp4")
    monkeypatch.setattr(media_presenter.storage, "get_presigned_url", presign_mock)

    response = await tasks_router.get_task_result(
        "task-1",
        current_user=type("User", (), {"id": 123})(),
        db=_FakeDB([_FakeResult(single=history)]),
    )

    assert response == {
        "status": "success",
        "task_id": "task-1",
        "task_type": "custom_video",
        "media_type": "video",
        "result_url": "https://cdn.example/task-1.mp4",
        "extra_outputs": {},
    }
    presign_mock.assert_called_once_with(
        "123/output_images/task-1.mp4",
        expires_hours=24,
        bucket=MINIO_BUCKET,
    )


@pytest.mark.asyncio
async def test_get_task_result_prefers_public_r2_url_for_web_history(
    monkeypatch,
):
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="txt2img",
        output_file="123/output_images/task-1.png",
        source="web",
    )
    r2_mock = AsyncMock(return_value="https://r2-test.aivison.it.com/history/task-1/original.png")
    presign_mock = MagicMock(return_value="http://192.168.1.115:9000/internal.png")
    monkeypatch.setattr(task_result_service, "get_first_r2_url_if_exists", r2_mock)
    monkeypatch.setattr(media_presenter.storage, "get_presigned_url", presign_mock)

    response = await tasks_router.get_task_result(
        "task-1",
        current_user=type("User", (), {"id": 123})(),
        db=_FakeDB([_FakeResult(single=history)]),
    )

    assert response == {
        "status": "success",
        "task_id": "task-1",
        "task_type": "txt2img",
        "media_type": "image",
        "result_url": "https://r2-test.aivison.it.com/history/task-1/original.png",
        "extra_outputs": {},
    }
    presign_mock.assert_not_called()
    r2_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_task_result_keeps_polling_when_web_history_public_url_not_ready(
    monkeypatch,
):
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="txt2img",
        output_file="123/output_images/task-1.png",
        source="web",
    )
    r2_mock = AsyncMock(return_value="")
    presign_mock = MagicMock(return_value="http://192.168.1.115:9000/internal.png")
    monkeypatch.setattr(task_result_service, "get_first_r2_url_if_exists", r2_mock)
    monkeypatch.setattr(media_presenter.storage, "get_presigned_url", presign_mock)

    response = await tasks_router.get_task_result(
        "task-1",
        current_user=type("User", (), {"id": 123})(),
        db=_FakeDB([_FakeResult(single=history)]),
    )

    assert response == {
        "status": "pending_result",
        "task_id": "task-1",
        "task_type": "txt2img",
        "media_type": "image",
        "extra_outputs": {},
    }
    presign_mock.assert_not_called()
    r2_mock.assert_awaited_once()


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


@pytest.mark.asyncio
async def test_get_task_result_resolves_history_extra_outputs(monkeypatch):
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="wan22_video_v2",
        output_file="123/output_images/task-1.mp4",
        extra_outputs={
            "last_frame": {
                "path": "123/output_images/task-1_last_frame.png",
                "media_type": "image",
            },
            "_wan22_context": {
                "wan22_resolution_preset": "hd",
                "wan22_negative_prompt": "blur",
                "wan22_use_end_frame": True,
                "wan22_prev_task_id": "task-0",
                "wan22_chain_task_ids": ["task-root", "task-0"],
            },
        },
    )
    presign_mock = MagicMock(side_effect=[
        "https://cdn.example/task-1.mp4",
        "https://cdn.example/task-1-last-frame.png",
    ])
    monkeypatch.setattr(media_presenter.storage, "get_presigned_url", presign_mock)

    response = await tasks_router.get_task_result(
        "task-1",
        current_user=type("User", (), {"id": 123})(),
        db=_FakeDB([_FakeResult(single=history)]),
    )

    assert response == {
        "status": "success",
        "task_id": "task-1",
        "task_type": "wan22_video_v2",
        "media_type": "video",
        "result_url": "https://cdn.example/task-1.mp4",
        "extra_outputs": {
            "last_frame": {
                "path": "123/output_images/task-1_last_frame.png",
                "media_type": "image",
                "url": "https://cdn.example/task-1-last-frame.png",
            }
        },
        "result_meta": {
            "wan22_resolution_preset": "hd",
            "wan22_negative_prompt": "blur",
            "wan22_use_end_frame": True,
            "wan22_prev_task_id": "task-0",
            "wan22_chain_task_ids": ["task-root", "task-0"],
        },
    }
