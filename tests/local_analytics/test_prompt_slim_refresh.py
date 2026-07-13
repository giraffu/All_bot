import pytest

from local_analytics_platform.app.prompt_mart import PROMPT_NORMALIZATION_VERSION
from local_analytics_platform.app.prompt_slim import (
    PROMPT_SLIM_RULE_VERSION,
    refresh_prompt_slim_candidates,
)


class FakePromptSlimConn:
    def __init__(self):
        self.executed = []

    async def execute(self, query, *args):
        self.executed.append((query, args))
        if "delete from analytics_prompt_slim_candidates" in query.lower():
            assert args == (PROMPT_NORMALIZATION_VERSION,)
            return "DELETE 7"
        if "insert into analytics_prompt_slim_candidates" in query.lower():
            return "INSERT 0 3"
        return "OK"

    async def fetchrow(self, query, *args):
        self.executed.append((query, args))
        if "analytics_prompt_mart_state" in query and "normalization_version" in query:
            return {"normalization_version": PROMPT_NORMALIZATION_VERSION}
        if "slim_count" in query:
            return {
                "slim_count": 3,
                "candidate_count": 2,
                "auto_rejected_count": 1,
                "manual_keep_count": 0,
                "manual_reject_count": 0,
                "excellent_count": 0,
                "archived_count": 0,
                "refreshed_at": "2026-06-26T09:00:00",
            }
        raise AssertionError(f"unexpected fetchrow query: {query}")


@pytest.mark.asyncio
async def test_refresh_prompt_slim_candidates_builds_schema_and_wide_table():
    conn = FakePromptSlimConn()

    status = await refresh_prompt_slim_candidates(conn)

    executed_sql = "\n".join(query for query, _ in conn.executed).lower()
    assert "create table if not exists analytics_prompt_slim_candidates" in executed_sql
    assert "alter table analytics_prompt_occurrence add column if not exists result_rating" in executed_sql
    assert "prompt_hash text primary key" in executed_sql
    assert "raw_prompt_representative text" in executed_sql
    assert "using_user_ids bigint[]" in executed_sql
    assert "task_type_counts jsonb" in executed_sql
    assert "result_likes bigint" in executed_sql
    assert "result_dislikes bigint" in executed_sql
    assert "gallery_likes bigint" in executed_sql
    assert "gallery_dislikes bigint" in executed_sql
    assert "gallery_apply_user_ids bigint[]" in executed_sql
    assert "prompt_unlock_user_ids bigint[]" in executed_sql
    assert "quality_stage text" in executed_sql
    assert "idx_prompt_slim_stage_score" in executed_sql
    assert "using gin(task_types)" in executed_sql
    assert "delete from analytics_prompt_slim_candidates" in executed_sql
    assert status["old_version_delete_result"] == "DELETE 7"
    assert status["slim_upsert_result"] == "INSERT 0 3"
    assert status["rule_version"] == PROMPT_SLIM_RULE_VERSION
    assert status["normalization_version"] == PROMPT_NORMALIZATION_VERSION


@pytest.mark.asyncio
async def test_refresh_prompt_slim_candidates_separates_result_and_gallery_signals():
    conn = FakePromptSlimConn()

    await refresh_prompt_slim_candidates(conn)

    upsert_sql = next(
        query.lower()
        for query, _ in conn.executed
        if "insert into analytics_prompt_slim_candidates" in query.lower()
    )
    assert "result_rating" in upsert_sql
    assert "result_like_user_ids" in upsert_sql
    assert "result_dislike_user_ids" in upsert_sql
    assert "gallery_posts gp" in upsert_sql
    assert "user_interactions" in upsert_sql
    assert "gallery_prompt_unlocks" in upsert_sql
    assert "action_type = 'apply'" in upsert_sql
    assert "gallery_apply_user_ids" in upsert_sql
    assert "prompt_unlock_user_ids" in upsert_sql

    executed_sql = "\n".join(query for query, _ in conn.executed).lower()
    assert "update analytics_prompt_occurrence o" in executed_sql
    assert "from history h" in executed_sql


@pytest.mark.asyncio
async def test_refresh_prompt_slim_candidates_preserves_manual_quality_stage():
    conn = FakePromptSlimConn()

    await refresh_prompt_slim_candidates(conn)

    upsert_sql = next(
        query.lower()
        for query, _ in conn.executed
        if "on conflict (prompt_hash) do update" in query.lower()
    )
    assert "manual_keep" in upsert_sql
    assert "manual_reject" in upsert_sql
    assert "excellent" in upsert_sql
    assert "archived" in upsert_sql
    assert "then analytics_prompt_slim_candidates.quality_stage" in upsert_sql
    assert "review_note = analytics_prompt_slim_candidates.review_note" in upsert_sql


@pytest.mark.asyncio
async def test_refresh_prompt_slim_candidates_applies_medium_low_quality_rules():
    conn = FakePromptSlimConn()

    await refresh_prompt_slim_candidates(conn)

    upsert_sql = next(
        query.lower()
        for query, _ in conn.executed
        if "insert into analytics_prompt_slim_candidates" in query.lower()
    )
    assert "too_short" in upsert_sql
    assert "char_count < 20 then 'too_short'" in upsert_sql
    assert "short_oneoff" in upsert_sql
    assert "symbol_or_digit_only" in upsert_sql
    assert "known_junk" in upsert_sql
    assert "auto_rejected" in upsert_sql
    assert "candidate" in upsert_sql
