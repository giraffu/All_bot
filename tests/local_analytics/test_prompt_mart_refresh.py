import pytest

from local_analytics_platform.app.prompt_mart import PROMPT_NORMALIZATION_VERSION, refresh_prompt_mart


class FakePromptMartConn:
    def __init__(self):
        self.executed = []

    async def execute(self, query, *args):
        self.executed.append((query, args))
        if "insert into analytics_prompt_occurrence" in query.lower():
            assert args == (["face_swap"], ["builtin prompt"], True, 3)
            return "INSERT 0 12"
        if "last_refresh_mode" in query:
            assert args == (True, PROMPT_NORMALIZATION_VERSION)
        return "OK"

    async def fetchrow(self, query, *args):
        self.executed.append((query, args))
        assert "analytics_prompt_dim" in query
        return {
            "prompt_count": 4,
            "occurrence_count": 12,
            "group_stats_count": 9,
            "stats_updated_at": "2026-06-26T03:00:00",
            "last_history_id": "99",
            "last_refresh_mode": "full",
        }


class FakeIncrementalPromptMartConn:
    def __init__(self):
        self.executed = []

    async def execute(self, query, *args):
        self.executed.append((query, args))
        normalized_query = query.lower()
        if "insert into analytics_prompt_occurrence" in normalized_query:
            assert args == (["face_swap"], ["builtin prompt"], False, 5)
            return "INSERT 0 3"
        if "create temporary table analytics_prompt_refresh_hashes" in normalized_query:
            assert args == ()
        if "insert into analytics_prompt_refresh_hashes" in normalized_query:
            assert args == (5,)
        if "last_refresh_mode" in normalized_query:
            assert args == (False, PROMPT_NORMALIZATION_VERSION)
        return "OK"

    async def fetchval(self, query, *args):
        self.executed.append((query, args))
        normalized_query = query.lower()
        if "normalization_version" in normalized_query:
            return PROMPT_NORMALIZATION_VERSION
        if "count(*)::bigint from analytics_prompt_refresh_hashes" in normalized_query:
            return 2
        raise AssertionError(f"unexpected fetchval: {query}")

    async def fetchrow(self, query, *args):
        self.executed.append((query, args))
        return {
            "prompt_count": 5,
            "occurrence_count": 15,
            "group_stats_count": 11,
            "rollup_stats_count": 42,
            "stats_updated_at": "2026-06-27T03:00:00",
            "last_history_id": "101",
            "last_refresh_mode": "incremental",
            "normalization_version": PROMPT_NORMALIZATION_VERSION,
        }


@pytest.mark.asyncio
async def test_refresh_prompt_mart_full_rebuilds_schema_occurrences_and_stats():
    conn = FakePromptMartConn()

    status = await refresh_prompt_mart(
        conn,
        builtin_template_keys=["face_swap"],
        builtin_template_prompts=["builtin prompt"],
        full=True,
        recent_days=3,
    )

    executed_sql = "\n".join(query for query, _ in conn.executed).lower()
    assert "create table if not exists analytics_prompt_occurrence" in executed_sql
    assert "raw_prompt text" in executed_sql
    assert "result_rating integer" in executed_sql
    assert "variant_count bigint" in executed_sql
    assert "truncate table" in executed_sql
    assert "insert into analytics_prompt_occurrence" in executed_sql
    assert "normalize(coalesce" in executed_sql
    assert "casefold(normalize" in executed_sql
    assert "^(\\s*\\[[^\\]]*\\]\\s*)+" in executed_sql
    assert "md5(nh.task_type || chr(31) || nh.prompt) as prompt_hash" in executed_sql
    assert "where length(nh.prompt) > 0" in executed_sql
    assert "coalesce(h.rating, 0)::int as result_rating" in executed_sql
    assert "insert into analytics_prompt_dim" in executed_sql
    assert "insert into analytics_prompt_group_stats" in executed_sql
    assert "(240, now() - interval '240 day')" in executed_sql
    assert "(360, now() - interval '360 day')" in executed_sql
    assert "analyze analytics_prompt_rollup_stats" in executed_sql
    assert "last_history_id" in executed_sql
    assert "normalization_version" in executed_sql
    assert status["occurrence_upsert_result"] == "INSERT 0 12"
    assert status["prompt_count"] == 4


@pytest.mark.asyncio
async def test_refresh_prompt_mart_incremental_rebuilds_only_affected_prompts():
    conn = FakeIncrementalPromptMartConn()

    status = await refresh_prompt_mart(
        conn,
        builtin_template_keys=["face_swap"],
        builtin_template_prompts=["builtin prompt"],
        full=False,
        recent_days=5,
    )

    executed_sql = "\n".join(query for query, _ in conn.executed).lower()
    assert "create temporary table analytics_prompt_refresh_hashes" in executed_sql
    assert "delete from analytics_prompt_group_stats where prompt_hash in" in executed_sql
    assert "delete from analytics_prompt_rollup_stats where prompt_hash in" in executed_sql
    assert "join analytics_prompt_refresh_hashes affected" in executed_sql
    assert "truncate table analytics_prompt_group_stats" not in executed_sql
    assert "truncate table analytics_prompt_rollup_stats" not in executed_sql
    assert status["occurrence_upsert_result"] == "INSERT 0 3"
    assert status["affected_prompt_hash_count"] == 2
