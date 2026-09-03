import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
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
        if "count(history.id)" in str(stmt).lower():
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
    obj.__table__ = SimpleNamespace(
        columns=[SimpleNamespace(name=k) for k in base.keys()]
    )
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


def test_build_history_item_payload_includes_h3_audio_and_extension_video_inputs():
    storage_service = _FakeStorage()
    history = _build_history(
        type="minimax_h3_ref2v",
        input_file="task-inputs/task-2/reference-a.png|task-inputs/task-2/reference-b.png",
        extra_outputs={
            "_minimax_h3_context": {
                "version": 3,
                "mode": "ref2v",
                "main_model": "10eros_bf16",
                "requested_duration": 10,
                "resolution_preset": "preview",
                "aspect_ratio": "9:16",
                "lora_items": [],
                "reference_audio": "task-inputs/task-2/voice.m4a",
                "prev_task_id": "task-1",
                "chain_task_ids": ["task-1"],
            }
        },
    )

    result = history_presenter.build_history_item_payload(
        history=history,
        storage_service=storage_service,
    )

    assert result["input_media"] == [
        {
            "file": "task-inputs/task-2/reference-a.png",
            "url": "url://default/task-inputs/task-2/reference-a.png",
            "preview_url": (
                f"url://{MINIO_BUCKET}/task-inputs/task-2/reference-a_thumb.webp"
            ),
            "kind": "image",
            "label": "参考图 1",
        },
        {
            "file": "task-inputs/task-2/reference-b.png",
            "url": "url://default/task-inputs/task-2/reference-b.png",
            "preview_url": (
                f"url://{MINIO_BUCKET}/task-inputs/task-2/reference-b_thumb.webp"
            ),
            "kind": "image",
            "label": "参考图 2",
        },
        {
            "file": "task-1.mp4",
            "url": "",
            "preview_url": "",
            "resolve_url": "/api/history/media/task-1",
            "kind": "video",
            "label": "输入视频",
        },
        {
            "file": "task-inputs/task-2/voice.m4a",
            "url": "url://default/task-inputs/task-2/voice.m4a",
            "preview_url": "",
            "kind": "audio",
            "label": "参考音频",
        },
    ]


def test_build_history_item_payload_does_not_label_legacy_h3_audio_as_an_image():
    history = _build_history(
        type="minimax_h3_ref2v",
        input_file="reference.png|voice.mp4",
        extra_outputs={
            "_minimax_h3_context": {
                "version": 3,
                "mode": "ref2v",
                "main_model": "10eros_bf16",
                "requested_duration": 5,
                "resolution_preset": "preview",
                "aspect_ratio": "16:9",
                "lora_items": [],
                "reference_audio": "voice.mp4",
            }
        },
    )

    result = history_presenter.build_history_item_payload(
        history=history,
        storage_service=_FakeStorage(),
    )

    assert [(item["kind"], item["label"]) for item in result["input_media"]] == [
        ("image", "参考图 1"),
        ("audio", "参考音频"),
    ]


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
async def test_get_all_history_payload_caches_only_total_while_rows_stay_live():
    count_cache = history_service.HistoryCountCache(ttl_seconds=300)
    first_history = _build_history(task_id="task-first")
    second_history = _build_history(task_id="task-second")
    first_db = _FakeHistoryDb(
        total=10,
        rows=[(first_history, "tester", "Tester", "worker-1", None)],
    )
    second_db = _FakeHistoryDb(
        total=999,
        rows=[(second_history, "tester", "Tester", "worker-1", None)],
    )

    first_result = await history_service.get_all_history_payload(
        db=first_db,
        count_cache=count_cache,
        storage_service=_FakeStorage(),
        resolve_media_urls_func=lambda **_kwargs: _resolved_media(),
    )
    second_result = await history_service.get_all_history_payload(
        db=second_db,
        count_cache=count_cache,
        storage_service=_FakeStorage(),
        resolve_media_urls_func=lambda **_kwargs: _resolved_media(),
    )

    assert first_result["total"] == 10
    assert second_result["total"] == 10
    assert second_result["items"][0]["task_id"] == "task-second"
    assert (
        sum(
            "count(history.id)" in str(stmt).lower() for stmt in first_db.executed_stmts
        )
        == 1
    )
    assert all(
        "count(history.id)" not in str(stmt).lower()
        for stmt in second_db.executed_stmts
    )


