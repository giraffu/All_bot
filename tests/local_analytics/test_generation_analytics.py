import pytest
from httpx import ASGITransport, AsyncClient

from local_analytics_platform.app import main as analytics_main


@pytest.mark.asyncio
async def test_generation_returns_comprehensive_analytics(monkeypatch):
    calls = []

    async def fake_fetchrow(query, *args):
        calls.append(("fetchrow", query, args))
        assert args == (30, analytics_main.GENERATION_OPERATION_TYPES)
        assert "generation_summary" in query
        return {
            "total_generations": 2000,
            "generations": 300,
            "creators": 40,
            "web_generations": 240,
            "bot_generations": 60,
            "result_records": 290,
            "result_rate": 96.67,
            "with_input_records": 120,
            "input_rate": 40,
            "favorited_records": 30,
            "favorite_rate": 10,
            "public_records": 20,
            "public_rate": 6.67,
            "gallery_posts": 15,
            "gallery_rate": 5,
            "likes": 100,
            "dislikes": 5,
            "comments": 12,
            "applies": 25,
            "prompt_unlocks": 8,
            "credits_spent": 900,
            "avg_credits_per_generation": 3,
            "worker_successes": 280,
            "worker_failures": 7,
            "worker_failure_rate": 2.44,
            "avg_worker_duration": 14.5,
            "p95_worker_duration": 33,
            "latest_generation_at": "2026-06-25T12:00:00",
            "avg_duration": 2.5,
            "avg_width": 768,
            "avg_height": 1024,
        }

    async def fake_fetch(query, *args):
        calls.append(("fetch", query, args))
        if "generation_daily" in query:
            assert args == (30, analytics_main.GENERATION_OPERATION_TYPES)
            return [
                {
                    "day": "2026-06-25",
                    "generations": 20,
                    "creators": 8,
                    "web_generations": 16,
                    "bot_generations": 4,
                    "result_records": 19,
                    "public_records": 2,
                    "favorited_records": 3,
                    "gallery_posts": 1,
                    "credits_spent": 60,
                    "worker_successes": 18,
                    "worker_failures": 1,
                }
            ]
        if "generation_by_type" in query:
            assert args == (30, analytics_main.GENERATION_OPERATION_TYPES)
            return [
                {
                    "task_type": "edit",
                    "generations": 100,
                    "creators": 12,
                    "result_records": 98,
                    "result_rate": 98,
                    "with_input": 100,
                    "input_rate": 100,
                    "favorited_records": 10,
                    "favorite_rate": 10,
                    "public_records": 8,
                    "public_rate": 8,
                    "gallery_posts": 5,
                    "gallery_rate": 5,
                    "likes": 20,
                    "dislikes": 1,
                    "comments": 2,
                    "applies": 4,
                    "credits_spent": 200,
                    "avg_credits_per_generation": 2,
                    "worker_failures": 1,
                    "worker_failure_rate": 1,
                    "avg_worker_duration": 10,
                    "avg_duration": 0,
                }
            ]
        if "generation_credits" in query:
            assert args == (30, analytics_main.GENERATION_OPERATION_TYPES)
            return [{"task_type": "edit", "debit_events": 100, "credits_spent": 200, "avg_credits_per_event": 2}]
        if "generation_hourly" in query:
            assert args == (30,)
            return [{"hour": 12, "generations": 10, "creators": 4}]
        if "generation_source_mix" in query:
            assert args == (30,)
            return [{"label": "Web", "source": "web", "count": 240, "creators": 35}]
        if "generation_quality_segments" in query:
            assert args == (30,)
            return [{"label": "有输出", "count": 290}, {"label": "Gallery 投稿", "count": 15}]
        if "generation_user_rank" in query:
            assert args == (30, 12)
            return [{"id": 101, "username": "maker", "full_name": "Maker", "generations": 50, "last_generation_at": "2026-06-25T12:00:00"}]
        if "generation_credit_user_rank" in query:
            assert args == (30, analytics_main.GENERATION_OPERATION_TYPES, 12)
            return [{"id": 102, "username": "spender", "full_name": "Spender", "credits_spent": 500, "debit_events": 100}]
        if "generation_gallery_user_rank" in query:
            assert args == (30, 12)
            return [{"id": 103, "username": "popular", "full_name": "Popular", "gallery_posts": 3, "likes": 30, "applies": 12}]
        if "generation_recent_high_signal" in query:
            assert args == (30, 12)
            return [
                {
                    "history_id": 201,
                    "task_id": "task_1",
                    "task_type": "edit",
                    "id": 101,
                    "username": "maker",
                    "full_name": "Maker",
                    "media_type": "image",
                    "likes": 20,
                    "dislikes": 1,
                    "comments": 2,
                    "applies": 5,
                    "is_favorited": True,
                    "is_public": True,
                    "created_at": "2026-06-25T12:00:00",
                    "signal_score": 57,
                }
            ]
        raise AssertionError(f"unexpected query: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/generation?days=30&limit=12")

    assert response.status_code == 200
    payload = response.json()
    assert payload["days"] == 30
    assert payload["limit"] == 12
    assert payload["summary"]["total_generations"] == 2000
    assert payload["summary"]["worker_failure_rate"] == 2.44
    assert payload["daily"][0]["credits_spent"] == 60
    assert payload["by_type"][0]["result_rate"] == 98
    assert payload["source_mix"][0]["label"] == "Web"
    assert payload["quality_segments"][1]["label"] == "Gallery 投稿"
    assert payload["leaderboards"]["generation"][0]["username"] == "maker"
    assert payload["leaderboards"]["credits"][0]["username"] == "spender"
    assert payload["leaderboards"]["gallery"][0]["username"] == "popular"
    assert payload["recent_high_signal"][0]["signal_score"] == 57
    assert any(call[0] == "fetch" and call[2] == (30, analytics_main.GENERATION_OPERATION_TYPES, 12) for call in calls)


