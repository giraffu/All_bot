import pytest
from httpx import ASGITransport, AsyncClient

from local_analytics_platform.app import main as analytics_main
from local_analytics_platform.app import routes_prompts
from local_analytics_platform.app.prompt_mart import PROMPT_NORMALIZATION_VERSION
from local_analytics_platform.app.prompt_template_candidates import (
    PROMPT_TEMPLATE_SCHEMA_SQL,
    PROMPT_TEMPLATE_VERSION,
    build_prompt_template_token_metadata,
    prompt_template_similarity_bucket,
    prompt_template_key,
    prompt_template_slot_signature,
    prompt_template_slots_from_tokens,
)
from local_analytics_platform.app.prompt_vectors import PROMPT_TOKEN_VERSION


def test_prompt_template_schema_contains_materialized_candidate_tables():
    schema_sql = "\n".join(PROMPT_TEMPLATE_SCHEMA_SQL).lower()

    assert "create table if not exists analytics_prompt_template_candidates" in schema_sql
    assert "create table if not exists analytics_prompt_template_candidate_prompts" in schema_sql
    assert "create table if not exists analytics_prompt_template_state" in schema_sql
    assert "token_slots jsonb not null default '{}'::jsonb" in schema_sql
    assert "similarity_bucket text not null default ''" in schema_sql
    assert "similarity_score numeric(20, 4) not null default 0" in schema_sql
    assert "similarity_metrics jsonb not null default '{}'::jsonb" in schema_sql
    assert "analytics_prompt_template_candidate_review_marks" in schema_sql
    assert "review_processed boolean not null default false" in schema_sql
    assert "review_processed_at timestamptz" in schema_sql
    assert "analytics_prompt_template_candidate_template_review_marks" in schema_sql
    assert "low_quality boolean not null default false" in schema_sql
    assert "low_quality_marked_at timestamptz" in schema_sql
    assert "marked_at timestamptz not null default now()" in schema_sql
    assert "primary key (template_version, template_key)" in schema_sql
    assert "idx_prompt_template_candidates_scope_score" in schema_sql
    assert "idx_prompt_template_template_review_low_quality" in schema_sql


def test_prompt_template_similarity_bucket_classifies_four_review_groups():
    assert prompt_template_similarity_bucket(0.53) == "高度相似"
    assert prompt_template_similarity_bucket(0.40) == "较相似"
    assert prompt_template_similarity_bucket(0.30) == "中等相似"
    assert prompt_template_similarity_bucket(0.20) == "差异较大"
    assert (
        prompt_template_similarity_bucket(
            0.35,
            avg_text_jaccard=0.10,
            avg_extra_token_jaccard=0.06,
            unique_prompt_ratio=0.95,
            slot_token_count=2,
        )
        == "差异较大"
    )


def test_prompt_template_slots_group_tokens_by_category_and_add_edit_defaults():
    metadata = build_prompt_template_token_metadata(
        [
            {"term": "一致", "category_label": "保持口径"},
            {"term": "女人", "category_label": "人物主体"},
            {"term": "深蹲", "category_label": "动作姿势"},
            {"term": "阴道", "category_label": "身体部分"},
            {"term": "脱衣", "category_label": "成人主题"},
            {"term": "镜头", "category_label": "镜头构图"},
            {"term": "无关高频", "category_label": "观测高频词"},
        ],
        [{"representative_token": "光影", "category_label": "风格质量"}],
    )

    slots = prompt_template_slots_from_tokens(
        ["女人", "一致", "深蹲", "阴道", "脱衣", "光影", "无关高频"],
        metadata,
        scope_key="edit",
    )

    assert slots["task_intent"] == ["P图", "主体人物", "人物一致"]
    assert slots["preserve"] == ["一致"]
    assert slots["subject"] == ["女人"]
    assert slots["pose_action"] == ["深蹲"]
    assert slots["body_part"] == ["阴道"]
    assert slots["adult_theme"] == ["脱衣"]
    assert slots["style_quality"] == ["光影"]
    assert "无关高频" not in str(slots)
    assert prompt_template_slot_signature(slots).startswith("task_intent:")
    assert prompt_template_key("edit", slots).startswith("tmpl_")
    model_slots = prompt_template_slots_from_tokens(
        ["一致", "女人", "深蹲", "镜头"],
        metadata,
        scope_key="model|edit|qwen/YARN_1.0.safetensors",
    )
    assert model_slots["task_intent"] == ["P图", "主体人物", "人物一致"]
    assert "/" not in prompt_template_key("model|edit|qwen/YARN_1.0.safetensors", model_slots)


