from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config import MINIO_BUCKET, MINIO_TEMPLATE_BUCKET
from dashboard.backend.presenters import history_presenter
from dashboard.backend.routers import history as history_router
from dashboard.backend.services import history_service
from src.database.models import History, User, WorkerLog


class _FakeStorage:
    def __init__(self):
        self.calls = []

    def get_presigned_url(self, object_name, bucket=None):
        self.calls.append((object_name, bucket))
        suffix = bucket or "default"
        return f"url://{suffix}/{object_name}"


class _FakeScalarResult:
    def __init__(self, scalar_value=0):
        self._scalar_value = scalar_value

    def scalar(self):
        return self._scalar_value


class _FakeRowsResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def __iter__(self):
        return iter(self._rows)


class _FakeHistoryDb:
    def __init__(self, total, rows):
        self.total = total
        self.rows = list(rows)
        self.executed_stmts = []
        self.execute_calls = 0
        self.rollback_calls = 0
        self.expunge_all_calls = 0

    async def execute(self, stmt):
        self.executed_stmts.append(stmt)
        self.execute_calls += 1
        if self.execute_calls == 1:
            return _FakeScalarResult(self.total)
        return _FakeRowsResult(self.rows)

    async def rollback(self):
        self.rollback_calls += 1

    def expunge_all(self):
        self.expunge_all_calls += 1


def _build_history(**overrides):
    base = {
        "id": 1,
        "user_id": 123,
        "task_id": "task-1",
        "type": "img2img",
        "input_file": "template:tpl/a.png|user/input.png",
        "output_file": "result.png",
        "prompt": "hello",
        "created_at": datetime(2026, 1, 1, 12, 0, 0),
        "rating": 1,
        "is_public": True,
        "source": "bot",
    }
    base.update(overrides)
    obj = SimpleNamespace(**base)
    obj.__table__ = SimpleNamespace(columns=[SimpleNamespace(name=k) for k in base.keys()])
    return obj


def test_build_history_item_payload_generates_storage_urls():
    storage_service = _FakeStorage()
    history = _build_history()

    result = history_presenter.build_history_item_payload(
        history=history,
        username="tester",
        full_name="Tester",
        worker_id="worker-1",
        storage_service=storage_service,
    )

    assert result["username"] == "tester"
    assert result["full_name"] == "Tester"
    assert result["worker_id"] == "worker-1"
    assert result["input_file_url"] == (
        f"url://{MINIO_TEMPLATE_BUCKET}/tpl/a.png|url://default/user/input.png"
    )
    assert result["input_file_preview_url"] == (
        f"url://{MINIO_TEMPLATE_BUCKET}/tpl/a_thumb.webp|"
        f"url://{MINIO_BUCKET}/user/input_thumb.webp"
    )
    assert result["output_file_url"] == "url://comfyui-temp/result.png"


@pytest.mark.parametrize(
    ("history_source", "extra_outputs", "private_client_type", "expected"),
    [
        ("web", None, None, "web"),
        ("bot", None, None, "bot"),
        (
            "bot",
            {"_qqcc_regenerate": {"kind": "quick_image", "mode": "face_swap"}},
            None,
            "bot:qqcc",
        ),
        (
            "bot",
            {"_qqcc_regenerate": {"kind": "quick_image", "mode": "face_swap"}},
            "bot:qqcc-private:17",
            "bot:qqcc-private:17",
        ),
    ],
)
def test_build_history_item_payload_resolves_bot_source_without_history_schema_change(
    history_source,
    extra_outputs,
    private_client_type,
    expected,
):
    history = _build_history(
        source=history_source,
        extra_outputs=extra_outputs,
    )

    result = history_presenter.build_history_item_payload(
        history=history,
        private_client_type=private_client_type,
        storage_service=_FakeStorage(),
    )

    assert result["source"] == expected


