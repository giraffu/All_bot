from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from local_analytics_platform.app import main as analytics_main
from local_analytics_platform.app.prompt_mart import PROMPT_NORMALIZATION_VERSION
from local_analytics_platform.app.prompt_near_graph import (
    CREATE_PROMPT_NEAR_GRAPH_SCHEMA_SQL,
    DEFAULT_NEAR_GRAPH_MAX_NEIGHBORS,
    PROMPT_NEAR_GRAPH_ALGORITHM_VERSION,
    NearGraphEdge,
    NearGraphPromptStats,
    build_near_graph,
    choose_family_center,
    search_result_may_be_truncated,
)
from local_analytics_platform.app.prompt_vectors import DEFAULT_VECTOR_MODEL_ID, normalize_embedding
from local_analytics_platform.app.prompt_vectors import EMBEDDING_DTYPE, embedding_to_bytes


def stats(prompt_hash: str, vector, *, quality_score: float = 10, uses: int = 1, users: int = 1) -> NearGraphPromptStats:
    return NearGraphPromptStats(
        prompt_hash=prompt_hash,
        task_type="edit",
        prompt=f"prompt {prompt_hash}",
        quality_score=quality_score,
        uses=uses,
        users=users,
        last_seen=datetime(2026, 7, 1, tzinfo=timezone.utc),
        embedding=normalize_embedding(vector),
    )


def test_prompt_near_graph_schema_contains_threshold_edge_tables():
    schema_sql = "\n".join(CREATE_PROMPT_NEAR_GRAPH_SCHEMA_SQL).lower()

    assert "create table if not exists analytics_prompt_near_graph_state" in schema_sql
    assert "create table if not exists analytics_prompt_near_graph_edges" in schema_sql
    assert "idx_prompt_near_graph_edges_task" in schema_sql
    assert PROMPT_NEAR_GRAPH_ALGORITHM_VERSION == "near-graph-v1"


def test_near_graph_keeps_chain_as_bridge_between_families():
    stats_by_hash = {
        "a": stats("a", [1.0, 0.0], quality_score=100),
        "b": stats("b", [0.98480775, 0.17364818], quality_score=90),
        "c": stats("c", [0.93969262, 0.34202014], quality_score=80),
    }
    edges = [
        NearGraphEdge("edit", "a", "b", 0.985),
        NearGraphEdge("edit", "b", "c", 0.985),
    ]

    result = build_near_graph(edges, stats_by_hash, threshold=0.95)

    assert sorted(len(family.member_hashes) for family in result.families) == [1, 2]
    assert len(result.bridges) == 1
    bridge = result.bridges[0]
    assert bridge.prompt_edge_count == 1
    assert bridge.examples == [{"source_hash": "b", "target_hash": "c", "similarity": 0.985}]
    assert any(set(family.member_hashes) == {"a", "b"} for family in result.families)
    assert any(family.member_hashes == ["c"] for family in result.families)


def test_near_graph_merges_complete_triangle_without_self_bridge():
    stats_by_hash = {
        "a": stats("a", [1.0, 0.0], quality_score=100),
        "b": stats("b", [0.98480775, 0.17364818], quality_score=90),
        "c": stats("c", [0.93969262, 0.34202014], quality_score=80),
    }
    edges = [
        NearGraphEdge("edit", "a", "b", 0.985),
        NearGraphEdge("edit", "a", "c", 0.96),
        NearGraphEdge("edit", "b", "c", 0.985),
    ]

    result = build_near_graph(edges, stats_by_hash, threshold=0.95)

    assert len(result.families) == 1
    assert set(result.families[0].member_hashes) == {"a", "b", "c"}
    assert result.bridges == []


def test_near_graph_threshold_changes_family_count():
    stats_by_hash = {
        "a": stats("a", [1.0, 0.0], quality_score=100),
        "b": stats("b", [0.98480775, 0.17364818], quality_score=90),
        "c": stats("c", [0.0, 1.0], quality_score=80),
        "d": stats("d", [0.17364818, 0.98480775], quality_score=70),
    }
    edges = [
        NearGraphEdge("edit", "a", "b", 0.96),
        NearGraphEdge("edit", "c", "d", 0.91),
    ]

    strict = build_near_graph(edges, stats_by_hash, threshold=0.95)
    loose = build_near_graph(edges, stats_by_hash, threshold=0.90)

    assert [len(family.member_hashes) for family in strict.families] == [2]
    assert sorted(len(family.member_hashes) for family in loose.families) == [2, 2]


def test_near_graph_center_uses_medoid_then_quality_tie_break():
    stats_by_hash = {
        "a": stats("a", [0.98480775, -0.17364818], quality_score=100),
        "b": stats("b", [1.0, 0.0], quality_score=10),
        "c": stats("c", [0.98480775, 0.17364818], quality_score=90),
    }

    center, _similarities = choose_family_center(["a", "b", "c"], stats_by_hash)

    assert center == "b"

    tied = {
        "x": stats("x", [1.0, 0.0], quality_score=1),
        "y": stats("y", [1.0, 0.0], quality_score=2),
    }
    center, _similarities = choose_family_center(["x", "y"], tied)

    assert center == "y"


