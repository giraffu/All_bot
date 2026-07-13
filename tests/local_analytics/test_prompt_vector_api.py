import pytest
from httpx import ASGITransport, AsyncClient

from local_analytics_platform.app import main as analytics_main
from local_analytics_platform.app import routes_prompts
from local_analytics_platform.app.prompt_mart import PROMPT_NORMALIZATION_VERSION
from local_analytics_platform.app.prompt_vectors import DEFAULT_VECTOR_MODEL_ID, PROMPT_TOKEN_VERSION


@pytest.fixture(autouse=True)
def clear_prompt_vector_resume_state():
    state = analytics_main.app.state._state
    for key in (
        "prompt_vector_resume_process",
        "prompt_vector_resume_started_at",
        "prompt_vector_resume_last_exit",
    ):
        state.pop(key, None)
    yield
    for key in (
        "prompt_vector_resume_process",
        "prompt_vector_resume_started_at",
        "prompt_vector_resume_last_exit",
    ):
        state.pop(key, None)


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
    assert payload["summary"]["candidate_count"] == 0
    assert payload["summary"]["embedded_count"] == 0
    assert payload["summary"]["pending_count"] == 0
    assert payload["summary"]["failed_count"] == 0
    assert payload["distributions"] == {"task_type": [], "status": [], "tokens": []}
    assert payload["tokens"]["total"] == 0
    assert "clusters" not in payload
    assert payload["resume"]["running"] is False