@pytest.mark.asyncio
async def test_get_all_history_payload_uses_presenter_for_items():
    storage_service = _FakeStorage()
    history = _build_history()
    db = _FakeHistoryDb(
        total=1,
        rows=[(history, "tester", "Tester", "worker-1", None)],
    )

    media_calls = []

    async def resolve_media_urls(**kwargs):
        media_calls.append((kwargs, db.rollback_calls))
        assert db.expunge_all_calls == 1
        return "url://r2/original.png", "url://r2/thumb.webp"

    result = await history_service.get_all_history_payload(
        db=db,
        page=1,
        page_size=20,
        storage_service=storage_service,
        resolve_media_urls_func=resolve_media_urls,
    )

    assert result["total"] == 1
    assert len(result["items"]) == 1
    assert result["items"][0]["username"] == "tester"
    assert result["items"][0]["worker_id"] == "worker-1"
    assert result["items"][0]["input_file_url"].startswith("url://")
    assert result["items"][0]["output_file_url"] == "url://r2/original.png"
    assert result["items"][0]["output_file_preview_url"] == "url://r2/thumb.webp"
    assert db.rollback_calls == 1
    assert db.expunge_all_calls == 1
    assert media_calls[0][1] == 1
    assert media_calls[0][0]["r2_lookup_strategy"] == "s3_cached"


@pytest.mark.asyncio
async def test_get_all_history_payload_releases_real_session_before_media_resolution():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        for model in (User, History, WorkerLog):
            await connection.run_sync(model.__table__.create)
        await connection.exec_driver_sql(
            "CREATE TABLE private_bot_task_submissions "
            "(registry_task_id VARCHAR(64), client_type VARCHAR(128))"
        )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        db.add(User(id=123, username="tester", full_name="Tester"))
        db.add(
            History(
                user_id=123,
                task_id="task-real-session",
                type="img2img",
                input_file="user/input.png",
                output_file="result.png",
                prompt="hello",
                source="web",
            )
        )
        await db.commit()

        async def resolve_media_urls(**kwargs):
            assert not db.in_transaction()
            assert kwargs["task_id"] == "task-real-session"
            return "url://r2/original.png", "url://r2/thumb.webp"

        result = await history_service.get_all_history_payload(
            db=db,
            page=1,
            page_size=1,
            storage_service=_FakeStorage(),
            resolve_media_urls_func=resolve_media_urls,
        )

    await engine.dispose()

    assert result["total"] == 1
    assert result["items"][0]["task_id"] == "task-real-session"
    assert result["items"][0]["output_file_preview_url"] == "url://r2/thumb.webp"


@pytest.mark.asyncio
async def test_get_all_history_payload_counts_each_task_once_with_repeated_worker_logs():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        for model in (User, History, WorkerLog):
            await connection.run_sync(model.__table__.create)
        await connection.exec_driver_sql(
            "CREATE TABLE private_bot_task_submissions "
            "(registry_task_id VARCHAR(64), client_type VARCHAR(128))"
        )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        db.add(User(id=123, username="tester", full_name="Tester"))
        db.add(
            History(
                user_id=123,
                task_id="task-with-retries",
                type="img2img",
                output_file="result.png",
                source="web",
            )
        )
        db.add_all(
            [
                WorkerLog(
                    id=1,
                    worker_id="worker-old",
                    task_id="task-with-retries",
                    status="failed",
                    start_time=datetime(2026, 1, 1, 12, 0, 0),
                    end_time=datetime(2026, 1, 1, 12, 0, 1),
                    duration=1,
                ),
                WorkerLog(
                    id=2,
                    worker_id="worker-latest",
                    task_id="task-with-retries",
                    status="success",
                    start_time=datetime(2026, 1, 1, 12, 0, 2),
                    end_time=datetime(2026, 1, 1, 12, 0, 3),
                    duration=1,
                ),
            ]
        )
        await db.commit()

        result = await history_service.get_all_history_payload(
            db=db,
            page=1,
            page_size=20,
            storage_service=_FakeStorage(),
            resolve_media_urls_func=lambda **_kwargs: _resolved_media(),
        )

    await engine.dispose()

    assert result["total"] == 1
    assert len(result["items"]) == 1
    assert result["items"][0]["worker_id"] == "worker-latest"


@pytest.mark.asyncio
async def test_get_all_history_payload_count_avoids_unfiltered_diagnostic_joins():
    db = _FakeHistoryDb(total=0, rows=[])

    await history_service.get_all_history_payload(
        db=db,
        storage_service=_FakeStorage(),
        resolve_media_urls_func=lambda **_kwargs: _resolved_media(),
    )

    count_sql = str(db.executed_stmts[0]).lower()
    assert "count(history.id)" in count_sql
    assert "worker_logs" not in count_sql
    assert "private_bot_task_submissions" not in count_sql
    assert "order by" not in count_sql