def test_near_graph_truncation_diagnostic_marks_hit_at_neighbor_limit():
    assert search_result_may_be_truncated(
        returned_neighbor_count=DEFAULT_NEAR_GRAPH_MAX_NEIGHBORS,
        max_neighbors=DEFAULT_NEAR_GRAPH_MAX_NEIGHBORS,
        last_similarity=0.91,
        lower_bound=0.90,
    )
    assert not search_result_may_be_truncated(
        returned_neighbor_count=DEFAULT_NEAR_GRAPH_MAX_NEIGHBORS,
        max_neighbors=DEFAULT_NEAR_GRAPH_MAX_NEIGHBORS,
        last_similarity=0.89,
        lower_bound=0.90,
    )


@pytest.mark.asyncio
async def test_prompt_near_graph_returns_stable_empty_state_when_tables_missing(monkeypatch):
    async def fake_fetchrow(query, *args):
        if "analytics_prompt_near_graph_state" in query:
            return {"ready": False}
        raise AssertionError(f"unexpected query: {query}")

    async def fake_fetch(query, *args):
        raise AssertionError(f"unexpected query: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get("/api/prompt-near-graph")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is False
    assert payload["summary"]["family_count"] == 0
    assert payload["graph"]["nodes"] == []
    assert payload["model"]["normalization_version"] == PROMPT_NORMALIZATION_VERSION
    assert payload["model"]["model_id"] == DEFAULT_VECTOR_MODEL_ID


@pytest.mark.asyncio
async def test_prompt_near_graph_api_returns_bridge_graph_and_family_detail(monkeypatch):
    def stats_row(prompt_hash: str, vector, quality_score: float):
        embedding = normalize_embedding(vector)
        return {
            "prompt_hash": prompt_hash,
            "task_type": "edit",
            "prompt": f"prompt {prompt_hash}",
            "embedding_dim": int(embedding.size),
            "embedding_f16": embedding_to_bytes(embedding),
            "embedding_dtype": EMBEDDING_DTYPE,
            "quality_score": quality_score,
            "uses": int(quality_score),
            "users": 1,
            "last_seen": datetime(2026, 7, 1, tzinfo=timezone.utc),
            "result_likes": 0,
            "result_dislikes": 0,
            "gallery_applies": 0,
            "prompt_unlocks": 0,
            "char_count": 8,
        }

    async def fake_fetchrow(query, *args):
        lower = query.lower()
        if "analytics_prompt_near_graph_state" in lower and "to_regclass" in lower:
            return {"ready": True}
        if "threshold_edge_count" in lower:
            return {
                "candidate_count": 3,
                "embedded_count": 3,
                "threshold_edge_count": 2,
                "latest_refreshed_at": "2026-07-01T12:00:00",
            }
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def fake_fetch(query, *args):
        lower = query.lower()
        if "from analytics_prompt_near_graph_state" in lower:
            return [
                {
                    "key": f"{DEFAULT_VECTOR_MODEL_ID}:{PROMPT_NORMALIZATION_VERSION}:near-graph-v1:lower_bound",
                    "value": "0.9",
                    "updated_at": "2026-07-01T12:00:00",
                },
                {
                    "key": f"{DEFAULT_VECTOR_MODEL_ID}:{PROMPT_NORMALIZATION_VERSION}:near-graph-v1:max_neighbors",
                    "value": "512",
                    "updated_at": "2026-07-01T12:00:00",
                },
            ]
        if "select task_type as label" in lower:
            return [{"label": "edit", "count": 2}]
        if "select task_type, source_hash, target_hash" in lower:
            return [
                {"task_type": "edit", "source_hash": "a", "target_hash": "b", "similarity": 0.985},
                {"task_type": "edit", "source_hash": "b", "target_hash": "c", "similarity": 0.985},
            ]
        if "from analytics_prompt_embeddings e" in lower and "e.prompt_hash = any" in lower:
            return [
                stats_row("a", [1.0, 0.0], 100),
                stats_row("b", [0.98480775, 0.17364818], 90),
                stats_row("c", [0.93969262, 0.34202014], 80),
            ]
        raise AssertionError(f"unexpected fetch query: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get("/api/prompt-near-graph?threshold=0.95&task_type=edit&limit=10")
        payload = response.json()
        detail_response = await client.get(
            f"/api/prompt-near-graph/families/{payload['graph']['nodes'][0]['family_id']}?threshold=0.95&task_type=edit"
        )

    assert response.status_code == 200
    assert payload["ready"] is True
    assert payload["selected_task_type"] == "edit"
    assert len(payload["graph"]["nodes"]) == 2
    assert len(payload["graph"]["edges"]) == 1
    assert payload["graph"]["edges"][0]["prompt_edge_count"] == 1
    assert payload["isolated_families"] == []
    detail = detail_response.json()
    assert detail_response.status_code == 200
    assert detail["family"]["family_id"] == payload["graph"]["nodes"][0]["family_id"]
    assert detail["members"]
    assert detail["bridge_examples"][0]["source_hash"] == "b"
