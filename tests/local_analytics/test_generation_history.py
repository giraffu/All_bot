import pytest
from httpx import ASGITransport, AsyncClient

from local_analytics_platform.app import main as analytics_main


@pytest.mark.asyncio
async def test_generation_history_returns_filtered_rows_and_type_counts(monkeypatch):
    async def fake_fetchrow(query, *args):
        assert "generation_history_total" in query
        assert args == ("edit",)
        return {"total": 21}

    async def fake_fetch(query, *args):
        if "generation_history_types" in query:
            assert args == ()
            return [
                {"task_type": "edit", "generation_count": 120},
                {"task_type": "video_lora", "generation_count": 30},
            ]
        if "generation_history_h3_main_models" in query:
            assert args == ()
            return [{"main_model": "10eros_int8", "generation_count": 7}]
        assert "generation_history_rows" in query
        assert args == ("edit", 10, 10)
        assert "left join users" in query.lower()
        assert "input_address" in query
        assert "output_address" in query
        assert "input_verified_count" in query
        assert "output_verified_count" in query
        return [
            {
                "id": 99,
                "user_id": 101,
                "nickname": "创作者",
                "task_type": "edit",
                "source": "web",
                "prompt": "保留人物，替换背景",
                "billing_resolution": "720p",
                "duration": None,
                "width": 768,
                "height": 1024,
                "favorite_count": 1,
                "rating": 1,
                "created_at": "2026-08-05T10:00:00",
                "input_address": "/api/generation-history/99/media?role_group=input",
                "output_address": "/api/generation-history/99/media?role_group=output",
                "input_asset_count": 2,
                "input_verified_count": 1,
                "output_asset_count": 3,
                "output_verified_count": 2,
            }
        ]

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/generation-history",
            params={"task_type": "edit", "sort": "type_count_desc", "page": 2},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["rows"][0]["nickname"] == "创作者"
    assert payload["rows"][0]["favorite_count"] == 1
    assert payload["rows"][0]["input_address"].endswith("role_group=input")
    assert payload["rows"][0]["output_address"].endswith("role_group=output")
    assert payload["rows"][0]["input_verified_count"] == 1
    assert payload["rows"][0]["output_verified_count"] == 2
    assert payload["task_types"][0] == {"task_type": "edit", "generation_count": 120}
    assert payload["h3_main_models"] == [
        {"main_model": "10eros_int8", "generation_count": 7}
    ]
    assert payload["pagination"] == {"page": 2, "limit": 10, "total": 21, "total_pages": 3}
    assert payload["filters"] == {
        "task_type": "edit",
        "h3_main_model": "",
        "sort": "type_count_desc",
    }


@pytest.mark.asyncio
async def test_generation_history_defaults_to_all_types_latest_first_and_ten_rows(monkeypatch):
    async def fake_fetchrow(query, *args):
        assert args == ("",)
        return {"total": 2}

    async def fake_fetch(query, *args):
        if "generation_history_types" in query:
            return []
        if "generation_history_h3_main_models" in query:
            return []
        assert args == ("", 10, 0)
        assert "h.created_at desc" in query.lower()
        assert "input_verified_count" in query
        assert "role_group=input" in query
        return []

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/generation-history")

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["page"] == 1
    assert payload["pagination"]["limit"] == 10
    assert payload["filters"] == {
        "task_type": "",
        "h3_main_model": "",
        "sort": "created_desc",
    }


@pytest.mark.asyncio
async def test_generation_history_rejects_unknown_sort():
    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/generation-history?sort=unknown")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_generation_history_filters_snapshot_backup_status(monkeypatch):
    async def fake_fetchrow(query, *args):
        assert "analytics_snapshot_backup_history_status" in query
        assert "snapshot_history.file_missing_count" in query
        assert "analytics_snapshot_backup_refs" not in query
        assert len(args) == 11
        return {"total": 4}

    async def fake_fetch(query, *args):
        if "generation_history_h3_main_models" in query or "group by 1" in query:
            return []
        assert "snapshot_history.backed_up_count" in query
        assert args[-2:] == (10, 0)
        return []

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/generation-history?snapshot_backup_status=file_missing"
        )

    assert response.status_code == 200
    assert response.json()["filters"]["snapshot_backup_status"] == "file_missing"


@pytest.mark.asyncio
async def test_generation_history_can_sort_all_rows_by_task_type_count(monkeypatch):
    async def fake_fetchrow(query, *args):
        return {"total": 20}

    async def fake_fetch(query, *args):
        if "generation_history_types" in query:
            return []
        if "generation_history_h3_main_models" in query:
            return []
        assert "with type_counts as" in query.lower()
        assert "type_counts.generation_count desc" in query.lower()
        assert args == (10, 0)
        return []

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/generation-history?sort=type_count_desc")

    assert response.status_code == 200
    assert response.json()["filters"]["sort"] == "type_count_desc"


@pytest.mark.asyncio
async def test_generation_history_filters_by_persisted_h3_main_model(monkeypatch):
    async def fake_fetchrow(query, *args):
        assert "_minimax_h3_context" in query
        assert "minimax_h3_i2v" in query
        assert args == (
            "", None, "", None, None, None, "", "", "", False,
            "10eros_int8",
        )
        return {"total": 1}

    async def fake_fetch(query, *args):
        if "generation_history_h3_main_models" in query:
            return [{"main_model": "10eros_bf16", "generation_count": 3}]
        if "group by 1" in query:
            return []
        assert "_minimax_h3_context" in query
        assert args == (
            "",
            None,
            "",
            None,
            None,
            None,
            "",
            "",
            "",
            False,
            "10eros_int8",
            10,
            0,
        )
        return [{"id": 7, "task_type": "minimax_h3_i2v", "h3_main_model": "10eros_int8"}]

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/generation-history?h3_main_model=10eros_int8")

    assert response.status_code == 200
    payload = response.json()
    assert payload["filters"]["h3_main_model"] == "10eros_int8"
    assert payload["rows"] == [
        {"id": 7, "task_type": "minimax_h3_i2v", "h3_main_model": "10eros_int8"}
    ]