@pytest.mark.asyncio
async def test_generation_hourly_comparison_returns_selected_dates(monkeypatch):
    async def fake_fetch(query, *args):
        assert "generation_hourly_comparison" in query
        assert args == (["2026-06-25", "2026-06-24"], analytics_main.GENERATION_OPERATION_TYPES)
        return [
            {
                "date": "2026-06-25",
                "hour": 12,
                "generations": 10,
                "creators": 4,
                "web_generations": 8,
                "bot_generations": 2,
                "credits_spent": 30,
                "worker_successes": 9,
                "worker_failures": 1,
            },
            {
                "date": "2026-06-24",
                "hour": 13,
                "generations": 6,
                "creators": 3,
                "web_generations": 5,
                "bot_generations": 1,
                "credits_spent": 18,
                "worker_successes": 6,
                "worker_failures": 0,
            },
        ]

    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/generation/hourly-comparison?dates=2026-06-25,2026-06-24")

    assert response.status_code == 200
    payload = response.json()
    assert payload["dates"] == ["2026-06-25", "2026-06-24"]
    assert payload["hourly"][0]["generations"] == 10
    assert payload["hourly"][0]["worker_failures"] == 1


@pytest.mark.asyncio
async def test_generation_hourly_cumulative_returns_period_totals(monkeypatch):
    async def fake_fetch(query, *args):
        assert "generation_hourly_cumulative" in query
        assert args == (30, analytics_main.GENERATION_OPERATION_TYPES)
        return [
            {
                "hour": 12,
                "generations": 30,
                "creators": 8,
                "web_generations": 24,
                "bot_generations": 6,
                "credits_spent": 90,
                "worker_successes": 28,
                "worker_failures": 2,
            }
        ]

    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/generation/hourly-cumulative?days=30")

    assert response.status_code == 200
    payload = response.json()
    assert payload["days"] == 30
    assert payload["hourly"][0]["hour"] == 12
    assert payload["hourly"][0]["credits_spent"] == 90


@pytest.mark.asyncio
async def test_generation_type_comparison_returns_selected_dates(monkeypatch):
    async def fake_fetch(query, *args):
        assert "generation_type_comparison" in query
        assert args == (["2026-06-25", "2026-06-24"],)
        return [
            {"date": "2026-06-25", "task_type": "edit", "generations": 12, "creators": 4},
            {"date": "2026-06-24", "task_type": "face_swap", "generations": 8, "creators": 3},
        ]

    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/generation/type-comparison?dates=2026-06-25,2026-06-24")

    assert response.status_code == 200
    payload = response.json()
    assert payload["dates"] == ["2026-06-25", "2026-06-24"]
    assert payload["types"][0]["task_type"] == "edit"