@pytest.mark.asyncio
async def test_prompt_template_candidates_returns_stable_empty_state_when_tables_missing(monkeypatch):
    async def fake_fetchrow(query, *args):
        if "analytics_prompt_template_candidates" in query:
            return {"ready": False, "state_ready": False}
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def fake_fetch(query, *args):
        raise AssertionError(f"unexpected fetch query: {query}")

    monkeypatch.setattr(routes_prompts, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(routes_prompts, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get("/api/prompt-template-candidates")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is False
    assert payload["rows"] == []
    assert payload["summary"]["template_count"] == 0
    assert payload["filters"] == {"tasks": [], "models": []}


@pytest.mark.asyncio
async def test_prompt_template_candidates_supports_task_model_filters_and_detail(monkeypatch):
    model_key = "qwen/YARN_1.0.safetensors"
    scope_key = f"model|edit|{model_key}"
    template_key = "tmpl_abc123"

    async def fake_ensure_schema():
        return None

    async def fake_fetchrow(query, *args):
        lower = query.lower()
        if "analytics_prompt_template_candidates" in lower and "to_regclass" in lower:
            return {"ready": True, "state_ready": True}
        if "count(*)::bigint as total" in lower:
            assert args == (PROMPT_TEMPLATE_VERSION, scope_key, "一致", 20, "高度相似", "processed")
            return {"total": 1}
        if "from analytics_prompt_template_candidates" in lower and "template_key = $2" in lower:
            assert args == (PROMPT_TEMPLATE_VERSION, template_key)
            return {
                "template_key": template_key,
                "scope_key": scope_key,
                "scope_kind": "model",
                "scope_label": "YARN",
                "parent_task_type": "edit",
                "model_key": model_key,
                "model_label": "YARN",
                "template_title": "自由P图 · 保持口径: 一致",
                "token_slots": {"preserve": ["一致"], "pose_action": ["深蹲"]},
                "tokens": ["一致", "深蹲"],
                "prompt_count": 2,
                "use_count": 8,
                "user_count": 3,
                "quality_score": 88.5,
                "similarity_bucket": "高度相似",
                "similarity_score": 0.82,
                "similarity_metrics": {"avg_text_jaccard": 0.9},
                "marked_prompt_count": 1,
                "low_quality": False,
                "low_quality_marked_at": None,
                "processed": True,
                "latest_prompt_at": "2026-07-08T12:00:00",
                "refreshed_at": "2026-07-08T12:30:00",
            }
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def fake_fetch(query, *args):
        lower = query.lower()
        if "from analytics_prompt_template_state" in lower:
            return []
        if "scope_kind = 'task'" in lower:
            return [{"value": "edit", "label": "自由P图"}]
        if "scope_kind = 'model'" in lower:
            assert args == (PROMPT_NORMALIZATION_VERSION, PROMPT_TOKEN_VERSION, "edit")
            return [{"task_type": "edit", "value": model_key, "label": "YARN", "scope_key": scope_key}]
        if "from analytics_prompt_template_candidates" in lower:
            assert args == (PROMPT_TEMPLATE_VERSION, scope_key, "一致", 20, "高度相似", "processed", 10, 0)
            return [
                {
                    "template_key": template_key,
                    "scope_key": scope_key,
                    "scope_kind": "model",
                    "scope_label": "YARN",
                    "parent_task_type": "edit",
                    "model_key": model_key,
                    "model_label": "YARN",
                    "template_title": "自由P图 · 保持口径: 一致",
                    "token_slots": {"preserve": ["一致"], "pose_action": ["深蹲"]},
                    "tokens": ["一致", "深蹲"],
                    "prompt_count": 2,
                    "use_count": 8,
                    "user_count": 3,
                    "quality_score": 88.5,
                    "similarity_bucket": "高度相似",
                    "similarity_score": 0.82,
                    "similarity_metrics": {"avg_text_jaccard": 0.9},
                    "marked_prompt_count": 1,
                    "low_quality": False,
                    "low_quality_marked_at": None,
                    "processed": True,
                    "latest_prompt_at": "2026-07-08T12:00:00",
                    "refreshed_at": "2026-07-08T12:30:00",
                }
            ]
        if "from analytics_prompt_template_candidate_prompts" in lower:
            assert args == (PROMPT_TEMPLATE_VERSION, template_key, 20, 0)
            return [
                {
                    "prompt_hash": "hash1",
                    "prompt": "保持人物一致并调整动作",
                    "tokens": ["一致", "深蹲"],
                    "token_slots": {"preserve": ["一致"], "pose_action": ["深蹲"]},
                    "task_types": ["edit"],
                    "scopes": ["all", "edit", scope_key],
                    "uses": 5,
                    "users": 2,
                    "quality_score": 90,
                    "last_seen": "2026-07-08T12:00:00",
                    "rank": 1,
                    "review_checked": True,
                    "review_marked_at": "2026-07-08T12:45:00",
                }
            ]
        raise AssertionError(f"unexpected fetch query: {query}")

    monkeypatch.setattr(routes_prompts, "_ensure_prompt_template_schema", fake_ensure_schema)
    monkeypatch.setattr(routes_prompts, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(routes_prompts, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        list_response = await client.get(
            "/api/prompt-template-candidates",
            params={
                "task_type": "edit",
                "model_key": model_key,
                "q": "一致",
                "similarity_bucket": "高度相似",
                "review_status": "processed",
                "limit": 10,
            },
        )
        detail_response = await client.get(f"/api/prompt-template-candidates/{template_key}/prompts")

    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["ready"] is True
    assert list_payload["scope"]["key"] == scope_key
    assert list_payload["pagination"]["total"] == 1
    assert list_payload["rows"][0]["template_key"] == template_key
    assert list_payload["rows"][0]["token_slots"]["preserve"] == ["一致"]
    assert list_payload["rows"][0]["similarity_bucket"] == "高度相似"
    assert list_payload["rows"][0]["processed"] is True
    assert list_payload["rows"][0]["marked_prompt_count"] == 1
    assert list_payload["rows"][0]["low_quality"] is False
    assert list_payload["similarity_bucket"] == "高度相似"
    assert list_payload["review_status"] == "processed"
    assert list_payload["filters"]["tasks"] == [{"value": "edit", "label": "自由P图"}]

    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["summary"]["template_key"] == template_key
    assert detail_payload["summary"]["marked_prompt_count"] == 1
    assert detail_payload["summary"]["low_quality"] is False
    assert detail_payload["summary"]["processed"] is True
    assert detail_payload["rows"][0]["prompt_preview"] == "保持人物一致并调整动作"
    assert detail_payload["rows"][0]["review_checked"] is True
    assert detail_payload["pagination"]["total"] == 2


@pytest.mark.asyncio
async def test_prompt_template_candidates_reject_invalid_review_filters(monkeypatch):
    async def fake_fetchrow(query, *args):
        if "analytics_prompt_template_candidates" in query and "to_regclass" in query:
            return {"ready": True, "state_ready": True}
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def fake_ensure_schema():
        return None

    monkeypatch.setattr(routes_prompts, "_ensure_prompt_template_schema", fake_ensure_schema)
    monkeypatch.setattr(routes_prompts, "_fetchrow", fake_fetchrow)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        invalid_bucket = await client.get(
            "/api/prompt-template-candidates",
            params={"similarity_bucket": "相似"},
        )
        invalid_status = await client.get(
            "/api/prompt-template-candidates",
            params={"review_status": "done"},
        )

    assert invalid_bucket.status_code == 400
    assert invalid_status.status_code == 400


@pytest.mark.asyncio
async def test_prompt_template_candidates_low_quality_filter_marks_processed(monkeypatch):
    template_key = "tmpl_low_quality"

    async def fake_ensure_schema():
        return None

    async def fake_fetchrow(query, *args):
        lower = query.lower()
        if "analytics_prompt_template_candidates" in lower and "to_regclass" in lower:
            return {"ready": True, "state_ready": True}
        if "count(*)::bigint as total" in lower:
            assert args == (PROMPT_TEMPLATE_VERSION, "edit", "", 20, "", "low_quality")
            return {"total": 1}
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def fake_fetch(query, *args):
        lower = query.lower()
        if "from analytics_prompt_template_state" in lower:
            return []
        if "from analytics_prompt_template_candidates" in lower:
            assert args == (PROMPT_TEMPLATE_VERSION, "edit", "", 20, "", "low_quality", 20, 0)
            return [
                {
                    "template_key": template_key,
                    "scope_key": "edit",
                    "scope_kind": "task",
                    "scope_label": "自由P图",
                    "parent_task_type": "edit",
                    "model_key": None,
                    "model_label": None,
                    "template_title": "自由P图 · 低质量样本",
                    "token_slots": {"preserve": ["一致"]},
                    "tokens": ["一致"],
                    "prompt_count": 21,
                    "use_count": 30,
                    "user_count": 8,
                    "quality_score": 12.5,
                    "similarity_bucket": "较相似",
                    "similarity_score": 0.4,
                    "similarity_metrics": {},
                    "marked_prompt_count": 0,
                    "low_quality": True,
                    "low_quality_marked_at": "2026-07-10T10:30:00",
                    "processed": True,
                    "latest_prompt_at": "2026-07-10T10:00:00",
                    "refreshed_at": "2026-07-10T10:10:00",
                }
            ]
        raise AssertionError(f"unexpected fetch query: {query}")

    monkeypatch.setattr(routes_prompts, "_ensure_prompt_template_schema", fake_ensure_schema)
    monkeypatch.setattr(routes_prompts, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(routes_prompts, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get(
            "/api/prompt-template-candidates",
            params={
                "task_type": "edit",
                "review_status": "low_quality",
                "limit": 20,
                "include_filters": "false",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["review_status"] == "low_quality"
    assert payload["pagination"]["total"] == 1
    assert payload["rows"][0]["template_key"] == template_key
    assert payload["rows"][0]["low_quality"] is True
    assert payload["rows"][0]["marked_prompt_count"] == 0
    assert payload["rows"][0]["processed"] is True


@pytest.mark.asyncio
async def test_prompt_template_candidate_template_review_mark_save_and_remove(monkeypatch):
    template_key = "tmpl_template_review"
    calls: list[tuple[str, tuple[object, ...]]] = []

    class FakeConn:
        def __init__(self) -> None:
            self.low_quality = False
            self.low_quality_marked_at = None

        async def execute(self, query, *args):
            calls.append((query, args))
            lower = query.lower()
            if "delete from analytics_prompt_template_candidate_template_review_marks" in lower:
                assert args == (PROMPT_TEMPLATE_VERSION, template_key)
                self.low_quality = False
                self.low_quality_marked_at = None
            return "OK"

        async def fetchrow(self, query, *args):
            calls.append((query, args))
            lower = query.lower()
            if "from analytics_prompt_template_candidates" in lower and "template_key = $2" in lower:
                assert args == (PROMPT_TEMPLATE_VERSION, template_key)
                return {"template_key": template_key}
            if "insert into analytics_prompt_template_candidate_template_review_marks" in lower:
                assert args == (PROMPT_TEMPLATE_VERSION, template_key)
                self.low_quality = True
                self.low_quality_marked_at = "2026-07-10T12:00:00"
                return {
                    "template_key": template_key,
                    "low_quality": True,
                    "low_quality_marked_at": self.low_quality_marked_at,
                }
            if "count(*)::bigint as marked_prompt_count" in lower:
                return {"marked_prompt_count": 0}
            if "from analytics_prompt_template_candidate_template_review_marks" in lower:
                return None
            raise AssertionError(f"unexpected fetchrow query: {query}")

    class FakeAcquire:
        def __init__(self, conn):
            self.conn = conn

        async def __aenter__(self):
            return self.conn

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakePool:
        def __init__(self):
            self.conn = FakeConn()

        def acquire(self):
            return FakeAcquire(self.conn)

    pool = FakePool()

    async def fake_pool():
        return pool

    monkeypatch.setattr(routes_prompts, "_pool", fake_pool)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        save_response = await client.post(
            "/api/prompt-template-candidates/template-review-marks",
            json={"template_key": template_key, "low_quality": True},
        )
        remove_response = await client.post(
            "/api/prompt-template-candidates/template-review-marks",
            json={"template_key": template_key, "low_quality": False},
        )

    assert save_response.status_code == 200
    save_payload = save_response.json()
    assert save_payload["template_key"] == template_key
    assert save_payload["low_quality"] is True
    assert save_payload["low_quality_marked_at"] == "2026-07-10T12:00:00"
    assert save_payload["marked_prompt_count"] == 0
    assert save_payload["processed"] is True

    assert remove_response.status_code == 200
    remove_payload = remove_response.json()
    assert remove_payload["template_key"] == template_key
    assert remove_payload["low_quality"] is False
    assert remove_payload["low_quality_marked_at"] is None
    assert remove_payload["marked_prompt_count"] == 0
    assert remove_payload["processed"] is False
    assert any(
        "insert into analytics_prompt_template_candidate_template_review_marks" in query.lower()
        for query, _ in calls
    )
    assert any(
        "delete from analytics_prompt_template_candidate_template_review_marks" in query.lower()
        for query, _ in calls
    )


@pytest.mark.asyncio
async def test_prompt_template_candidate_template_review_mark_unknown_template_returns_404(monkeypatch):
    class FakeConn:
        async def execute(self, query, *args):
            return "OK"

        async def fetchrow(self, query, *args):
            lower = query.lower()
            if "from analytics_prompt_template_candidates" in lower and "template_key = $2" in lower:
                return None
            raise AssertionError(f"unexpected fetchrow query: {query}")

    class FakeAcquire:
        async def __aenter__(self):
            return FakeConn()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakePool:
        def acquire(self):
            return FakeAcquire()

    async def fake_pool():
        return FakePool()

    monkeypatch.setattr(routes_prompts, "_pool", fake_pool)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.post(
            "/api/prompt-template-candidates/template-review-marks",
            json={"template_key": "tmpl_missing", "low_quality": True},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_prompt_template_candidate_review_mark_save_and_remove(monkeypatch):
    template_key = "tmpl_review"
    prompt_hash = "hash_review"
    calls: list[tuple[str, tuple[object, ...]]] = []

    class FakeConn:
        def __init__(self) -> None:
            self.marked = False

        async def execute(self, query, *args):
            calls.append((query, args))
            lower = query.lower()
            if "insert into analytics_prompt_template_candidate_review_marks" in lower:
                self.marked = True
            if "delete from analytics_prompt_template_candidate_review_marks" in lower:
                self.marked = False
            return "OK"

        async def fetchrow(self, query, *args):
            lower = query.lower()
            if "from analytics_prompt_template_candidate_prompts" in lower:
                assert args == (PROMPT_TEMPLATE_VERSION, template_key, prompt_hash)
                return {
                    "template_key": template_key,
                    "prompt_hash": prompt_hash,
                    "scope_key": "edit",
                    "prompt": "保持一致并调整姿势",
                    "tokens": ["一致", "深蹲"],
                    "token_slots": {"preserve": ["一致"]},
                    "task_types": ["edit"],
                    "scopes": ["all", "edit"],
                    "uses": 5,
                    "users": 2,
                    "quality_score": 90,
                    "last_seen": "2026-07-08T12:00:00",
                }
            if "count(*)::bigint as marked_prompt_count" in lower:
                return {"marked_prompt_count": 1 if self.marked else 0}
            raise AssertionError(f"unexpected fetchrow query: {query}")

    class FakeAcquire:
        def __init__(self, conn):
            self.conn = conn

        async def __aenter__(self):
            return self.conn

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakePool:
        def __init__(self):
            self.conn = FakeConn()

        def acquire(self):
            return FakeAcquire(self.conn)

    pool = FakePool()

    async def fake_pool():
        return pool

    monkeypatch.setattr(routes_prompts, "_pool", fake_pool)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        save_response = await client.post(
            "/api/prompt-template-candidates/review-marks",
            json={"template_key": template_key, "prompt_hash": prompt_hash, "checked": True},
        )
        remove_response = await client.post(
            "/api/prompt-template-candidates/review-marks",
            json={"template_key": template_key, "prompt_hash": prompt_hash, "checked": False},
        )

    assert save_response.status_code == 200
    assert save_response.json()["review_checked"] is True
    assert save_response.json()["marked_prompt_count"] == 1
    assert remove_response.status_code == 200
    assert remove_response.json()["review_checked"] is False
    assert remove_response.json()["marked_prompt_count"] == 0
    assert any("insert into analytics_prompt_template_candidate_review_marks" in query.lower() for query, _ in calls)
    assert any("delete from analytics_prompt_template_candidate_review_marks" in query.lower() for query, _ in calls)


@pytest.mark.asyncio
async def test_prompt_template_candidate_review_marks_list_for_copy(monkeypatch):
    model_key = "qwen/YARN_1.0.safetensors"
    scope_key = f"model|edit|{model_key}"

    async def fake_ensure_schema():
        return None

    async def fake_fetchrow(query, *args):
        lower = query.lower()
        if "analytics_prompt_template_candidates" in lower and "to_regclass" in lower:
            return {"ready": True, "state_ready": True}
        if "processed_prompt_count" in lower:
            assert args == (PROMPT_TEMPLATE_VERSION, scope_key, "姿势", "高度相似", "unprocessed")
            return {"total": 1, "processed_prompt_count": 0, "unprocessed_prompt_count": 1}
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def fake_fetch(query, *args):
        lower = query.lower()
        if "from analytics_prompt_template_candidate_review_marks marks" in lower:
            assert args == (PROMPT_TEMPLATE_VERSION, scope_key, "姿势", "高度相似", "unprocessed", 50, 0)
            return [
                {
                    "template_key": "tmpl_saved",
                    "template_title": "自由P图 · 保持口径: 一致",
                    "scope_key": scope_key,
                    "scope_label": "YARN",
                    "parent_task_type": "edit",
                    "model_key": model_key,
                    "model_label": "YARN",
                    "prompt_count": 25,
                    "similarity_bucket": "高度相似",
                    "similarity_score": 0.82,
                    "prompt_hash": "hash_saved",
                    "prompt": "保持人物一致并调整姿势",
                    "tokens": ["一致", "姿势"],
                    "token_slots": {"preserve": ["一致"], "pose_action": ["姿势"]},
                    "task_types": ["edit"],
                    "scopes": ["all", "edit", scope_key],
                    "uses": 12,
                    "users": 4,
                    "quality_score": 99.5,
                    "last_seen": "2026-07-09T12:00:00",
                    "review_processed": False,
                    "review_processed_at": None,
                    "marked_at": "2026-07-10T08:00:00",
                    "updated_at": "2026-07-10T08:10:00",
                }
            ]
        raise AssertionError(f"unexpected fetch query: {query}")

    monkeypatch.setattr(routes_prompts, "_ensure_prompt_template_schema", fake_ensure_schema)
    monkeypatch.setattr(routes_prompts, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(routes_prompts, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get(
            "/api/prompt-template-candidates/review-marks",
            params={
                "task_type": "edit",
                "model_key": model_key,
                "q": "姿势",
                "similarity_bucket": "高度相似",
                "processed_status": "unprocessed",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["pagination"]["total"] == 1
    assert payload["scope"]["key"] == scope_key
    assert payload["rows"][0]["prompt"] == "保持人物一致并调整姿势"
    assert payload["rows"][0]["prompt_preview"] == "保持人物一致并调整姿势"
    assert payload["rows"][0]["template_title"] == "自由P图 · 保持口径: 一致"
    assert payload["rows"][0]["similarity_bucket"] == "高度相似"
    assert payload["rows"][0]["quality_score"] == 99.5
    assert payload["rows"][0]["review_processed"] is False
    assert payload["summary"]["processed_prompt_count"] == 0
    assert payload["summary"]["unprocessed_prompt_count"] == 1
    assert payload["processed_status"] == "unprocessed"


@pytest.mark.asyncio
async def test_prompt_template_candidate_review_marks_reject_invalid_processed_status(monkeypatch):
    async def fake_fetchrow(query, *args):
        if "analytics_prompt_template_candidates" in query and "to_regclass" in query:
            return {"ready": True, "state_ready": True}
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def fake_ensure_schema():
        return None

    monkeypatch.setattr(routes_prompts, "_ensure_prompt_template_schema", fake_ensure_schema)
    monkeypatch.setattr(routes_prompts, "_fetchrow", fake_fetchrow)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get(
            "/api/prompt-template-candidates/review-marks",
            params={"processed_status": "done"},
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_prompt_template_candidate_review_mark_processed_toggle(monkeypatch):
    template_key = "tmpl_review"
    prompt_hash = "hash_review"
    calls: list[tuple[str, tuple[object, ...]]] = []

    class FakeConn:
        async def execute(self, query, *args):
            calls.append((query, args))
            return "OK"

        async def fetchrow(self, query, *args):
            calls.append((query, args))
            lower = query.lower()
            if "update analytics_prompt_template_candidate_review_marks" in lower:
                assert args == (PROMPT_TEMPLATE_VERSION, template_key, prompt_hash, True)
                return {
                    "template_key": template_key,
                    "prompt_hash": prompt_hash,
                    "review_processed": True,
                    "review_processed_at": "2026-07-10T09:00:00",
                }
            raise AssertionError(f"unexpected fetchrow query: {query}")

    class FakeAcquire:
        async def __aenter__(self):
            return FakeConn()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakePool:
        def acquire(self):
            return FakeAcquire()

    async def fake_pool():
        return FakePool()

    monkeypatch.setattr(routes_prompts, "_pool", fake_pool)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.post(
            "/api/prompt-template-candidates/review-marks/processed",
            json={"template_key": template_key, "prompt_hash": prompt_hash, "processed": True},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["review_processed"] is True
    assert payload["review_processed_at"] == "2026-07-10T09:00:00"
    assert any("review_processed_at" in query.lower() for query, _ in calls)
