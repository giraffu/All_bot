import pytest
from httpx import ASGITransport, AsyncClient

from local_analytics_platform.app import main as analytics_main
from local_analytics_platform.app import routes_prompts
from local_analytics_platform.app.prompt_decomposition import (
    PROMPT_DECOMPOSITION_SAVED_SCHEMA_SQL,
    build_prompt_decomposition_token_metadata,
    prompt_decomposition_filter_groups,
    prompt_decomposition_grouped_tokens,
)


def test_prompt_decomposition_schema_contains_saved_template_table():
    schema_sql = "\n".join(PROMPT_DECOMPOSITION_SAVED_SCHEMA_SQL).lower()

    assert "create table if not exists analytics_prompt_decomposition_saved_templates" in schema_sql
    assert "grouped_tokens jsonb not null default '[]'::jsonb" in schema_sql
    assert "unique (scope_key, prompt_hash)" in schema_sql
    assert "idx_prompt_decomposition_saved_scope_updated" in schema_sql


def test_prompt_decomposition_groups_split_items_and_visual_layers():
    metadata = build_prompt_decomposition_token_metadata(
        [
            {"term": "卧室", "category_label": "场景", "subcategory_label": "地点"},
            {"term": "床", "category_label": "场景", "subcategory_label": "家具"},
            {"term": "铁链", "category_label": "成人主题", "subcategory_label": "器具道具"},
            {"term": "一致", "category_label": "保持口径", "subcategory_label": "一致"},
            {"term": "深蹲", "category_label": "动作姿势", "subcategory_label": "姿势"},
            {"term": "乳房", "category_label": "身体部分", "subcategory_label": "胸部"},
        ],
        [
            {"representative_token": "写实", "category_label": "风格质量", "subcategory_label": "质量"},
            {"representative_token": "俯拍", "category_label": "镜头构图", "subcategory_label": "角度"},
        ],
    )

    filters = prompt_decomposition_filter_groups(
        [
            {"token": "卧室", "prompt_count": 80, "use_count": 100, "user_count": 30},
            {"token": "床", "prompt_count": 60, "use_count": 90, "user_count": 24},
            {"token": "铁链", "prompt_count": 40, "use_count": 70, "user_count": 18},
            {"token": "写实", "prompt_count": 75, "use_count": 88, "user_count": 26},
            {"token": "俯拍", "prompt_count": 55, "use_count": 66, "user_count": 21},
        ],
        metadata,
    )
    grouped = prompt_decomposition_grouped_tokens(
        ["一致", "卧室", "床", "铁链", "写实", "俯拍", "乳房", "深蹲"],
        metadata,
    )

    filter_labels = [item["label"] for item in filters]
    assert filter_labels == ["场景", "物品", "画面风格构图"]
    assert filters[0]["subgroups"][0]["label"] == "地点"
    assert filters[1]["subgroups"][0]["label"] in {"场景物件", "成人道具"}
    assert any(group["label"] == "画面风格构图" for group in grouped)
    assert any(group["label"] == "身体细节" for group in grouped)
    assert any(group["label"] == "物品" and "床" in group["tokens"] for group in grouped)
    assert any(group["label"] == "物品" and "铁链" in group["tokens"] for group in grouped)


@pytest.mark.asyncio
async def test_prompt_decomposition_returns_stable_empty_state_when_tables_missing(monkeypatch):
    async def fake_prompt_token_tables_status():
        return {"ready": False, "deletion_ready": True, "scope_summary_ready": True}

    monkeypatch.setattr(routes_prompts, "_prompt_token_tables_status", fake_prompt_token_tables_status)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get("/api/prompt-decomposition")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is False
    assert payload["rows"] == []
    assert payload["filters"] == {"groups": []}
    assert payload["summary"]["candidate_count"] == 0


