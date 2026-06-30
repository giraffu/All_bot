import pytest
from httpx import ASGITransport, AsyncClient

from local_analytics_platform.app import main as analytics_main
from local_analytics_platform.app.prompt_graph import PROMPT_GRAPH_ALGORITHM_VERSION
from local_analytics_platform.app.prompt_mart import PROMPT_NORMALIZATION_VERSION
from local_analytics_platform.app.prompt_vectors import DEFAULT_VECTOR_MODEL_ID


@pytest.mark.asyncio
async def test_prompt_graph_returns_stable_empty_state_when_tables_missing(monkeypatch):
    async def fake_fetchrow(query, *args):
        if "analytics_prompt_graph_state" in query:
            return {"ready": False}
        raise AssertionError(f"unexpected query: {query}")

    async def fake_fetch(query, *args):
        raise AssertionError(f"unexpected query: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get("/api/prompt-graph")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is False
    assert payload["summary"]["node_count"] == 0
    assert payload["graph"]["nodes"] == []
    assert payload["model"]["algorithm_version"] == PROMPT_GRAPH_ALGORITHM_VERSION


@pytest.mark.asyncio
async def test_prompt_graph_returns_summary_distributions_and_graph(monkeypatch):
    calls = []

    async def fake_fetchrow(query, *args):
        calls.append(("fetchrow", query, args))
        lower = query.lower()
        if "analytics_prompt_graph_state" in lower and "to_regclass" in lower:
            return {"ready": True}
        if "node_count" in lower and "community_count" in lower:
            assert args == (DEFAULT_VECTOR_MODEL_ID, PROMPT_NORMALIZATION_VERSION, PROMPT_GRAPH_ALGORITHM_VERSION)
            return {
                "candidate_count": 100,
                "node_count": 100,
                "embedded_count": 98,
                "scene_count": 4,
                "micro_count": 3,
                "singleton_count": 20,
                "no_scene_count": 2,
                "community_count": 7,
                "edge_count": 5,
                "centroid_bridge_count": 0,
                "latest_refreshed_at": "2026-06-30T12:00:00",
            }
        if "source_task_type" in lower and "edge_count" in lower:
            assert args == (DEFAULT_VECTOR_MODEL_ID, PROMPT_NORMALIZATION_VERSION, PROMPT_GRAPH_ALGORITHM_VERSION, "edit")
            return {
                "candidate_count": 90,
                "node_count": 90,
                "scene_count": 4,
                "micro_count": 3,
                "singleton_count": 20,
                "no_scene_count": 2,
                "edge_count": 5,
            }
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def fake_fetch(query, *args):
        calls.append(("fetch", query, args))
        lower = query.lower()
        if "from analytics_prompt_graph_state" in lower:
            return [
                {
                    "key": f"{DEFAULT_VECTOR_MODEL_ID}:{PROMPT_NORMALIZATION_VERSION}:{PROMPT_GRAPH_ALGORITHM_VERSION}:layout_algorithm",
                    "value": "pca-v1",
                    "updated_at": "2026-06-30T12:00:00",
                }
            ]
        if "from analytics_prompt_graph_communities c" in lower and "join analytics_prompt_graph_layout" in lower:
            assert args == (
                DEFAULT_VECTOR_MODEL_ID,
                PROMPT_NORMALIZATION_VERSION,
                PROMPT_GRAPH_ALGORITHM_VERSION,
                "scene",
                "edit",
                10,
                "%portrait%",
                40,
            )
            return [
                {
                    "community_id": "scene1",
                    "community_type": "scene",
                    "task_type": "edit",
                    "label": "portrait",
                    "representative_prompt": "portrait soft light",
                    "member_count": 34,
                    "micro_count": 3,
                    "singleton_count": 4,
                    "quality_score": 55.0,
                    "total_uses": 200,
                    "total_users": 80,
                    "avg_similarity": 0.78,
                    "x": 0.1,
                    "y": -0.2,
                    "refreshed_at": "2026-06-30T12:00:00",
                }
            ]
        if "from analytics_prompt_graph_community_edges" in lower:
            assert args == (
                DEFAULT_VECTOR_MODEL_ID,
                PROMPT_NORMALIZATION_VERSION,
                PROMPT_GRAPH_ALGORITHM_VERSION,
                ["scene1"],
                "all",
                "edit",
            )
            return [
                {
                    "source_community_id": "scene1",
                    "target_community_id": "scene2",
                    "edge_type": "similarity",
                    "weight": 0.93,
                    "prompt_edge_count": 8,
                    "duplicate_edge_count": 0,
                    "avg_similarity": 0.93,
                    "max_similarity": 0.93,
                }
            ]
        if "from analytics_prompt_graph_nodes" in lower and "group by task_type" in lower:
            return [{"label": "edit", "count": 90}, {"label": "video", "count": 10}]
        if "from analytics_prompt_graph_communities" in lower and "group by task_type" in lower:
            return [{"label": "edit", "count": 4}, {"label": "video", "count": 2}]
        if "group by node_status" in lower:
            return [{"label": "clustered", "count": 80}, {"label": "singleton", "count": 20}]
        if "group by community_type" in lower:
            return [{"label": "scene", "count": 4}, {"label": "micro", "count": 3}]
        raise AssertionError(f"unexpected fetch query: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get("/api/prompt-graph?level=scene&task_type=edit&min_size=10&q=portrait")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["summary"]["node_count"] == 100
    assert payload["selected_task_type"] == "edit"
    assert payload["available_task_types"][0]["label"] == "edit"
    assert payload["task_summary"]["node_count"] == 90
    assert payload["model"]["layout_algorithm"] == "pca-v1"
    assert payload["graph"]["nodes"][0]["id"] == "scene1"
    assert payload["graph"]["edges"][0]["edge_type"] == "similarity"
    assert payload["distributions"]["node_status"][0]["label"] == "clustered"
    assert any(call[0] == "fetch" and call[2][-1] == 40 for call in calls)


@pytest.mark.asyncio
async def test_prompt_graph_defaults_to_largest_task_type(monkeypatch):
    async def fake_fetchrow(query, *args):
        lower = query.lower()
        if "analytics_prompt_graph_state" in lower and "to_regclass" in lower:
            return {"ready": True}
        if "node_count" in lower and "community_count" in lower:
            return {
                "candidate_count": 100,
                "node_count": 100,
                "embedded_count": 100,
                "scene_count": 6,
                "micro_count": 4,
                "singleton_count": 12,
                "no_scene_count": 5,
                "community_count": 10,
                "edge_count": 3,
                "centroid_bridge_count": 0,
                "latest_refreshed_at": None,
            }
        if "source_task_type" in lower and "edge_count" in lower:
            assert args[-1] == "edit"
            return {
                "candidate_count": 70,
                "node_count": 70,
                "scene_count": 4,
                "micro_count": 3,
                "singleton_count": 10,
                "no_scene_count": 2,
                "edge_count": 3,
            }
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def fake_fetch(query, *args):
        lower = query.lower()
        if "from analytics_prompt_graph_state" in lower:
            return []
        if "from analytics_prompt_graph_nodes" in lower and "group by task_type" in lower:
            return [{"label": "edit", "count": 70}, {"label": "video", "count": 30}]
        if "from analytics_prompt_graph_communities c" in lower and "join analytics_prompt_graph_layout" in lower:
            assert args[4] == "edit"
            return []
        if "from analytics_prompt_graph_communities" in lower and "group by task_type" in lower:
            return [{"label": "edit", "count": 4}, {"label": "video", "count": 2}]
        if "group by node_status" in lower or "group by community_type" in lower:
            return []
        raise AssertionError(f"unexpected fetch query: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get("/api/prompt-graph?level=scene")

    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_task_type"] == "edit"
    assert payload["graph"]["nodes"] == []


@pytest.mark.asyncio
async def test_prompt_graph_community_detail_returns_limited_members(monkeypatch):
    async def fake_fetchrow(query, *args):
        lower = query.lower()
        if "analytics_prompt_graph_state" in lower and "to_regclass" in lower:
            return {"ready": True}
        if "from analytics_prompt_graph_communities" in lower:
            assert args == ("scene1", DEFAULT_VECTOR_MODEL_ID, PROMPT_NORMALIZATION_VERSION, PROMPT_GRAPH_ALGORITHM_VERSION)
            return {
                "community_id": "scene1",
                "community_type": "scene",
                "task_type": "edit",
                "label": "portrait",
                "representative_hash": "a" * 32,
                "representative_prompt": "portrait soft light",
                "member_count": 34,
                "micro_count": 3,
                "singleton_count": 4,
                "quality_score": 55,
                "total_uses": 200,
                "total_users": 80,
                "avg_similarity": 0.78,
                "refreshed_at": "2026-06-30T12:00:00",
            }
        raise AssertionError(f"unexpected query: {query}")

    async def fake_fetch(query, *args):
        lower = query.lower()
        if "from analytics_prompt_graph_communities child" in lower:
            assert args == ("scene1", DEFAULT_VECTOR_MODEL_ID, PROMPT_NORMALIZATION_VERSION, PROMPT_GRAPH_ALGORITHM_VERSION, 20)
            return [{"community_id": "micro1", "label": "micro", "member_count": 2, "avg_similarity": 0.95}]
        if "from analytics_prompt_graph_memberships m" in lower:
            assert args == ("scene1", 30)
            return [
                {
                    "community_id": "scene1",
                    "prompt_hash": "a" * 32,
                    "membership_type": "scene",
                    "confidence": 0.98,
                    "confidence_band": "high",
                    "member_rank": 1,
                    "prompt": "portrait soft light",
                    "raw_prompt_representative": "Portrait soft light",
                    "uses": 5,
                    "users": 3,
                    "quality_score": 12,
                    "result_likes": 1,
                    "result_dislikes": 0,
                    "gallery_applies": 1,
                    "prompt_unlocks": 0,
                    "last_seen": "2026-06-25T00:00:00",
                }
            ]
        if "from analytics_prompt_graph_community_edges" in lower:
            assert args == ("scene1", DEFAULT_VECTOR_MODEL_ID, PROMPT_NORMALIZATION_VERSION, PROMPT_GRAPH_ALGORITHM_VERSION, 20)
            return [{"target_community_id": "scene2", "edge_type": "similarity", "weight": 0.93}]
        raise AssertionError(f"unexpected query: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get("/api/prompt-graph/communities/scene1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["community"]["community_id"] == "scene1"
    assert payload["children"][0]["community_id"] == "micro1"
    assert payload["members"][0]["prompt_preview"] == "portrait soft light"
    assert payload["bridge_edges"][0]["edge_type"] == "similarity"