@pytest.mark.asyncio
async def test_prompt_vectors_returns_embedding_summary_and_distributions(monkeypatch):
    async def fake_fetchrow(query, *args):
        lower = query.lower()
        if "analytics_prompt_vector_state" in lower and "to_regclass" in lower:
            return {"ready": True}
        if "analytics_prompt_token_stats" in lower and "to_regclass" in lower:
            return {"ready": True}
        if "candidate_count" in lower and "embedded_count" in lower and "failed_count" in lower:
            assert args == (DEFAULT_VECTOR_MODEL_ID, PROMPT_NORMALIZATION_VERSION)
            return {
                "candidate_count": 100,
                "embedded_count": 80,
                "failed_count": 2,
                "latest_embedded_at": "2026-07-04T12:00:00",
            }
        if "from analytics_prompt_token_stats" in lower and "count(*)" in lower:
            return {
                "token_count": 2,
                "token_stats_refreshed_at": "2026-07-04T13:00:00",
            }
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def fake_fetch(query, *args):
        lower = query.lower()
        if "from analytics_prompt_vector_state" in lower:
            return [
                {
                    "key": f"{DEFAULT_VECTOR_MODEL_ID}:{PROMPT_NORMALIZATION_VERSION}:embedding_dim",
                    "value": "4096",
                    "updated_at": "2026-07-04T12:00:00",
                },
                {
                    "key": f"{DEFAULT_VECTOR_MODEL_ID}:{PROMPT_NORMALIZATION_VERSION}:last_success_at",
                    "value": '"2026-07-04T12:00:00"',
                    "updated_at": "2026-07-04T12:00:00",
                },
                {
                    "key": f"{DEFAULT_VECTOR_MODEL_ID}:{PROMPT_NORMALIZATION_VERSION}:index_dir",
                    "value": '"/legacy/usearch/index"',
                    "updated_at": "2026-07-04T12:00:00",
                },
            ]
        if "from analytics_prompt_embeddings" in lower and "group by task_type" in lower:
            assert args == (DEFAULT_VECTOR_MODEL_ID, PROMPT_NORMALIZATION_VERSION)
            return [{"label": "edit", "count": 50}, {"label": "custom_video", "count": 30}]
        if "from analytics_prompt_embeddings" in lower and "group by status" in lower:
            assert args == (DEFAULT_VECTOR_MODEL_ID, PROMPT_NORMALIZATION_VERSION)
            return [{"label": "embedded", "count": 80}, {"label": "error", "count": 2}]
        if "from analytics_prompt_token_stats" in lower:
            return [
                {"label": "cinematic", "count": 12, "use_count": 30, "user_count": 10, "token_kind": "latin"},
                {"label": "少女", "count": 9, "use_count": 16, "user_count": 8, "token_kind": "cjk"},
            ]
        raise AssertionError(f"unexpected fetch query: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get("/api/prompt-vectors")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["summary"]["embedding_coverage"] == 80.0
    assert payload["summary"]["pending_count"] == 20
    assert payload["summary"]["failed_count"] == 2
    assert payload["model"]["embedding_dim"] == 4096
    assert "index_dir" not in payload["model"]
    assert payload["distributions"]["task_type"] == [
        {"label": "edit", "count": 50},
        {"label": "custom_video", "count": 30},
    ]
    assert payload["distributions"]["status"] == [
        {"label": "embedded", "count": 80},
        {"label": "error", "count": 2},
    ]
    assert payload["tokens"]["total"] == 2
    assert payload["distributions"]["tokens"] == [
        {"label": "cinematic", "count": 12, "use_count": 30, "user_count": 10, "token_kind": "latin"},
        {"label": "少女", "count": 9, "use_count": 16, "user_count": 8, "token_kind": "cjk"},
    ]
    assert "clusters" not in payload


@pytest.mark.asyncio
async def test_removed_prompt_analysis_routes_are_not_registered():
    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        paths = [
            "/api/prompt-vectors/clusters/cluster1",
            "/api/prompt-near-representatives",
            "/api/prompt-near-graph",
            "/api/prompt-scenes",
            "/api/prompt-graph",
        ]
        responses = [await client.get(path) for path in paths]

    assert [response.status_code for response in responses] == [404, 404, 404, 404, 404]


@pytest.mark.asyncio
async def test_prompt_tokens_returns_searchable_paginated_token_table(monkeypatch):
    async def fake_fetchrow(query, *args):
        lower = query.lower()
        if "analytics_prompt_token_stats" in lower and "to_regclass" in lower:
            return {"ready": True, "scope_summary_ready": True}
        if "from analytics_prompt_token_scope_summary" in lower:
            assert args == (PROMPT_NORMALIZATION_VERSION, PROMPT_TOKEN_VERSION, "all")
            return {"candidate_count": 100}
        if "candidate_count" in lower and "token_count" in lower:
            assert args == (PROMPT_NORMALIZATION_VERSION, PROMPT_TOKEN_VERSION, "all", 100, 5)
            return {
                "candidate_count": 100,
                "token_count": 2,
                "filtered_token_count": 1,
                "refreshed_at": "2026-07-07T00:30:00",
            }
        if "count(*)::bigint as total" in lower:
            assert args == (PROMPT_NORMALIZATION_VERSION, PROMPT_TOKEN_VERSION, "all", "光", 5)
            return {"total": 1}
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def fake_fetch(query, *args):
        lower = query.lower()
        if "distinct on" in lower and "analytics_prompt_token_stats" in lower:
            return []
        if "from analytics_prompt_token_stats" in lower:
            assert args == (PROMPT_NORMALIZATION_VERSION, PROMPT_TOKEN_VERSION, "all", "光", 5, 100, 20, 20)
            return [
                {
                    "token": "光影",
                    "token_kind": "cjk",
                    "prompt_count": 12,
                    "use_count": 30,
                    "user_count": 10,
                    "prompt_share": 12.0,
                    "refreshed_at": "2026-07-07T00:30:00",
                }
            ]
        raise AssertionError(f"unexpected fetch query: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get("/api/prompt-tokens", params={"q": "光", "page": 2, "limit": 20})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["query"] == "光"
    assert payload["min_prompt_count"] == 5
    assert payload["pagination"] == {"page": 2, "limit": 20, "total": 1, "has_next": False}
    assert payload["summary"]["filtered_token_count"] == 1
    assert payload["rows"] == [
        {
            "token": "光影",
            "token_kind": "cjk",
            "prompt_count": 12,
            "use_count": 30,
            "user_count": 10,
            "prompt_share": 12.0,
            "refreshed_at": "2026-07-07T00:30:00",
        }
    ]
    assert payload["scope"] == {"key": "all", "task_type": "", "model_key": "", "label": "全部词元"}


@pytest.mark.asyncio
async def test_prompt_tokens_can_filter_by_task_type_and_attached_model(monkeypatch):
    model_key = "qwen/YARN_1.0.safetensors"
    scope_key = f"model|edit|{model_key}"

    async def fake_fetchrow(query, *args):
        lower = query.lower()
        if "analytics_prompt_token_stats" in lower and "to_regclass" in lower:
            return {"ready": True, "scope_summary_ready": True}
        if "from analytics_prompt_token_scope_summary" in lower:
            assert args == (PROMPT_NORMALIZATION_VERSION, PROMPT_TOKEN_VERSION, scope_key)
            return {"candidate_count": 25}
        if "candidate_count" in lower and "token_count" in lower:
            assert args == (PROMPT_NORMALIZATION_VERSION, PROMPT_TOKEN_VERSION, scope_key, 25, 5)
            return {
                "candidate_count": 25,
                "token_count": 8,
                "filtered_token_count": 1,
                "refreshed_at": "2026-07-07T13:20:00",
            }
        if "count(*)::bigint as total" in lower:
            assert args == (PROMPT_NORMALIZATION_VERSION, PROMPT_TOKEN_VERSION, scope_key, "光", 5)
            return {"total": 1}
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def fake_fetch(query, *args):
        lower = query.lower()
        if "scope_kind = 'task'" in lower:
            return [
                {"value": "edit", "label": "自由P图"},
                {"value": "unavailable_task", "label": "无可用任务"},
            ]
        if "scope_kind = 'model'" in lower:
            assert args == (PROMPT_NORMALIZATION_VERSION, PROMPT_TOKEN_VERSION, "edit")
            return [
                {
                    "task_type": "edit",
                    "value": model_key,
                    "label": "逼真",
                    "scope_key": scope_key,
                }
            ]
        if "from analytics_prompt_token_stats" in lower:
            assert args == (PROMPT_NORMALIZATION_VERSION, PROMPT_TOKEN_VERSION, scope_key, "光", 5, 25, 20, 0)
            return [
                {
                    "token": "光影",
                    "token_kind": "cjk",
                    "prompt_count": 5,
                    "use_count": 9,
                    "user_count": 4,
                    "prompt_share": 20.0,
                    "refreshed_at": "2026-07-07T13:20:00",
                }
            ]
        raise AssertionError(f"unexpected fetch query: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get(
            "/api/prompt-tokens",
            params={"q": "光", "task_type": "img2img_lora", "model_key": model_key, "page": 1, "limit": 20},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["scope"] == {
        "key": scope_key,
        "task_type": "edit",
        "model_key": model_key,
        "label": "自由P图 / 逼真",
    }
    assert payload["filters"]["tasks"] == [
        {"value": "edit", "label": "自由P图"},
        {"value": "unavailable_task", "label": "无可用任务"},
    ]
    assert payload["filters"]["models"] == [
        {"task_type": "edit", "value": model_key, "label": "逼真", "scope_key": scope_key}
    ]
    assert payload["rows"][0]["prompt_count"] == 5


@pytest.mark.asyncio
async def test_prompt_tokens_can_skip_filter_options_for_fast_pagination(monkeypatch):
    async def fake_fetchrow(query, *args):
        lower = query.lower()
        if "analytics_prompt_token_stats" in lower and "to_regclass" in lower:
            return {"ready": True, "scope_summary_ready": True}
        if "from analytics_prompt_token_scope_summary" in lower:
            return {"candidate_count": 100}
        if "candidate_count" in lower and "token_count" in lower:
            return {
                "candidate_count": 100,
                "token_count": 2,
                "filtered_token_count": 2,
                "refreshed_at": "2026-07-07T00:30:00",
            }
        if "count(*)::bigint as total" in lower:
            return {"total": 2}
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def fake_fetch(query, *args):
        lower = query.lower()
        if "distinct on" in lower:
            raise AssertionError("filter options should not be queried when include_filters=false")
        if "from analytics_prompt_token_stats" in lower:
            return [
                {
                    "token": "光影",
                    "token_kind": "cjk",
                    "prompt_count": 12,
                    "use_count": 30,
                    "user_count": 10,
                    "prompt_share": 12.0,
                    "refreshed_at": "2026-07-07T00:30:00",
                }
            ]
        raise AssertionError(f"unexpected fetch query: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get("/api/prompt-tokens", params={"include_filters": "false"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["filters"] == {"tasks": [], "models": []}
    assert payload["filters_included"] is False


@pytest.mark.asyncio
async def test_prompt_tokens_allows_deep_last_page(monkeypatch):
    async def fake_fetchrow(query, *args):
        lower = query.lower()
        if "analytics_prompt_token_stats" in lower and "to_regclass" in lower:
            return {"ready": True, "scope_summary_ready": True}
        if "from analytics_prompt_token_scope_summary" in lower:
            return {"candidate_count": 773998}
        if "select\n                coalesce" in query:
            return {
                "candidate_count": 773998,
                "token_count": 3574756,
                "filtered_token_count": 3574756,
                "refreshed_at": "2026-07-07T01:27:46",
            }
        if "candidate_count" in lower and "token_count" in lower:
            assert args == (PROMPT_NORMALIZATION_VERSION, PROMPT_TOKEN_VERSION, "all", 773998, 1)
            return {
                "candidate_count": 773998,
                "token_count": 3574756,
                "filtered_token_count": 3574756,
                "refreshed_at": "2026-07-07T01:27:46",
            }
        if "count(*)" in lower and "from analytics_prompt_token_stats" in lower:
            return {"total": 3574756}
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def fake_fetch(query, *args):
        if "distinct on" in query.lower() and "analytics_prompt_token_stats" in query.lower():
            return []
        assert args == (
            PROMPT_NORMALIZATION_VERSION,
            PROMPT_TOKEN_VERSION,
            "all",
            "",
            1,
            773998,
            15,
            3_574_755,
        )
        return [
            {
                "token": "末页",
                "token_kind": "cjk",
                "prompt_count": 1,
                "use_count": 1,
                "user_count": 1,
                "prompt_share": 0.0001,
                "refreshed_at": "2026-07-07T01:27:46",
            }
        ]

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get("/api/prompt-tokens", params={"page": 238318, "limit": 15, "min_prompt_count": 1})

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"] == {"page": 238318, "limit": 15, "total": 3574756, "has_next": False}
    assert payload["rows"][0]["token"] == "末页"


@pytest.mark.asyncio
async def test_prompt_token_prompts_returns_prompt_rows_with_other_tokens(monkeypatch):
    async def fake_fetchrow(query, *args):
        lower = query.lower()
        if "analytics_prompt_token_stats" in lower and "to_regclass" in lower:
            return {"ready": True}
        if "from analytics_prompt_token_stats" in lower:
            assert args == (PROMPT_NORMALIZATION_VERSION, PROMPT_TOKEN_VERSION, "all", "光影", 5)
            return {
                "token": "光影",
                "token_kind": "cjk",
                "prompt_count": 12,
                "use_count": 30,
                "user_count": 10,
                "refreshed_at": "2026-07-07T00:30:00",
            }
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def fake_fetch(query, *args):
        lower = query.lower()
        if "from analytics_prompt_token_prompts" in lower:
            assert args == (PROMPT_NORMALIZATION_VERSION, PROMPT_TOKEN_VERSION, "光影", "all", 20, 0)
            return [
                {
                    "prompt_hash": "a" * 32,
                    "prompt": "少女 光影 portrait",
                    "tokens": ["少女", "低频词", "光影", "portrait"],
                    "task_types": ["edit"],
                    "scopes": ["all", "edit"],
                    "char_count": 14,
                    "uses": 5,
                    "users": 3,
                    "quality_score": 88.5,
                    "last_seen": "2026-07-07T00:20:00",
                }
            ]
        if "from analytics_prompt_token_stats" in lower and "token = any" in lower:
            assert args == (PROMPT_NORMALIZATION_VERSION, PROMPT_TOKEN_VERSION, "all", 5, ["少女", "低频词", "portrait"])
            return [{"token": "少女"}, {"token": "portrait"}]
        raise AssertionError(f"unexpected fetch query: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get("/api/prompt-token-prompts", params={"token": "光影"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["prompt_count"] == 12
    assert payload["pagination"] == {"page": 1, "limit": 20, "total": 12, "has_next": False}
    assert payload["rows"][0]["prompt_preview"] == "少女 光影 portrait"
    assert payload["min_prompt_count"] == 5
    assert payload["rows"][0]["tokens"] == ["少女", "低频词", "光影", "portrait"]
    assert payload["rows"][0]["other_tokens"] == ["少女", "portrait"]


@pytest.mark.asyncio
async def test_prompt_tokens_filters_low_frequency_terms_with_configurable_threshold(monkeypatch):
    async def fake_fetchrow(query, *args):
        lower = query.lower()
        if "analytics_prompt_token_stats" in lower and "to_regclass" in lower:
            return {"ready": True, "scope_summary_ready": True}
        if "from analytics_prompt_token_scope_summary" in lower:
            return {"candidate_count": 100}
        if "candidate_count" in lower and "token_count" in lower:
            assert args == (PROMPT_NORMALIZATION_VERSION, PROMPT_TOKEN_VERSION, "all", 100, 10)
            return {
                "candidate_count": 100,
                "token_count": 3,
                "filtered_token_count": 1,
                "refreshed_at": "2026-07-07T00:30:00",
            }
        if "count(*)::bigint as total" in lower:
            assert args == (PROMPT_NORMALIZATION_VERSION, PROMPT_TOKEN_VERSION, "all", "", 10)
            return {"total": 1}
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def fake_fetch(query, *args):
        lower = query.lower()
        if "distinct on" in lower and "analytics_prompt_token_stats" in lower:
            return []
        if "from analytics_prompt_token_stats" in lower:
            assert args == (PROMPT_NORMALIZATION_VERSION, PROMPT_TOKEN_VERSION, "all", "", 10, 100, 50, 0)
            return [
                {
                    "token": "高频词",
                    "token_kind": "cjk",
                    "prompt_count": 10,
                    "use_count": 15,
                    "user_count": 9,
                    "prompt_share": 10.0,
                    "refreshed_at": "2026-07-07T00:30:00",
                }
            ]
        raise AssertionError(f"unexpected fetch query: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get("/api/prompt-tokens", params={"min_prompt_count": 10})

    assert response.status_code == 200
    payload = response.json()
    assert payload["min_prompt_count"] == 10
    assert payload["pagination"]["total"] == 1
    assert payload["rows"][0]["token"] == "高频词"


@pytest.mark.asyncio
async def test_prompt_tokens_excludes_soft_deleted_terms_when_deletion_table_exists(monkeypatch):
    async def fake_fetchrow(query, *args):
        lower = query.lower()
        if "analytics_prompt_token_stats" in lower and "to_regclass" in lower:
            return {"ready": True, "deletion_ready": True, "scope_summary_ready": True}
        if "from analytics_prompt_token_scope_summary" in lower:
            return {"candidate_count": 100}
        if "candidate_count" in lower and "token_count" in lower:
            assert "analytics_prompt_token_deleted_rules" in lower
            assert args == (PROMPT_NORMALIZATION_VERSION, PROMPT_TOKEN_VERSION, "all", 100, 5)
            return {
                "candidate_count": 100,
                "token_count": 1,
                "filtered_token_count": 1,
                "refreshed_at": "2026-07-07T00:30:00",
            }
        if "count(*)::bigint as total" in lower:
            assert "analytics_prompt_token_deleted_rules" in lower
            assert args == (PROMPT_NORMALIZATION_VERSION, PROMPT_TOKEN_VERSION, "all", "", 5)
            return {"total": 1}
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def fake_fetch(query, *args):
        lower = query.lower()
        if "distinct on" in lower and "analytics_prompt_token_stats" in lower:
            return []
        if "from analytics_prompt_token_stats" in lower:
            assert "analytics_prompt_token_deleted_rules" in lower
            assert args == (PROMPT_NORMALIZATION_VERSION, PROMPT_TOKEN_VERSION, "all", "", 5, 100, 50, 0)
            return [
                {
                    "token": "保留词",
                    "token_kind": "cjk",
                    "prompt_count": 10,
                    "use_count": 15,
                    "user_count": 9,
                    "prompt_share": 10.0,
                    "refreshed_at": "2026-07-07T00:30:00",
                }
            ]
        raise AssertionError(f"unexpected fetch query: {query}")

    monkeypatch.setattr(routes_prompts, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(routes_prompts, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get("/api/prompt-tokens")

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total"] == 1
    assert payload["rows"][0]["token"] == "保留词"


@pytest.mark.asyncio
async def test_prompt_token_prompts_excludes_soft_deleted_other_tokens(monkeypatch):
    async def fake_fetchrow(query, *args):
        lower = query.lower()
        if "analytics_prompt_token_stats" in lower and "to_regclass" in lower:
            return {"ready": True, "deletion_ready": True}
        if "from analytics_prompt_token_stats" in lower:
            assert "analytics_prompt_token_deleted_rules" in lower
            assert args == (PROMPT_NORMALIZATION_VERSION, PROMPT_TOKEN_VERSION, "all", "光影", 5)
            return {
                "token": "光影",
                "token_kind": "cjk",
                "prompt_count": 12,
                "use_count": 30,
                "user_count": 10,
                "refreshed_at": "2026-07-07T00:30:00",
            }
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def fake_fetch(query, *args):
        lower = query.lower()
        if "from analytics_prompt_token_prompts" in lower:
            return [
                {
                    "prompt_hash": "a" * 32,
                    "prompt": "少女 光影 删除词",
                    "tokens": ["少女", "删除词", "光影"],
                    "task_types": ["edit"],
                    "scopes": ["all", "edit"],
                    "char_count": 14,
                    "uses": 5,
                    "users": 3,
                    "quality_score": 88.5,
                    "last_seen": "2026-07-07T00:20:00",
                }
            ]
        if "from analytics_prompt_token_stats" in lower and "token = any" in lower:
            assert "analytics_prompt_token_deleted_rules" in lower
            assert args == (PROMPT_NORMALIZATION_VERSION, PROMPT_TOKEN_VERSION, "all", 5, ["少女", "删除词"])
            return [{"token": "少女"}]
        raise AssertionError(f"unexpected fetch query: {query}")

    monkeypatch.setattr(routes_prompts, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(routes_prompts, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get("/api/prompt-token-prompts", params={"token": "光影"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["rows"][0]["tokens"] == ["少女", "删除词", "光影"]
    assert payload["rows"][0]["other_tokens"] == ["少女"]


@pytest.mark.asyncio
async def test_prompt_token_deletions_can_be_listed_marked_and_restored(monkeypatch):
    execute_calls = []

    async def fake_execute(query, *args):
        execute_calls.append((query, args))
        return "OK"

    async def fake_fetch(query, *args):
        lower = query.lower()
        if "from analytics_prompt_token_deleted_rules" in lower:
            assert args == (PROMPT_NORMALIZATION_VERSION, PROMPT_TOKEN_VERSION, "all")
            return [
                {
                    "token": "删除词",
                    "deleted_at": "2026-07-07T12:00:00",
                    "updated_at": "2026-07-07T12:00:00",
                    "token_kind": "cjk",
                    "prompt_count": 8,
                    "use_count": 11,
                    "user_count": 5,
                    "refreshed_at": "2026-07-07T11:00:00",
                }
            ]
        raise AssertionError(f"unexpected fetch query: {query}")

    monkeypatch.setattr(routes_prompts, "_execute", fake_execute)
    monkeypatch.setattr(routes_prompts, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        list_response = await client.get("/api/prompt-token-deletions")
        delete_response = await client.post("/api/prompt-token-deletions", json={"token": " 删除词 "})
        restore_response = await client.post("/api/prompt-token-deletions/restore", json={"token": "删除词"})

    assert list_response.status_code == 200
    assert list_response.json()["rows"][0]["token"] == "删除词"
    assert delete_response.status_code == 200
    assert delete_response.json() == {"status": "deleted", "token": "删除词"}
    assert restore_response.status_code == 200
    assert restore_response.json() == {"status": "restored", "token": "删除词"}
    assert any("insert into analytics_prompt_token_deleted_rules" in query.lower() for query, _args in execute_calls)
    assert any("delete from analytics_prompt_token_deleted_rules" in query.lower() for query, _args in execute_calls)


@pytest.mark.asyncio
async def test_prompt_token_aliases_list_filters_disabled_rules(monkeypatch):
    queries = []
    state_rows = [
        {
            "key": f"{DEFAULT_VECTOR_MODEL_ID}:{PROMPT_NORMALIZATION_VERSION}:prompt_token_alias_rules_updated_at",
            "value": "2026-07-08T10:00:00+00:00",
            "updated_at": "2026-07-08T10:00:00+00:00",
        },
        {
            "key": f"{DEFAULT_VECTOR_MODEL_ID}:{PROMPT_NORMALIZATION_VERSION}:prompt_token_alias_applied_at",
            "value": "2026-07-08T10:00:00+00:00",
            "updated_at": "2026-07-08T10:00:00+00:00",
        },
    ]

    async def fake_execute(*args, **kwargs):
        return "OK"

    async def fake_fetch(query, *args):
        queries.append(query)
        lower = query.lower()
        if "from analytics_prompt_vector_state" in lower:
            return state_rows
        if "from analytics_prompt_token_alias_rules" in lower:
            assert "where enabled" in lower
            return [
                {
                    "id": 1,
                    "representative_token": "面部",
                    "alias_tokens": ["脸部"],
                    "aliases_text": "脸部",
                    "category_key": "body_part",
                    "category_label": "身体部分",
                    "subcategory_key": "face",
                    "subcategory_label": "面部",
                    "source": "manual",
                    "seed_batch": "",
                    "enabled": True,
                    "sort_order": 0,
                    "updated_at": "2026-07-08T10:00:00",
                }
            ]
        raise AssertionError(f"unexpected fetch query: {query}")

    monkeypatch.setattr(analytics_main, "_execute", fake_execute)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get("/api/prompt-token-aliases")

    assert response.status_code == 200
    assert response.json()["rows"][0]["representative"] == "面部"
    assert any("from analytics_prompt_token_alias_rules" in query.lower() for query in queries)


@pytest.mark.asyncio
async def test_prompt_token_aliases_can_be_saved_and_report_pending(monkeypatch):
    execute_calls = []
    state_rows = [
        {
            "key": f"{DEFAULT_VECTOR_MODEL_ID}:{PROMPT_NORMALIZATION_VERSION}:prompt_token_alias_rules_updated_at",
            "value": "2026-07-07T14:40:00+00:00",
            "updated_at": "2026-07-07T14:40:00+00:00",
        },
        {
            "key": f"{DEFAULT_VECTOR_MODEL_ID}:{PROMPT_NORMALIZATION_VERSION}:prompt_token_alias_applied_at",
            "value": "2026-07-07T14:20:00+00:00",
            "updated_at": "2026-07-07T14:20:00+00:00",
        },
    ]

    async def fake_execute(query, *args):
        execute_calls.append((query, args))
        return "OK"

    async def fake_fetch(query, *args):
        lower = query.lower()
        if "from analytics_prompt_vector_state" in lower:
            return state_rows
        if "from analytics_prompt_token_alias_rules" in lower:
            return []
        raise AssertionError(f"unexpected fetch query: {query}")

    monkeypatch.setattr(analytics_main, "_execute", fake_execute)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.put(
            "/api/prompt-token-aliases",
            json={
                "rows": [
                    {
                        "representative": "面部",
                        "aliases_text": "脸部，面容, 面容",
                        "category_key": "body_part",
                        "category_label": "身体部分",
                        "subcategory_key": "face",
                        "subcategory_label": "面部",
                    }
                ]
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "saved"
    assert payload["row_count"] == 1
    assert payload["alias_count"] == 2
    assert payload["alias_status"]["pending"] is True
    replace_payload = execute_calls[-2][1][0]
    assert "面部" in replace_payload
    assert "脸部" in replace_payload
    assert "body_part" in replace_payload


@pytest.mark.asyncio
async def test_prompt_token_aliases_reject_conflicting_aliases(monkeypatch):
    async def fail_execute(*args, **kwargs):
        raise AssertionError("invalid alias rules should not write")

    monkeypatch.setattr(analytics_main, "_execute", fail_execute)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.put(
            "/api/prompt-token-aliases",
            json={
                "rows": [
                    {"representative": "面部", "aliases_text": "脸部"},
                    {"representative": "相貌", "aliases_text": "脸部"},
                ]
            },
        )

    assert response.status_code == 400
    assert "同义词元重复映射" in response.json()["detail"]


@pytest.mark.asyncio
async def test_prompt_token_custom_terms_list_filters_disabled_rules(monkeypatch):
    queries = []
    state_rows = [
        {
            "key": f"{DEFAULT_VECTOR_MODEL_ID}:{PROMPT_NORMALIZATION_VERSION}:prompt_token_custom_terms_updated_at",
            "value": "2026-07-08T10:00:00+00:00",
            "updated_at": "2026-07-08T10:00:00+00:00",
        },
        {
            "key": f"{DEFAULT_VECTOR_MODEL_ID}:{PROMPT_NORMALIZATION_VERSION}:prompt_token_custom_terms_applied_at",
            "value": "2026-07-08T10:00:00+00:00",
            "updated_at": "2026-07-08T10:00:00+00:00",
        },
    ]

    async def fake_execute(*args, **kwargs):
        return "OK"

    async def fake_fetch(query, *args):
        queries.append(query)
        lower = query.lower()
        if "from analytics_prompt_vector_state" in lower:
            return state_rows
        if "from analytics_prompt_token_custom_terms" in lower:
            assert "where enabled" in lower
            return [
                {
                    "id": 1,
                    "term": "高马尾",
                    "category_key": "appearance",
                    "category_label": "外观特征",
                    "subcategory_key": "hair",
                    "subcategory_label": "头发",
                    "source": "manual",
                    "seed_batch": "",
                    "notes": "hair style",
                    "enabled": True,
                    "sort_order": 0,
                    "updated_at": "2026-07-08T10:00:00",
                }
            ]
        raise AssertionError(f"unexpected fetch query: {query}")

    monkeypatch.setattr(analytics_main, "_execute", fake_execute)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get("/api/prompt-token-custom-terms")

    assert response.status_code == 200
    assert response.json()["rows"][0]["term"] == "高马尾"
    assert any("from analytics_prompt_token_custom_terms" in query.lower() for query in queries)


@pytest.mark.asyncio
async def test_prompt_token_custom_terms_can_be_saved_and_report_pending(monkeypatch):
    execute_calls = []
    state_rows = [
        {
            "key": f"{DEFAULT_VECTOR_MODEL_ID}:{PROMPT_NORMALIZATION_VERSION}:prompt_token_custom_terms_updated_at",
            "value": "2026-07-07T15:40:00+00:00",
            "updated_at": "2026-07-07T15:40:00+00:00",
        },
        {
            "key": f"{DEFAULT_VECTOR_MODEL_ID}:{PROMPT_NORMALIZATION_VERSION}:prompt_token_custom_terms_applied_at",
            "value": "2026-07-07T15:20:00+00:00",
            "updated_at": "2026-07-07T15:20:00+00:00",
        },
    ]

    async def fake_execute(query, *args):
        execute_calls.append((query, args))
        return "OK"

    async def fake_fetch(query, *args):
        lower = query.lower()
        if "from analytics_prompt_vector_state" in lower:
            return state_rows
        if "from analytics_prompt_token_custom_terms" in lower:
            return [
                {
                    "id": 1,
                    "term": "高马尾",
                    "category_key": "appearance",
                    "category_label": "外观特征",
                    "subcategory_key": "hair",
                    "subcategory_label": "头发",
                    "source": "manual",
                    "seed_batch": "",
                    "notes": "hair style",
                    "enabled": True,
                    "sort_order": 0,
                    "updated_at": "2026-07-07T15:00:00",
                }
            ]
        raise AssertionError(f"unexpected fetch query: {query}")

    monkeypatch.setattr(analytics_main, "_execute", fake_execute)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        list_response = await client.get("/api/prompt-token-custom-terms")
        save_response = await client.put(
            "/api/prompt-token-custom-terms",
            json={
                "rows": [
                    {
                        "term": "高马尾，蓝紫渐变发色",
                        "category_key": "appearance",
                        "category_label": "外观特征",
                        "subcategory_key": "hair",
                        "subcategory_label": "头发",
                        "notes": "hair terms",
                    },
                    {"term": "高马尾"},
                ]
            },
        )

    assert list_response.status_code == 200
    assert list_response.json()["rows"][0]["term"] == "高马尾"
    assert list_response.json()["rows"][0]["category_key"] == "appearance"
    assert save_response.status_code == 200
    payload = save_response.json()
    assert payload["status"] == "saved"
    assert payload["row_count"] == 2
    assert payload["custom_term_status"]["pending"] is True
    replace_payload = execute_calls[-2][1][0]
    assert "高马尾" in replace_payload
    assert "蓝紫渐变发色" in replace_payload
    assert "appearance" in replace_payload


@pytest.mark.asyncio
async def test_prompt_token_generated_rule_overwrite_replaces_manual_tables(monkeypatch):
    execute_calls = []
    state_rows = [
        {
            "key": f"{DEFAULT_VECTOR_MODEL_ID}:{PROMPT_NORMALIZATION_VERSION}:prompt_token_alias_rules_updated_at",
            "value": "2026-07-07T16:00:00+00:00",
            "updated_at": "2026-07-07T16:00:00+00:00",
        },
        {
            "key": f"{DEFAULT_VECTOR_MODEL_ID}:{PROMPT_NORMALIZATION_VERSION}:prompt_token_custom_terms_updated_at",
            "value": "2026-07-07T16:00:00+00:00",
            "updated_at": "2026-07-07T16:00:00+00:00",
        },
    ]

    async def fake_execute(query, *args):
        execute_calls.append((query, args))
        return "OK"

    async def fake_fetch(query, *args):
        lower = query.lower()
        if "from analytics_prompt_vector_state" in lower:
            return state_rows
        if "from analytics_prompt_token_stats" in lower:
            return [
                {"token": "无毛小穴", "token_kind": "cjk", "prompt_count": 120, "use_count": 180, "user_count": 90},
                {"token": "林子瑜的房子", "token_kind": "cjk", "prompt_count": 80, "use_count": 100, "user_count": 60},
            ]
        raise AssertionError(f"unexpected fetch query: {query}")

    monkeypatch.setattr(analytics_main, "_execute", fake_execute)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.post("/api/prompt-token-rules/overwrite-generated")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "overwritten"
    assert payload["report"]["coverage"]["decomposed"] >= 2
    assert payload["deletions"] == {"rows": [], "total": 0}
    assert any(row["term"] == "无毛" for row in payload["custom_terms"]["rows"])
    assert any(row["term"] == "小穴" for row in payload["custom_terms"]["rows"])
    assert any(row["term"] == "房子" for row in payload["custom_terms"]["rows"])
    vagina_rule = next(row for row in payload["aliases"]["rows"] if row["representative"] == "阴道")
    assert "小穴" in vagina_rule["aliases"]
    overwrite_query, overwrite_args = execute_calls[-1]
    assert "delete from analytics_prompt_token_deleted_rules" in overwrite_query.lower()
    assert "delete from analytics_prompt_token_custom_terms" in overwrite_query.lower()
    assert "delete from analytics_prompt_token_alias_rules" in overwrite_query.lower()
    assert "无毛" in overwrite_args[0]
    assert "阴道" in overwrite_args[1]


@pytest.mark.asyncio
async def test_prompt_token_custom_terms_reject_invalid_terms(monkeypatch):
    async def fail_execute(*args, **kwargs):
        raise AssertionError("invalid custom terms should not write")

    monkeypatch.setattr(analytics_main, "_execute", fail_execute)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.put(
            "/api/prompt-token-custom-terms",
            json={"rows": [{"term": "的"}]},
        )

    assert response.status_code == 400
    assert "指定词元无效" in response.json()["detail"]


@pytest.mark.asyncio
async def test_prompt_token_alias_rebuild_starts_tokens_only_process(monkeypatch, tmp_path):
    calls = {}

    class FakeProcess:
        pid = 5252

        def poll(self):
            return 0

    def fake_popen(command, **kwargs):
        calls["command"] = command
        calls["kwargs"] = kwargs
        return FakeProcess()

    async def fake_fetch(query, *args):
        if "from analytics_prompt_vector_state" in query.lower():
            return []
        raise AssertionError(f"unexpected fetch query: {query}")

    monkeypatch.setattr(analytics_main, "PROMPT_VECTOR_RESUME_LOG", tmp_path / "resume.log")
    monkeypatch.setattr(analytics_main, "_database_url", lambda: "postgresql://local/test")
    monkeypatch.setattr(analytics_main, "_is_prompt_vector_refresh_lock_held", lambda: False)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)
    monkeypatch.setattr(analytics_main.subprocess, "Popen", fake_popen)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.post("/api/prompt-token-aliases/rebuild")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "started"
    assert payload["pid"] == 5252
    assert calls["command"][1:4] == ["-m", "app.refresh_prompt_vectors", "--tokens-only"]
    assert "--statement-timeout-ms" in calls["command"]
    assert calls["kwargs"]["env"]["LOCAL_ANALYTICS_DATABASE_URL"] == "postgresql://local/test"


@pytest.mark.asyncio
async def test_prompt_vectors_resume_starts_embed_only_process(monkeypatch, tmp_path):
    calls = {}

    class FakeProcess:
        pid = 4242

        def poll(self):
            return None

    def fake_popen(command, **kwargs):
        calls["command"] = command
        calls["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(analytics_main, "PROMPT_VECTOR_RESUME_LOG", tmp_path / "resume.log")
    monkeypatch.setattr(analytics_main, "_database_url", lambda: "postgresql://local/test")
    monkeypatch.setattr(analytics_main, "_is_prompt_vector_refresh_lock_held", lambda: False)
    monkeypatch.setattr(analytics_main.subprocess, "Popen", fake_popen)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.post("/api/prompt-vectors/resume")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "started"
    assert payload["pid"] == 4242
    assert calls["command"][1:4] == ["-m", "app.refresh_prompt_vectors", "--embed-only"]
    assert "--batch-size" in calls["command"]
    assert "--data-dir" in calls["command"]
    assert "--skip-token-refresh" in calls["command"]
    assert calls["kwargs"]["env"]["LOCAL_ANALYTICS_DATABASE_URL"] == "postgresql://local/test"


@pytest.mark.asyncio
async def test_prompt_vectors_resume_reports_running_when_lock_is_held(monkeypatch, tmp_path):
    def fail_popen(*args, **kwargs):
        raise AssertionError("resume should not start a second process")

    monkeypatch.setattr(analytics_main, "PROMPT_VECTOR_RESUME_LOG", tmp_path / "resume.log")
    monkeypatch.setattr(analytics_main, "_is_prompt_vector_refresh_lock_held", lambda: True)
    monkeypatch.setattr(analytics_main.subprocess, "Popen", fail_popen)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.post("/api/prompt-vectors/resume")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "running"
    assert payload["resume"]["lock_held"] is True
