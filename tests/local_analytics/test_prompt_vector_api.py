import pytest
from httpx import ASGITransport, AsyncClient

from local_analytics_platform.app import main as analytics_main
from local_analytics_platform.app.prompt_mart import PROMPT_NORMALIZATION_VERSION
from local_analytics_platform.app.prompt_vectors import DEFAULT_VECTOR_MODEL_ID


@pytest.mark.asyncio
async def test_prompt_vectors_returns_stable_empty_state_when_tables_missing(monkeypatch):
    async def fake_fetchrow(query, *args):
        if "analytics_prompt_vector_state" in query:
            return {"ready": False}
        raise AssertionError(f"unexpected query: {query}")

    async def fake_fetch(query, *args):
        raise AssertionError(f"unexpected query: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get("/api/prompt-vectors")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is False
    assert payload["summary"]["embedded_count"] == 0
    assert payload["clusters"] == []


@pytest.mark.asyncio
async def test_prompt_vectors_returns_summary_distributions_and_cluster_rows(monkeypatch):
    calls = []

    async def fake_fetchrow(query, *args):
        calls.append(("fetchrow", query, args))
        lower = query.lower()
        if "analytics_prompt_vector_state" in lower and "to_regclass" in lower:
            return {"ready": True}
        if "candidate_count" in lower and "embedded_count" in lower:
            assert args == (DEFAULT_VECTOR_MODEL_ID, PROMPT_NORMALIZATION_VERSION)
            return {
                "candidate_count": 100,
                "embedded_count": 80,
                "edge_count": 30,
                "duplicate_edge_count": 10,
                "similar_edge_count": 20,
                "cluster_count": 3,
                "clustered_prompts": 8,
                "latest_refreshed_at": "2026-06-26T12:00:00",
            }
        if "select count(*)" in lower and "from filtered" in lower:
            assert args == (
                DEFAULT_VECTOR_MODEL_ID,
                PROMPT_NORMALIZATION_VERSION,
                "edit",
                2,
                0.92,
                "%portrait%",
            )
            return {"total": 1}
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def fake_fetch(query, *args):
        calls.append(("fetch", query, args))
        lower = query.lower()
        if "from analytics_prompt_vector_state" in lower:
            return [
                {
                    "key": f"{DEFAULT_VECTOR_MODEL_ID}:{PROMPT_NORMALIZATION_VERSION}:embedding_dim",
                    "value": "3",
                    "updated_at": "2026-06-26T12:00:00",
                }
            ]
        if "from filtered" in lower and "cluster_id" in lower:
            assert args == (
                DEFAULT_VECTOR_MODEL_ID,
                PROMPT_NORMALIZATION_VERSION,
                "edit",
                2,
                0.92,
                "%portrait%",
                "member_count",
                40,
                0,
            )
            return [
                {
                    "cluster_id": "cluster1",
                    "model_id": DEFAULT_VECTOR_MODEL_ID,
                    "normalization_version": PROMPT_NORMALIZATION_VERSION,
                    "task_type": "edit",
                    "representative_hash": "a" * 32,
                    "representative_prompt": "portrait soft light",
                    "member_count": 3,
                    "duplicate_edge_count": 2,
                    "min_similarity": 0.93,
                    "avg_similarity": 0.95,
                    "max_similarity": 0.98,
                    "total_uses": 20,
                    "total_users": 7,
                    "quality_score": 33.0,
                    "representative_uses": 10,
                    "representative_users": 4,
                    "representative_result_likes": 2,
                    "representative_result_dislikes": 0,
                    "representative_gallery_applies": 3,
                    "representative_prompt_unlocks": 1,
                    "char_count": 19,
                    "last_seen": "2026-06-25T00:00:00",
                    "refreshed_at": "2026-06-26T12:00:00",
                }
            ]
        if "from analytics_prompt_similarity_clusters" in lower and "group by task_type" in lower:
            return [{"label": "edit", "count": 1}]
        if "cluster_size" not in lower and "cross join lateral" in lower:
            return [{"label": "3-5 条", "count": 1}]
        if "from analytics_prompt_similarity_edges" in lower and "group by band" in lower:
            return [{"label": "duplicate", "count": 10}, {"label": "similar", "count": 20}]
        raise AssertionError(f"unexpected fetch query: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get("/api/prompt-vectors?task_type=edit&q=portrait&min_similarity=0.92")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["summary"]["embedding_coverage"] == 80.0
    assert payload["model"]["embedding_dim"] == 3
    assert payload["clusters"][0]["cluster_id"] == "cluster1"
    assert payload["clusters"][0]["representative_preview"] == "portrait soft light"
    assert payload["distributions"]["task_type"] == [{"label": "edit", "count": 1}]
    assert payload["pagination"]["total"] == 1
    assert any(call[0] == "fetch" and call[2][-3:] == ("member_count", 40, 0) for call in calls)


@pytest.mark.asyncio
async def test_prompt_vector_cluster_detail_returns_members(monkeypatch):
    async def fake_fetchrow(query, *args):
        lower = query.lower()
        if "analytics_prompt_vector_state" in lower and "to_regclass" in lower:
            return {"ready": True}
        if "from analytics_prompt_similarity_clusters" in lower:
            assert args == ("cluster1", DEFAULT_VECTOR_MODEL_ID, PROMPT_NORMALIZATION_VERSION)
            return {
                "cluster_id": "cluster1",
                "model_id": DEFAULT_VECTOR_MODEL_ID,
                "normalization_version": PROMPT_NORMALIZATION_VERSION,
                "task_type": "edit",
                "representative_hash": "a" * 32,
                "representative_prompt": "portrait soft light",
                "member_count": 2,
                "duplicate_edge_count": 1,
                "min_similarity": 0.94,
                "avg_similarity": 0.95,
                "max_similarity": 0.96,
                "total_uses": 9,
                "total_users": 4,
                "quality_score": 12,
                "refreshed_at": "2026-06-26T12:00:00",
            }
        raise AssertionError(f"unexpected query: {query}")

    async def fake_fetch(query, *args):
        assert args == ("cluster1",)
        return [
            {
                "cluster_id": "cluster1",
                "prompt_hash": "a" * 32,
                "task_type": "edit",
                "similarity_to_representative": 1.0,
                "is_representative": True,
                "member_rank": 1,
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
        response = await client.get("/api/prompt-vectors/clusters/cluster1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["cluster"]["cluster_id"] == "cluster1"
    assert payload["members"][0]["is_representative"] is True
    assert payload["members"][0]["prompt_preview"] == "portrait soft light"


@pytest.mark.asyncio
async def test_prompt_vectors_rejects_bad_sort(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get("/api/prompt-vectors?sort=bad")

    assert response.status_code == 400
