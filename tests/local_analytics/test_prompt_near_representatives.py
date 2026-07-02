from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from local_analytics_platform.app import main as analytics_main
from local_analytics_platform.app.prompt_mart import PROMPT_NORMALIZATION_VERSION
from local_analytics_platform.app.prompt_near_representatives import (
    NearPromptEdge,
    NearPromptStats,
    build_near_representative_groups,
)
from local_analytics_platform.app.prompt_vectors import DEFAULT_VECTOR_MODEL_ID


def near_stats(prompt_hash: str, *, quality_score: float = 10, uses: int = 1, users: int = 1) -> NearPromptStats:
    return NearPromptStats(
        prompt_hash=prompt_hash,
        task_type="edit",
        prompt=f"prompt {prompt_hash}",
        quality_score=quality_score,
        uses=uses,
        users=users,
        last_seen=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )


def test_near_representative_threshold_changes_group_count():
    stats = {
        "a": near_stats("a", quality_score=100),
        "b": near_stats("b", quality_score=90),
        "c": near_stats("c", quality_score=80),
        "d": near_stats("d", quality_score=70),
    }
    edges = [
        NearPromptEdge("edit", "a", "b", 0.95),
        NearPromptEdge("edit", "c", "d", 0.88),
    ]

    strict = build_near_representative_groups(edges, stats, threshold=0.92)
    loose = build_near_representative_groups(edges, stats, threshold=0.86)

    assert [(group.representative_hash, group.member_hashes) for group in strict] == [("a", ["a", "b"])]
    assert [(group.representative_hash, group.member_hashes) for group in loose] == [
        ("a", ["a", "b"]),
        ("c", ["c", "d"]),
    ]


def test_near_representative_groups_do_not_bridge_through_middle_member():
    stats = {
        "a": near_stats("a", quality_score=100),
        "b": near_stats("b", quality_score=90),
        "c": near_stats("c", quality_score=80),
    }
    edges = [
        NearPromptEdge("edit", "a", "b", 0.93),
        NearPromptEdge("edit", "b", "c", 0.93),
    ]

    groups = build_near_representative_groups(edges, stats, threshold=0.92)

    assert len(groups) == 1
    assert groups[0].representative_hash == "a"
    assert groups[0].member_hashes == ["a", "b"]


def test_near_representative_prefers_quality_usage_user_and_recency():
    old = datetime(2026, 6, 1, tzinfo=timezone.utc)
    new = datetime(2026, 7, 1, tzinfo=timezone.utc)
    stats = {
        "a": NearPromptStats("a", "edit", "prompt a", 10, 4, 2, old),
        "b": NearPromptStats("b", "edit", "prompt b", 10, 5, 2, old),
        "c": NearPromptStats("c", "edit", "prompt c", 10, 5, 3, old),
        "d": NearPromptStats("d", "edit", "prompt d", 10, 5, 3, new),
    }
    edges = [
        NearPromptEdge("edit", "a", "b", 0.95),
        NearPromptEdge("edit", "a", "c", 0.95),
        NearPromptEdge("edit", "a", "d", 0.95),
        NearPromptEdge("edit", "b", "c", 0.95),
        NearPromptEdge("edit", "b", "d", 0.95),
        NearPromptEdge("edit", "c", "d", 0.95),
    ]

    groups = build_near_representative_groups(edges, stats, threshold=0.92)

    assert groups[0].representative_hash == "d"


@pytest.mark.asyncio
async def test_prompt_near_representatives_returns_stable_empty_state_when_tables_missing(monkeypatch):
    async def fake_fetchrow(query, *args):
        if "analytics_prompt_vector_state" in query:
            return {"ready": False}
        raise AssertionError(f"unexpected query: {query}")

    async def fake_fetch(query, *args):
        raise AssertionError(f"unexpected query: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get("/api/prompt-near-representatives")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is False
    assert payload["summary"]["group_count"] == 0
    assert payload["groups"] == []


@pytest.mark.asyncio
async def test_prompt_near_representatives_recomputes_groups_for_threshold(monkeypatch):
    def stats_row(prompt_hash: str, quality_score: float):
        return {
            "prompt_hash": prompt_hash,
            "task_type": "edit",
            "prompt": f"prompt {prompt_hash}",
            "quality_score": quality_score,
            "uses": int(quality_score),
            "users": 1,
            "last_seen": "2026-07-01T00:00:00",
            "result_likes": 0,
            "result_dislikes": 0,
            "gallery_applies": 0,
            "prompt_unlocks": 0,
            "char_count": 8,
        }

    async def fake_fetchrow(query, *args):
        lower = query.lower()
        if "analytics_prompt_vector_state" in lower and "to_regclass" in lower:
            return {"ready": True}
        if "threshold_edge_count" in lower:
            threshold = float(args[2])
            return {
                "candidate_count": 5,
                "embedded_count": 5,
                "threshold_edge_count": 1 if threshold >= 0.92 else 2,
                "latest_refreshed_at": "2026-07-01T12:00:00",
            }
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def fake_fetch(query, *args):
        lower = query.lower()
        if "similarity::float8 as similarity" in lower:
            threshold = float(args[2])
            rows = [
                {"task_type": "edit", "source_hash": "a", "neighbor_hash": "b", "similarity": 0.95},
                {"task_type": "edit", "source_hash": "c", "neighbor_hash": "d", "similarity": 0.88},
            ]
            return [row for row in rows if row["similarity"] >= threshold]
        if "s.prompt_hash = any" in lower:
            return [
                stats_row("a", 100),
                stats_row("b", 90),
                stats_row("c", 80),
                stats_row("d", 70),
            ]
        raise AssertionError(f"unexpected fetch query: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        strict_response = await client.get("/api/prompt-near-representatives?threshold=0.92&task_type=edit")
        loose_response = await client.get("/api/prompt-near-representatives?threshold=0.86&task_type=edit")

    strict = strict_response.json()
    loose = loose_response.json()
    assert strict["model"]["threshold"] == 0.92
    assert strict["summary"]["group_count"] == 1
    assert loose["summary"]["group_count"] == 2
    assert loose["summary"]["merged_members"] == 2
    assert loose["groups"][0]["representative_hash"] == "a"
    assert loose["distributions"]["group_size"] == [{"label": "2 条", "count": 2}]
    assert loose["model"]["normalization_version"] == PROMPT_NORMALIZATION_VERSION
    assert loose["model"]["model_id"] == DEFAULT_VECTOR_MODEL_ID