@pytest.mark.asyncio
async def test_get_all_history_payload_worker_filter_uses_exists_without_duplicate_join():
    db = _FakeHistoryDb(total=0, rows=[])

    await history_service.get_all_history_payload(
        db=db,
        worker_id="worker-1",
        storage_service=_FakeStorage(),
        resolve_media_urls_func=lambda **_kwargs: _resolved_media(),
    )

    count_sql = str(db.executed_stmts[0]).lower()
    assert "exists" in count_sql
    assert "worker_logs" in count_sql
    assert "join worker_logs" not in count_sql
    assert "order by" not in count_sql


@pytest.mark.asyncio
async def test_get_all_history_payload_accepts_qqcc_source_filter():
    storage_service = _FakeStorage()
    history = _build_history(
        extra_outputs={
            "_qqcc_regenerate": {"kind": "quick_image", "mode": "face_swap"}
        }
    )
    db = _FakeHistoryDb(
        total=1,
        rows=[(history, "tester", "Tester", "worker-1", None)],
    )

    result = await history_service.get_all_history_payload(
        db=db,
        source="bot:qqcc",
        storage_service=storage_service,
        resolve_media_urls_func=lambda **_kwargs: _resolved_media(),
    )

    assert result["total"] == 1
    assert result["items"][0]["source"] == "bot:qqcc"


@pytest.mark.asyncio
async def test_get_all_history_payload_degrades_when_thumbnail_lookup_fails():
    storage_service = _FakeStorage()
    history = _build_history(output_file="folder/output.mp4", type="custom_video")
    db = _FakeHistoryDb(
        total=1,
        rows=[(history, "tester", "Tester", "worker-1", None)],
    )

    async def failing_media_resolver(**_kwargs):
        raise TimeoutError("R2 thumbnail lookup timed out")

    result = await history_service.get_all_history_payload(
        db=db,
        storage_service=storage_service,
        resolve_media_urls_func=failing_media_resolver,
    )

    assert result["items"][0]["output_file_url"] == (
        "url://default/folder/output.mp4"
    )
    assert result["items"][0].get("output_file_preview_url") is None


@pytest.mark.asyncio
async def test_get_all_history_router_forwards_source_filter(monkeypatch):
    captured = {}

    async def fake_get_all_history_payload(**kwargs):
        captured.update(kwargs)
        return {"items": [], "total": 0}

    monkeypatch.setattr(
        history_router,
        "get_all_history_payload",
        fake_get_all_history_payload,
    )

    result = await history_router.get_all_history(
        source="bot:qqcc-private",
        db=object(),
    )

    assert result == {"items": [], "total": 0}
    assert captured["source"] == "bot:qqcc-private"


@pytest.mark.asyncio
async def test_get_user_history_payload_uses_presenter_for_items():
    storage_service = _FakeStorage()
    history = _build_history(output_file="folder/output.png")
    db = _FakeRowsResult([(history, "worker-2", None)])

    class _CountResult:
        def scalar(self):
            return 125

    class _FakeUserHistoryDb:
        rollback_calls = 0
        expunge_all_calls = 0
        execute_calls = 0

        async def execute(self, _stmt):
            self.execute_calls += 1
            if self.execute_calls == 1:
                return _CountResult()
            return db

        async def rollback(self):
            self.rollback_calls += 1

        def expunge_all(self):
            self.expunge_all_calls += 1

    user_db = _FakeUserHistoryDb()

    async def resolve_media_urls(**_kwargs):
        assert user_db.expunge_all_calls == 1
        assert user_db.rollback_calls == 1
        return "url://r2/output.png", "url://r2/output_thumb.webp"

    result = await history_service.get_user_history_payload(
        user_id=123,
        page=2,
        page_size=25,
        db=user_db,
        storage_service=storage_service,
        resolve_media_urls_func=resolve_media_urls,
    )

    assert result["total"] == 125
    assert result["page"] == 2
    assert result["page_size"] == 25
    assert len(result["items"]) == 1
    assert result["items"][0]["worker_id"] == "worker-2"
    assert result["items"][0]["output_file_url"] == "url://r2/output.png"
    assert result["items"][0]["output_file_preview_url"] == "url://r2/output_thumb.webp"
    assert user_db.expunge_all_calls == 1


async def _resolved_media():
    return "url://r2/original.png", "url://r2/thumb.webp"