@pytest.mark.asyncio
async def test_prompt_decomposition_returns_filters_and_grouped_prompt_rows(monkeypatch):
    async def fake_prompt_token_tables_status():
        return {"ready": True, "deletion_ready": True, "scope_summary_ready": True}

    async def fake_token_metadata():
        return build_prompt_decomposition_token_metadata(
            [
                {"term": "一致", "category_label": "保持口径", "subcategory_label": "一致"},
                {"term": "卧室", "category_label": "场景", "subcategory_label": "地点"},
                {"term": "床", "category_label": "场景", "subcategory_label": "家具"},
                {"term": "丝袜", "category_label": "服饰配件", "subcategory_label": "衣物"},
                {"term": "乳房", "category_label": "身体部分", "subcategory_label": "胸部"},
                {"term": "精液", "category_label": "成人主题", "subcategory_label": "体液"},
            ],
            [
                {"representative_token": "写实", "category_label": "风格质量", "subcategory_label": "质量"},
                {"representative_token": "俯拍", "category_label": "镜头构图", "subcategory_label": "角度"},
            ],
        )

    async def fake_candidate_count(scope_key, *, summary_ready):
        assert scope_key == "edit"
        assert summary_ready is True
        return 200

    async def fake_saved_rows(scope_key, *, limit=20):
        assert scope_key == "edit"
        return 2, []

    async def fake_fetchrow(query, *args):
        lower = query.lower()
        if "count(*)::bigint as total" in lower and "analytics_prompt_token_prompts" in lower:
            assert args[2] == "edit"
            assert args[4] == ["一致", "卧室"]
            return {"total": 1}
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def fake_fetch(query, *args):
        lower = query.lower()
        if "from analytics_prompt_token_stats" in lower:
            return [
                {"token": "一致", "prompt_count": 120, "use_count": 150, "user_count": 80, "refreshed_at": "2026-07-09T20:00:00"},
                {"token": "卧室", "prompt_count": 90, "use_count": 110, "user_count": 60, "refreshed_at": "2026-07-09T20:00:00"},
                {"token": "床", "prompt_count": 70, "use_count": 90, "user_count": 45, "refreshed_at": "2026-07-09T20:00:00"},
                {"token": "丝袜", "prompt_count": 65, "use_count": 88, "user_count": 40, "refreshed_at": "2026-07-09T20:00:00"},
                {"token": "乳房", "prompt_count": 80, "use_count": 100, "user_count": 50, "refreshed_at": "2026-07-09T20:00:00"},
                {"token": "精液", "prompt_count": 55, "use_count": 84, "user_count": 38, "refreshed_at": "2026-07-09T20:00:00"},
                {"token": "写实", "prompt_count": 58, "use_count": 86, "user_count": 39, "refreshed_at": "2026-07-09T20:00:00"},
                {"token": "俯拍", "prompt_count": 52, "use_count": 75, "user_count": 32, "refreshed_at": "2026-07-09T20:00:00"},
            ]
        if "from analytics_prompt_token_prompts" in lower:
            return [
                {
                    "prompt_hash": "hash-1",
                    "prompt": "保持人物一致，在卧室床上俯拍，丝袜，乳房沾有精液，写实风格",
                    "tokens": ["一致", "卧室", "床", "俯拍", "丝袜", "乳房", "精液", "写实"],
                    "task_types": ["edit"],
                    "scopes": ["all", "edit"],
                    "char_count": 30,
                    "uses": 18,
                    "users": 12,
                    "quality_score": 91.3,
                    "last_seen": "2026-07-09T20:10:00",
                }
            ]
        raise AssertionError(f"unexpected fetch query: {query}")

    monkeypatch.setattr(routes_prompts, "_prompt_token_tables_status", fake_prompt_token_tables_status)
    monkeypatch.setattr(routes_prompts, "_prompt_decomposition_token_metadata", fake_token_metadata)
    monkeypatch.setattr(routes_prompts, "_prompt_token_scope_candidate_count", fake_candidate_count)
    monkeypatch.setattr(routes_prompts, "_prompt_decomposition_saved_rows", fake_saved_rows)
    monkeypatch.setattr(routes_prompts, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(routes_prompts, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get(
            "/api/prompt-decomposition",
            params={"selected_tokens": "一致,卧室", "page": 1, "limit": 20},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["scope"]["key"] == "edit"
    assert payload["summary"]["candidate_count"] == 200
    assert payload["summary"]["matched_prompt_count"] == 1
    assert payload["summary"]["saved_template_count"] == 2
    assert payload["selected_tokens"] == ["一致", "卧室"]
    assert [group["label"] for group in payload["filters"]["groups"][:5]] == [
        "保持口径",
        "场景",
        "物品",
        "成人主题",
        "画面风格构图",
    ]
    assert payload["rows"][0]["matched_tokens"] == ["一致", "卧室"]
    grouped_labels = [group["label"] for group in payload["rows"][0]["grouped_tokens"]]
    assert "保持口径" in grouped_labels
    assert "场景" in grouped_labels
    assert "物品" in grouped_labels
    assert "服饰配件" in grouped_labels


@pytest.mark.asyncio
async def test_prompt_decomposition_save_coerces_iso_last_seen_to_datetime(monkeypatch):
    async def fake_token_metadata():
        return {}

    async def fake_ensure_schema(conn):
        return None

    class FakeConn:
        def __init__(self):
            self.execute_args = None
            self.fetchrow_calls = 0

        async def fetchrow(self, query, *args):
            self.fetchrow_calls += 1
            if self.fetchrow_calls == 1:
                return {
                    "prompt_hash": "hash-1",
                    "prompt": "测试 prompt",
                    "tokens": ["一致", "卧室"],
                    "uses": 12,
                    "users": 8,
                    "quality_score": 88.6,
                    "last_seen": "2026-07-09T20:10:00+00:00",
                }
            return {
                "id": 1,
                "scope_key": "edit",
                "task_type": "edit",
                "title": "模板标题",
                "prompt_hash": "hash-1",
                "prompt": "测试 prompt",
                "selected_tokens": ["一致"],
                "tokens": ["一致", "卧室"],
                "grouped_tokens": [],
                "uses": 12,
                "users": 8,
                "quality_score": 88.6,
                "last_seen": "2026-07-09T20:10:00+00:00",
                "created_at": "2026-07-09T20:11:00+00:00",
                "updated_at": "2026-07-09T20:11:00+00:00",
            }

        async def execute(self, query, *args):
            self.execute_args = args
            return "INSERT 0 1"

    class FakeAcquire:
        def __init__(self, conn):
            self.conn = conn

        async def __aenter__(self):
            return self.conn

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakePool:
        def __init__(self, conn):
            self.conn = conn

        def acquire(self):
            return FakeAcquire(self.conn)

    fake_conn = FakeConn()

    async def fake_pool():
        return FakePool(fake_conn)

    monkeypatch.setattr(routes_prompts, "_prompt_decomposition_token_metadata", fake_token_metadata)
    monkeypatch.setattr(routes_prompts, "ensure_prompt_decomposition_schema", fake_ensure_schema)
    monkeypatch.setattr(routes_prompts, "_pool", fake_pool)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.post(
            "/api/prompt-decomposition/saved",
            json={
                "task_type": "edit",
                "prompt_hash": "hash-1",
                "title": "模板标题",
                "selected_tokens": ["一致"],
            },
        )

    assert response.status_code == 200
    assert fake_conn.execute_args is not None
    assert fake_conn.execute_args[11].isoformat() == "2026-07-09T20:10:00+00:00"