@pytest.mark.asyncio
async def test_history_count_cache_keeps_filter_totals_separate():
    count_cache = history_service.HistoryCountCache(ttl_seconds=300)
    web_db = _FakeHistoryDb(total=3, rows=[])
    bot_db = _FakeHistoryDb(total=7, rows=[])

    web_result = await history_service.get_all_history_payload(
        db=web_db,
        source="web",
        count_cache=count_cache,
        storage_service=_FakeStorage(),
        resolve_media_urls_func=lambda **_kwargs: _resolved_media(),
    )
    bot_result = await history_service.get_all_history_payload(
        db=bot_db,
        source="bot",
        count_cache=count_cache,
        storage_service=_FakeStorage(),
        resolve_media_urls_func=lambda **_kwargs: _resolved_media(),
    )

    assert web_result["total"] == 3
    assert bot_result["total"] == 7
    assert web_db.execute_calls == 2
    assert bot_db.execute_calls == 2


@pytest.mark.asyncio
async def test_history_count_cache_keeps_username_totals_separate():
    count_cache = history_service.HistoryCountCache(ttl_seconds=300)
    gray_db = _FakeHistoryDb(total=3, rows=[])
    alice_db = _FakeHistoryDb(total=7, rows=[])

    gray_result = await history_service.get_all_history_payload(
        db=gray_db,
        username="Gray",
        count_cache=count_cache,
        storage_service=_FakeStorage(),
        resolve_media_urls_func=lambda **_kwargs: _resolved_media(),
    )
    alice_result = await history_service.get_all_history_payload(
        db=alice_db,
        username="alice",
        count_cache=count_cache,
        storage_service=_FakeStorage(),
        resolve_media_urls_func=lambda **_kwargs: _resolved_media(),
    )

    assert gray_result["total"] == 3
    assert alice_result["total"] == 7
    assert gray_db.execute_calls == 2
    assert alice_db.execute_calls == 2


@pytest.mark.asyncio
async def test_history_count_cache_single_flights_concurrent_loads():
    count_cache = history_service.HistoryCountCache(ttl_seconds=300)
    load_started = asyncio.Event()
    release_load = asyncio.Event()
    load_calls = 0

    async def load_total():
        nonlocal load_calls
        load_calls += 1
        load_started.set()
        await release_load.wait()
        return 42

    first = asyncio.create_task(count_cache.get_or_load(("all",), load_total))
    await load_started.wait()
    second = asyncio.create_task(count_cache.get_or_load(("all",), load_total))
    release_load.set()

    assert await asyncio.gather(first, second) == [42, 42]
    assert load_calls == 1


