import pytest
from httpx import ASGITransport, AsyncClient

from local_analytics_platform.app import main as analytics_main
from local_analytics_platform.app.prompt_mart import PROMPT_NORMALIZATION_VERSION
from local_analytics_platform.app.prompt_scenes import PROMPT_SCENE_ALGORITHM_VERSION
from local_analytics_platform.app.prompt_vectors import DEFAULT_VECTOR_MODEL_ID


@pytest.mark.asyncio
async def test_prompt_scenes_returns_stable_empty_state_when_tables_missing(monkeypatch):
    async def fake_fetchrow(query, *args):
        if "analytics_prompt_semantic_scene_state" in query:
            return {"ready": False}
        raise AssertionError(f"unexpected query: {query}")

    async def fake_fetch(query, *args):
        raise AssertionError(f"unexpected query: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get("/api/prompt-scenes")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is False
    assert payload["summary"]["scene_count"] == 0
    assert payload["scenes"] == []
    assert payload["model"]["algorithm_version"] == PROMPT_SCENE_ALGORITHM_VERSION


@pytest.mark.asyncio
async def test_prompt_scenes_returns_summary_distributions_and_scene_rows(monkeypatch):
    calls = []

    async def fake_fetchrow(query, *args):
        calls.append(("fetchrow", query, args))
        lower = query.lower()
        if "analytics_prompt_semantic_scene_state" in lower and "to_regclass" in lower:
            return {"ready": True}
        if "candidate_count" in lower and "scene_count" in lower:
            assert args == (DEFAULT_VECTOR_MODEL_ID, PROMPT_NORMALIZATION_VERSION, PROMPT_SCENE_ALGORITHM_VERSION)
            return {
                "candidate_count": 100,
                "embedded_count": 100,
                "scene_count": 4,
                "scene_members": 100,
                "top_candidates": 40,
                "latest_refreshed_at": "2026-06-29T12:00:00",
            }
        if "select count(*)" in lower and "from filtered" in lower:
            assert args == (
                DEFAULT_VECTOR_MODEL_ID,
                PROMPT_NORMALIZATION_VERSION,
                PROMPT_SCENE_ALGORITHM_VERSION,
                "edit",
                10,
                "%portrait%",
                "high",
            )
            return {"total": 1}
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def fake_fetch(query, *args):
        calls.append(("fetch", query, args))
        lower = query.lower()
        if "from analytics_prompt_semantic_scene_state" in lower:
            return [
                {
                    "key": f"{DEFAULT_VECTOR_MODEL_ID}:{PROMPT_NORMALIZATION_VERSION}:{PROMPT_SCENE_ALGORITHM_VERSION}:target_scene_count",
                    "value": "1000",
                    "updated_at": "2026-06-29T12:00:00",
                }
            ]
        if "from filtered" in lower and "scene_id" in lower:
            assert args == (
                DEFAULT_VECTOR_MODEL_ID,
                PROMPT_NORMALIZATION_VERSION,
                PROMPT_SCENE_ALGORITHM_VERSION,
                "edit",
                10,
                "%portrait%",
                "high",
                "member_count",
                40,
                0,
            )
            return [
                {
                    "scene_id": "scene1",
                    "model_id": DEFAULT_VECTOR_MODEL_ID,
                    "normalization_version": PROMPT_NORMALIZATION_VERSION,
                    "algorithm_version": PROMPT_SCENE_ALGORITHM_VERSION,
                    "task_type": "edit",
                    "representative_hash": "a" * 32,
                    "representative_prompt": "portrait soft light",
                    "manual_label": None,
                    "member_count": 34,
                    "candidate_count": 30,
                    "high_confidence_count": 20,
                    "medium_confidence_count": 10,
                    "low_confidence_count": 4,
                    "min_similarity": 0.56,
                    "avg_similarity": 0.78,
                    "max_similarity": 0.99,
                    "total_uses": 200,
                    "total_users": 80,
                    "quality_score": 55.0,
                    "representative_uses": 20,
                    "representative_users": 10,
                    "representative_result_likes": 5,
                    "representative_result_dislikes": 0,
                    "representative_gallery_applies": 7,
                    "representative_prompt_unlocks": 2,
                    "char_count": 19,
                    "last_seen": "2026-06-28T00:00:00",
                    "refreshed_at": "2026-06-29T12:00:00",
                }
            ]
        if "from analytics_prompt_semantic_scenes" in lower and "group by task_type" in lower:
            return [{"label": "edit", "count": 1}]
        if "cross join lateral" in lower:
            return [{"label": "11-50 条", "count": 1}]
        if "from analytics_prompt_semantic_scene_members" in lower and "group by m.confidence_band" in lower:
            return [{"label": "high", "count": 20}, {"label": "medium", "count": 10}]
        raise AssertionError(f"unexpected fetch query: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get(
            "/api/prompt-scenes?task_type=edit&q=portrait&min_size=10&confidence_band=high"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["summary"]["embedding_coverage"] == 100.0
    assert payload["model"]["target_scene_count"] == 1000
    assert payload["scenes"][0]["scene_id"] == "scene1"
    assert payload["scenes"][0]["display_label"] == "portrait soft light"
    assert payload["distributions"]["confidence"][0] == {"label": "high", "count": 20}
    assert payload["pagination"]["total"] == 1
    assert any(call[0] == "fetch" and call[2][-3:] == ("member_count", 40, 0) for call in calls)


@pytest.mark.asyncio
async def test_prompt_scene_detail_returns_top_candidates_only(monkeypatch):
    async def fake_fetchrow(query, *args):
        lower = query.lower()
        if "analytics_prompt_semantic_scene_state" in lower and "to_regclass" in lower:
            return {"ready": True}
        if "from analytics_prompt_semantic_scenes" in lower:
            assert args == ("scene1", DEFAULT_VECTOR_MODEL_ID, PROMPT_NORMALIZATION_VERSION, PROMPT_SCENE_ALGORITHM_VERSION)
            return {
                "scene_id": "scene1",
                "model_id": DEFAULT_VECTOR_MODEL_ID,
                "normalization_version": PROMPT_NORMALIZATION_VERSION,
                "algorithm_version": PROMPT_SCENE_ALGORITHM_VERSION,
                "task_type": "edit",
                "representative_hash": "a" * 32,
                "representative_prompt": "portrait soft light",
                "manual_label": "柔光人像",
                "member_count": 34,
                "candidate_count": 30,
                "high_confidence_count": 20,
                "medium_confidence_count": 10,
                "low_confidence_count": 4,
                "min_similarity": 0.56,
                "avg_similarity": 0.78,
                "max_similarity": 0.99,
                "total_uses": 200,
                "total_users": 80,
                "quality_score": 55.0,
                "centroid_f16": b"\x8a\x00",
                "refreshed_at": "2026-06-29T12:00:00",
            }
        raise AssertionError(f"unexpected query: {query}")

    async def fake_fetch(query, *args):
        lower = query.lower()
        assert "m.candidate_rank is not null" in lower
        assert "limit $2::int" in lower
        assert args == ("scene1", 30)
        return [
            {
                "scene_id": "scene1",
                "prompt_hash": "a" * 32,
                "task_type": "edit",
                "similarity_to_scene": 0.98,
                "confidence_band": "high",
                "member_rank": 1,
                "candidate_rank": 1,
                "prompt": "portrait soft light",
                "raw_prompt_representative": "Portrait soft light",
                "variant_count": 1,
                "char_count": 19,
                "uses": 5,
                "users": 3,
                "result_likes": 1,
                "result_dislikes": 0,
                "gallery_likes": 2,
                "gallery_dislikes": 0,
                "gallery_applies": 1,
                "prompt_unlocks": 0,
                "quality_score": 12,
                "positive_signal_score": 12,
                "negative_signal_score": 0,
                "source_scopes": ["natural"],
                "first_seen": "2026-06-01T00:00:00",
                "last_seen": "2026-06-25T00:00:00",
            }
        ]

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get("/api/prompt-scenes/scene1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["scene"]["scene_id"] == "scene1"
    assert payload["scene"]["display_label"] == "柔光人像"
    assert "centroid_f16" not in payload["scene"]
    assert payload["candidates"][0]["candidate_rank"] == 1
    assert payload["candidates"][0]["prompt_preview"] == "portrait soft light"
