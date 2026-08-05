import asyncio
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
        self.rollback_count = 0
        self._in_transaction = True

    async def execute(self, _stmt):
        return next(self._results)

    def in_transaction(self):
        return self._in_transaction

    async def rollback(self):
        self.rollback_count += 1
        self._in_transaction = False


@pytest.mark.asyncio
async def test_web_result_r2_miss_requests_async_archive_restore(monkeypatch):
    monkeypatch.setattr(
        task_result_service, "_resolve_web_r2_url", AsyncMock(return_value="")
    )
    misses = []

    async def record_miss(history_id):
        misses.append(history_id)

    snapshot = task_result_service._HistorySnapshot(
        history_id=17,
        user_id=123,
        task_id="task-restore",
        type="custom_video",
        output_file="outputs/task-restore.mp4",
        source="web",
        extra_outputs=None,
    )
    assert (
        await task_result_service._resolve_task_result_url(
            snapshot, media_type="video", r2_miss_func=record_miss
        )
        == ""
    )
    assert misses == [17]

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
        "result_meta": {},
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
        "result_meta": {},
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
        "result_meta": {},
    }
    presign_mock.assert_not_called()
    r2_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_task_result_releases_read_transaction_before_r2_lookup(
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
    db = _FakeDB([_FakeResult(single=history)])

    async def r2_lookup(*_object_keys, **_kwargs):
        assert db.rollback_count == 1
        return "https://r2-test.aivison.it.com/history/task-1/original.png"

    monkeypatch.setattr(
        task_result_service,
        "get_first_r2_url_if_exists",
        r2_lookup,
    )

    response = await tasks_router.get_task_result(
        "task-1",
        current_user=type("User", (), {"id": 123})(),
        db=db,
    )

    assert response["status"] == "success"
    assert response["result_url"] == (
        "https://r2-test.aivison.it.com/history/task-1/original.png"
    )
    assert db.rollback_count == 1


@pytest.mark.asyncio
async def test_get_task_result_falls_back_to_storage_url_when_web_history_r2_not_ready(
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
        "status": "success",
        "task_id": "task-1",
        "task_type": "txt2img",
        "media_type": "image",
        "result_url": "http://192.168.1.115:9000/internal.png",
        "extra_outputs": {},
        "result_meta": {},
    }
    presign_mock.assert_called_once_with(
        "123/output_images/task-1.png",
        expires_hours=task_result_service.WEB_RESULT_STORAGE_FALLBACK_EXPIRES_HOURS,
        bucket=MINIO_BUCKET,
    )
    r2_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_task_result_uses_r2_s3_presign_for_image_after_public_miss(
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
    monkeypatch.setattr(
        task_result_service,
        "get_first_r2_url_if_exists",
        AsyncMock(return_value=""),
    )
    r2_exists_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(
        task_result_service.storage,
        "async_r2_object_exists",
        r2_exists_mock,
    )
    r2_presign = MagicMock(return_value="https://r2-s3.example/presigned.png")
    monkeypatch.setattr(task_result_service, "build_r2_presigned_url", r2_presign)
    storage_presign = MagicMock(
        side_effect=AssertionError("secondary storage path must not be used")
    )
    monkeypatch.setattr(media_presenter.storage, "get_presigned_url", storage_presign)

    response = await tasks_router.get_task_result(
        "task-1",
        current_user=type("User", (), {"id": 123})(),
        db=_FakeDB([_FakeResult(single=history)]),
    )

    assert response["status"] == "success"
    assert response["result_url"] == "https://r2-s3.example/presigned.png"
    r2_presign.assert_called_once_with(
        "history/task-1/original.png",
        expires_hours=task_result_service.WEB_RESULT_STORAGE_FALLBACK_EXPIRES_HOURS,
    )
    storage_presign.assert_not_called()


@pytest.mark.asyncio
async def test_get_task_result_keeps_web_video_pending_when_r2_not_ready(
    monkeypatch,
):
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="custom_video",
        output_file="123/output_images/task-1.mp4",
        source="web",
    )
    r2_mock = AsyncMock(return_value="")
    presign_mock = MagicMock(return_value="http://192.168.1.115:9000/internal.mp4")
    r2_exists_mock = AsyncMock(return_value=False)
    monkeypatch.setattr(task_result_service, "get_first_r2_url_if_exists", r2_mock)
    monkeypatch.setattr(media_presenter.storage, "get_presigned_url", presign_mock)
    monkeypatch.setattr(
        task_result_service.storage,
        "async_r2_object_exists",
        r2_exists_mock,
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
    presign_mock.assert_not_called()
    r2_mock.assert_awaited_once()
    r2_exists_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_task_result_keeps_video_pending_when_only_s3_fallback_exists(
    monkeypatch,
):
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="custom_video",
        output_file="123/output_images/task-1.mp4",
        source="web",
    )
    r2_mock = AsyncMock(return_value="")
    r2_exists_mock = AsyncMock(return_value=True)
    presigned_mock = MagicMock(return_value="https://r2-s3.example/presigned.mp4")
    presign_mock = MagicMock(return_value="http://192.168.1.115:9000/internal.mp4")
    monkeypatch.setattr(task_result_service, "get_first_r2_url_if_exists", r2_mock)
    monkeypatch.setattr(
        task_result_service.storage,
        "async_r2_object_exists",
        r2_exists_mock,
    )
    monkeypatch.setattr(
        task_result_service,
        "build_r2_presigned_url",
        presigned_mock,
    )
    monkeypatch.setattr(media_presenter.storage, "get_presigned_url", presign_mock)

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
    presign_mock.assert_not_called()
    r2_mock.assert_awaited_once_with(
        "history/task-1/original.mp4",
        "123/output_images/task-1.mp4",
        "task-1.mp4",
        timeout_seconds=task_result_service.WEB_RESULT_R2_LOOKUP_TIMEOUT_SECONDS,
        fallback_to_presigned=False,
    )
    r2_exists_mock.assert_not_awaited()
    presigned_mock.assert_not_called()


@pytest.mark.asyncio
async def test_get_task_result_keeps_web_video_pending_when_r2_lookup_times_out(
    monkeypatch,
):
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="custom_video",
        output_file="123/output_images/task-1.mp4",
        source="web",
    )

    async def slow_r2_lookup(*_object_keys, **_kwargs):
        await asyncio.sleep(1)
        return "https://r2-test.aivison.it.com/history/task-1/original.mp4"

    monkeypatch.setattr(
        task_result_service,
        "WEB_RESULT_R2_LOOKUP_TIMEOUT_SECONDS",
        0.01,
    )
    monkeypatch.setattr(
        task_result_service,
        "get_first_r2_url_if_exists",
        slow_r2_lookup,
    )
    presign_mock = MagicMock(return_value="http://192.168.1.115:9000/internal.mp4")
    monkeypatch.setattr(media_presenter.storage, "get_presigned_url", presign_mock)
    r2_exists_mock = AsyncMock(return_value=False)
    monkeypatch.setattr(
        task_result_service.storage,
        "async_r2_object_exists",
        r2_exists_mock,
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
    presign_mock.assert_not_called()
    r2_exists_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_task_result_keeps_video_pending_when_public_lookup_times_out(
    monkeypatch,
):
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="custom_video",
        output_file="123/output_images/task-1.mp4",
        source="web",
    )

    async def slow_r2_lookup(*_object_keys, **_kwargs):
        await asyncio.sleep(1)
        return ""

    monkeypatch.setattr(
        task_result_service,
        "WEB_RESULT_R2_LOOKUP_TIMEOUT_SECONDS",
        0.01,
    )
    monkeypatch.setattr(
        task_result_service,
        "get_first_r2_url_if_exists",
        slow_r2_lookup,
    )
    r2_exists_mock = AsyncMock(return_value=True)
    presigned_mock = MagicMock(return_value="https://r2-s3.example/presigned.mp4")
    minio_presign_mock = MagicMock(
        return_value="http://192.168.1.115:9000/internal.mp4"
    )
    monkeypatch.setattr(
        task_result_service.storage,
        "async_r2_object_exists",
        r2_exists_mock,
    )
    monkeypatch.setattr(
        task_result_service,
        "build_r2_presigned_url",
        presigned_mock,
    )
    monkeypatch.setattr(
        media_presenter.storage,
        "get_presigned_url",
        minio_presign_mock,
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
    r2_exists_mock.assert_not_awaited()
    presigned_mock.assert_not_called()
    minio_presign_mock.assert_not_called()


@pytest.mark.asyncio
async def test_get_task_result_keeps_polling_when_web_history_has_no_available_url(
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
    presign_mock = MagicMock(return_value="")
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
    presign_mock.assert_called_once_with(
        "123/output_images/task-1.png",
        expires_hours=task_result_service.WEB_RESULT_STORAGE_FALLBACK_EXPIRES_HOURS,
        bucket=MINIO_BUCKET,
    )
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
            "wan22_segment_index": 3,
        },
    }