@pytest.mark.asyncio
async def test_refresh_default_history_count_cache_primes_unfiltered_total():
    count_cache = history_service.HistoryCountCache(ttl_seconds=300)
    warm_db = _FakeHistoryDb(total=23, rows=[])

    class _SessionContext:
        async def __aenter__(self):
            return warm_db

        async def __aexit__(self, *_args):
            return None

    total = await history_service.refresh_default_history_count_cache(
        count_cache=count_cache,
        session_factory=_SessionContext,
    )
    request_db = _FakeHistoryDb(total=999, rows=[])
    result = await history_service.get_all_history_payload(
        db=request_db,
        count_cache=count_cache,
        storage_service=_FakeStorage(),
        resolve_media_urls_func=lambda **_kwargs: _resolved_media(),
    )

    assert total == 23
    assert result["total"] == 23
    assert warm_db.execute_calls == 1
    assert warm_db.rollback_calls == 1
    assert request_db.execute_calls == 1


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
async def test_get_all_history_payload_filters_by_exact_username_case_insensitively():
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
        db.add_all(
            [
                User(id=123, username="GrayArtist", full_name="Gray"),
                User(id=456, username="someone_else", full_name="Someone"),
                User(id=789, username="GrayArtistExtra", full_name="Gray Extra"),
                History(
                    user_id=123,
                    task_id="task-gray",
                    type="img2img",
                    output_file="gray.png",
                    source="web",
                ),
                History(
                    user_id=456,
                    task_id="task-other",
                    type="img2img",
                    output_file="other.png",
                    source="web",
                ),
                History(
                    user_id=789,
                    task_id="task-gray-extra",
                    type="img2img",
                    output_file="gray-extra.png",
                    source="web",
                ),
            ]
        )
        await db.commit()

        result = await history_service.get_all_history_payload(
            db=db,
            username="grayartist",
            storage_service=_FakeStorage(),
            resolve_media_urls_func=lambda **_kwargs: _resolved_media(),
        )

    await engine.dispose()

    assert result["total"] == 1
    assert [item["username"] for item in result["items"]] == ["GrayArtist"]


@pytest.mark.asyncio
async def test_get_all_history_payload_accepts_qqcc_source_filter():
    storage_service = _FakeStorage()
    history = _build_history(
        extra_outputs={"_qqcc_regenerate": {"kind": "quick_image", "mode": "face_swap"}}
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

    assert result["items"][0]["output_file_url"] == ("url://default/folder/output.mp4")
    assert result["items"][0].get("output_file_preview_url") is None


@pytest.mark.asyncio
async def test_get_all_history_router_forwards_source_and_username_filters(monkeypatch):
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
        username="gray",
        db=object(),
    )

    assert result == {"items": [], "total": 0}
    assert captured["source"] == "bot:qqcc-private"
    assert captured["username"] == "gray"


@pytest.mark.asyncio
async def test_get_history_media_url_releases_db_before_resolving_media():
    history = _build_history(
        task_id="task-parent",
        type="minimax_h3_ref2v",
        output_file="task-results/backend-parent/primary.mp4",
    )

    class _ScalarRows:
        def scalars(self):
            return self

        def first(self):
            return history

    class _MediaDb:
        rollback_calls = 0

        async def execute(self, _stmt):
            return _ScalarRows()

        async def rollback(self):
            self.rollback_calls += 1

    db = _MediaDb()

    async def resolve_media_urls(**kwargs):
        assert db.rollback_calls == 1
        assert kwargs["task_id"] == "task-parent"
        assert kwargs["output_file"] == "task-results/backend-parent/primary.mp4"
        return "url://r2/parent.mp4", "url://r2/parent_thumb.webp"

    result = await history_service.get_history_media_url(
        task_id="task-parent",
        db=db,
        resolve_media_urls_func=resolve_media_urls,
        storage_service=_FakeStorage(),
    )

    assert result == "url://r2/parent.mp4"


@pytest.mark.asyncio
async def test_get_history_media_route_returns_a_signed_url_on_demand(monkeypatch):
    async def fake_get_history_media_url(**_kwargs):
        return "https://media.example/parent.mp4"

    monkeypatch.setattr(
        history_router,
        "get_history_media_url",
        fake_get_history_media_url,
    )

    response = await history_router.get_history_media("task-parent", db=object())

    assert response == {"url": "https://media.example/parent.mp4"}


@pytest.mark.asyncio
async def test_get_history_media_route_returns_404_for_missing_history(monkeypatch):
    async def fake_get_history_media_url(**_kwargs):
        return None

    monkeypatch.setattr(
        history_router,
        "get_history_media_url",
        fake_get_history_media_url,
    )

    with pytest.raises(HTTPException) as exc_info:
        await history_router.get_history_media("missing", db=object())

    assert exc_info.value.status_code == 404


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
