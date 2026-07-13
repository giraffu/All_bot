from __future__ import annotations

from typing import Any

from .prompt_mart import PROMPT_NORMALIZATION_VERSION


PROMPT_SLIM_RULE_VERSION = "slim-v3-task-type-prefix-strip"
PROMPT_SLIM_MANUAL_STAGES = ("manual_keep", "manual_reject", "excellent", "archived")


CREATE_PROMPT_SLIM_SCHEMA_SQL = [
    "alter table analytics_prompt_occurrence add column if not exists result_rating integer not null default 0",
    """
    create table if not exists analytics_prompt_slim_candidates (
        prompt_hash text primary key,
        normalization_version text not null,
        prompt text not null,
        raw_prompt_representative text,
        variant_count bigint not null default 1,
        char_count integer not null,
        uses bigint not null default 0,
        users bigint not null default 0,
        using_user_ids bigint[] not null default '{}',
        first_seen timestamp,
        last_seen timestamp,
        task_types text[] not null default '{}',
        task_type_counts jsonb not null default '{}'::jsonb,
        source_scopes text[] not null default '{}',
        source_counts jsonb not null default '{}'::jsonb,
        result_likes bigint not null default 0,
        result_dislikes bigint not null default 0,
        result_like_user_ids bigint[] not null default '{}',
        result_dislike_user_ids bigint[] not null default '{}',
        gallery_posts bigint not null default 0,
        gallery_likes bigint not null default 0,
        gallery_dislikes bigint not null default 0,
        gallery_comments bigint not null default 0,
        gallery_applies bigint not null default 0,
        gallery_apply_user_ids bigint[] not null default '{}',
        prompt_unlocks bigint not null default 0,
        prompt_unlock_user_ids bigint[] not null default '{}',
        quality_score numeric(20, 2) not null default 0,
        positive_signal_score numeric(20, 2) not null default 0,
        negative_signal_score numeric(20, 2) not null default 0,
        quality_stage text not null default 'candidate',
        low_quality_reasons text[] not null default '{}',
        rule_version text not null,
        review_note text,
        reviewed_by text,
        reviewed_at timestamptz,
        created_at timestamptz not null default now(),
        updated_at timestamptz not null default now(),
        refreshed_at timestamptz not null default now(),
        constraint chk_prompt_slim_quality_stage check (
            quality_stage in (
                'auto_rejected',
                'candidate',
                'manual_keep',
                'manual_reject',
                'excellent',
                'archived'
            )
        )
    )
    """,
    "create index if not exists idx_prompt_slim_stage_score on analytics_prompt_slim_candidates(quality_stage, quality_score desc)",
    "create index if not exists idx_prompt_slim_last_seen on analytics_prompt_slim_candidates(last_seen desc)",
    "create index if not exists idx_prompt_slim_uses on analytics_prompt_slim_candidates(uses desc)",
    "create index if not exists idx_prompt_slim_task_types on analytics_prompt_slim_candidates using gin(task_types)",
    "create index if not exists idx_prompt_slim_source_scopes on analytics_prompt_slim_candidates using gin(source_scopes)",
    "create index if not exists idx_prompt_slim_low_quality_reasons on analytics_prompt_slim_candidates using gin(low_quality_reasons)",
    "alter table analytics_prompt_slim_candidates add column if not exists normalization_version text not null default 'unknown'",
    "alter table analytics_prompt_slim_candidates add column if not exists raw_prompt_representative text",
    "alter table analytics_prompt_slim_candidates add column if not exists variant_count bigint not null default 1",
    "alter table analytics_prompt_slim_candidates add column if not exists using_user_ids bigint[] not null default '{}'",
    "alter table analytics_prompt_slim_candidates add column if not exists task_type_counts jsonb not null default '{}'::jsonb",
    "alter table analytics_prompt_slim_candidates add column if not exists source_scopes text[] not null default '{}'",
    "alter table analytics_prompt_slim_candidates add column if not exists source_counts jsonb not null default '{}'::jsonb",
    "alter table analytics_prompt_slim_candidates add column if not exists result_likes bigint not null default 0",
    "alter table analytics_prompt_slim_candidates add column if not exists result_dislikes bigint not null default 0",
    "alter table analytics_prompt_slim_candidates add column if not exists result_like_user_ids bigint[] not null default '{}'",
    "alter table analytics_prompt_slim_candidates add column if not exists result_dislike_user_ids bigint[] not null default '{}'",
    "alter table analytics_prompt_slim_candidates add column if not exists gallery_posts bigint not null default 0",
    "alter table analytics_prompt_slim_candidates add column if not exists gallery_likes bigint not null default 0",
    "alter table analytics_prompt_slim_candidates add column if not exists gallery_dislikes bigint not null default 0",
    "alter table analytics_prompt_slim_candidates add column if not exists gallery_comments bigint not null default 0",
    "alter table analytics_prompt_slim_candidates add column if not exists gallery_applies bigint not null default 0",
    "alter table analytics_prompt_slim_candidates add column if not exists gallery_apply_user_ids bigint[] not null default '{}'",
    "alter table analytics_prompt_slim_candidates add column if not exists prompt_unlocks bigint not null default 0",
    "alter table analytics_prompt_slim_candidates add column if not exists prompt_unlock_user_ids bigint[] not null default '{}'",
    "alter table analytics_prompt_slim_candidates add column if not exists quality_score numeric(20, 2) not null default 0",
    "alter table analytics_prompt_slim_candidates add column if not exists positive_signal_score numeric(20, 2) not null default 0",
    "alter table analytics_prompt_slim_candidates add column if not exists negative_signal_score numeric(20, 2) not null default 0",
    "alter table analytics_prompt_slim_candidates add column if not exists quality_stage text not null default 'candidate'",
    "alter table analytics_prompt_slim_candidates add column if not exists low_quality_reasons text[] not null default '{}'",
    "alter table analytics_prompt_slim_candidates add column if not exists rule_version text not null default 'unknown'",
    "alter table analytics_prompt_slim_candidates add column if not exists review_note text",
    "alter table analytics_prompt_slim_candidates add column if not exists reviewed_by text",
    "alter table analytics_prompt_slim_candidates add column if not exists reviewed_at timestamptz",
    "alter table analytics_prompt_slim_candidates add column if not exists refreshed_at timestamptz not null default now()",
]


PROMPT_SLIM_MART_VERSION_SQL = """
select value as normalization_version
from analytics_prompt_mart_state
where key = 'normalization_version'
"""


DELETE_OLD_PROMPT_SLIM_VERSION_SQL = """
delete from analytics_prompt_slim_candidates
where normalization_version <> $1::text
"""


BACKFILL_PROMPT_OCCURRENCE_RATING_SQL = """
update analytics_prompt_occurrence o
set
    result_rating = coalesce(h.rating, 0)::int,
    updated_at = now()
from history h
where h.id = o.history_id
  and o.result_rating is distinct from coalesce(h.rating, 0)::int
"""


UPSERT_PROMPT_SLIM_CANDIDATES_SQL = """
insert into analytics_prompt_slim_candidates (
    prompt_hash,
    normalization_version,
    prompt,
    raw_prompt_representative,
    variant_count,
    char_count,
    uses,
    users,
    using_user_ids,
    first_seen,
    last_seen,
    task_types,
    task_type_counts,
    source_scopes,
    source_counts,
    result_likes,
    result_dislikes,
    result_like_user_ids,
    result_dislike_user_ids,
    gallery_posts,
    gallery_likes,
    gallery_dislikes,
    gallery_comments,
    gallery_applies,
    gallery_apply_user_ids,
    prompt_unlocks,
    prompt_unlock_user_ids,
    quality_score,
    positive_signal_score,
    negative_signal_score,
    quality_stage,
    low_quality_reasons,
    rule_version,
    created_at,
    updated_at,
    refreshed_at
)
with unlock_counts as (
    select post_id, count(*)::bigint as unlocks
    from gallery_prompt_unlocks
    group by post_id
),
gallery_by_task as (
    select
        gp.task_id,
        min(gp.id) as representative_post_id,
        count(*)::bigint as post_count,
        coalesce(sum(gp.likes_count), 0)::bigint as gallery_likes,
        coalesce(sum(gp.dislikes_count), 0)::bigint as gallery_dislikes,
        coalesce(sum(gp.comments_count), 0)::bigint as gallery_comments,
        coalesce(sum(gp.applied_count), 0)::bigint as gallery_applies,
        coalesce(sum(coalesce(uc.unlocks, 0)), 0)::bigint as prompt_unlocks
    from gallery_posts gp
    left join unlock_counts uc on uc.post_id = gp.id
    where gp.is_active is true
      and gp.task_id is not null
    group by gp.task_id
),
scoped_occurrences as (
    select
        o.history_id,
        o.prompt_hash,
        o.task_id,
        coalesce(nullif(o.raw_prompt, ''), o.prompt) as raw_prompt,
        o.prompt,
        o.char_count,
        o.user_id,
        coalesce(o.task_type, 'unknown') as task_type,
        o.created_at,
        coalesce(o.source, 'unknown') as input_source,
        coalesce(o.result_rating, 0) as result_rating,
        case
            when coalesce(gp.post_count, 0) > 0 then 'source_template'
            else 'natural'
        end as source_scope,
        coalesce(gp.post_count, 0)::bigint as gallery_posts,
        coalesce(gp.gallery_likes, 0)::bigint as gallery_likes,
        coalesce(gp.gallery_dislikes, 0)::bigint as gallery_dislikes,
        coalesce(gp.gallery_comments, 0)::bigint as gallery_comments,
        coalesce(gp.gallery_applies, 0)::bigint as gallery_applies,
        coalesce(gp.prompt_unlocks, 0)::bigint as prompt_unlocks
    from analytics_prompt_occurrence o
    left join gallery_by_task gp on gp.task_id = o.task_id
    where o.allow_contribute is distinct from false
      and o.builtin_template_key is null
),
raw_variant_counts as (
    select
        prompt_hash,
        raw_prompt,
        count(*)::bigint as raw_uses,
        max(created_at) as raw_last_seen
    from scoped_occurrences
    group by prompt_hash, raw_prompt
),
raw_representatives as (
    select distinct on (prompt_hash)
        prompt_hash,
        raw_prompt as raw_prompt_representative
    from raw_variant_counts
    order by prompt_hash, raw_uses desc, raw_last_seen desc, raw_prompt
),
task_type_rows as (
    select prompt_hash, task_type, count(*)::bigint as uses
    from scoped_occurrences
    group by prompt_hash, task_type
),
task_type_counts as (
    select
        prompt_hash,
        jsonb_object_agg(task_type, uses order by task_type) as task_type_counts
    from task_type_rows
    group by prompt_hash
),
source_rows as (
    select prompt_hash, source_scope, count(*)::bigint as uses
    from scoped_occurrences
    group by prompt_hash, source_scope
),
source_counts as (
    select
        prompt_hash,
        jsonb_object_agg(source_scope, uses order by source_scope) as source_counts
    from source_rows
    group by prompt_hash
),
gallery_apply_users as (
    select
        s.prompt_hash,
        array_agg(distinct ui.user_id order by ui.user_id) filter (where ui.user_id is not null) as gallery_apply_user_ids
    from scoped_occurrences s
    join gallery_posts gp on gp.task_id = s.task_id and gp.is_active is true
    join user_interactions ui on ui.post_id = gp.id and ui.action_type = 'apply'
    group by s.prompt_hash
),
prompt_unlock_users as (
    select
        s.prompt_hash,
        array_agg(distinct gu.user_id order by gu.user_id) filter (where gu.user_id is not null) as prompt_unlock_user_ids
    from scoped_occurrences s
    join gallery_posts gp on gp.task_id = s.task_id and gp.is_active is true
    join gallery_prompt_unlocks gu on gu.post_id = gp.id
    group by s.prompt_hash
),
grouped as (
    select
        s.prompt_hash,
        min(s.prompt) as prompt,
        max(s.char_count)::int as char_count,
        count(*)::bigint as uses,
        count(distinct s.user_id)::bigint as users,
        coalesce(array_agg(distinct s.user_id order by s.user_id) filter (where s.user_id is not null), '{}') as using_user_ids,
        min(s.created_at) as first_seen,
        max(s.created_at) as last_seen,
        array_remove(array_agg(distinct s.task_type order by s.task_type), null) as task_types,
        array_remove(array_agg(distinct s.source_scope order by s.source_scope), null) as source_scopes,
        count(distinct s.raw_prompt)::bigint as variant_count,
        count(*) filter (where s.result_rating > 0)::bigint as result_likes,
        count(*) filter (where s.result_rating < 0)::bigint as result_dislikes,
        coalesce(array_agg(distinct s.user_id order by s.user_id) filter (where s.result_rating > 0 and s.user_id is not null), '{}') as result_like_user_ids,
        coalesce(array_agg(distinct s.user_id order by s.user_id) filter (where s.result_rating < 0 and s.user_id is not null), '{}') as result_dislike_user_ids,
        coalesce(sum(s.gallery_posts), 0)::bigint as gallery_posts,
        coalesce(sum(s.gallery_likes), 0)::bigint as gallery_likes,
        coalesce(sum(s.gallery_dislikes), 0)::bigint as gallery_dislikes,
        coalesce(sum(s.gallery_comments), 0)::bigint as gallery_comments,
        coalesce(sum(s.gallery_applies), 0)::bigint as gallery_applies,
        coalesce(sum(s.prompt_unlocks), 0)::bigint as prompt_unlocks
    from scoped_occurrences s
    group by s.prompt_hash
),
scored as (
    select
        g.*,
        coalesce(rr.raw_prompt_representative, g.prompt) as raw_prompt_representative,
        coalesce(tt.task_type_counts, '{}'::jsonb) as task_type_counts,
        coalesce(sc.source_counts, '{}'::jsonb) as source_counts,
        coalesce(gau.gallery_apply_user_ids, '{}') as gallery_apply_user_ids,
        coalesce(puu.prompt_unlock_user_ids, '{}') as prompt_unlock_user_ids,
        (
            g.result_likes
            + g.gallery_likes
            + g.gallery_applies
            + g.prompt_unlocks
            + g.gallery_posts
        )::bigint as engagement_positive_count,
        round(
            (
                ln(g.uses + 1) * 4
                + ln(g.users + 1) * 8
                + g.gallery_posts * 6
                + g.result_likes * 3
                + g.gallery_likes * 2
                + g.gallery_applies * 5
                + g.prompt_unlocks * 8
            )::numeric,
            2
        ) as positive_signal_score,
        round((g.result_dislikes * 3 + g.gallery_dislikes * 2)::numeric, 2) as negative_signal_score
    from grouped g
    left join raw_representatives rr on rr.prompt_hash = g.prompt_hash
    left join task_type_counts tt on tt.prompt_hash = g.prompt_hash
    left join source_counts sc on sc.prompt_hash = g.prompt_hash
    left join gallery_apply_users gau on gau.prompt_hash = g.prompt_hash
    left join prompt_unlock_users puu on puu.prompt_hash = g.prompt_hash
),
classified as (
    select
        scored.*,
        array_remove(array[
            case when char_count < 20 then 'too_short' end,
            case
                when char_count <= 20
                  and uses = 1
                  and users = 1
                  and engagement_positive_count = 0
                then 'short_oneoff'
            end,
            case when prompt ~ '^[[:punct:][:space:][:digit:]]+$' then 'symbol_or_digit_only' end,
            case
                when lower(prompt) in ('test', '测试', '无', 'none', 'null', 'na', 'n/a', 'prompt')
                then 'known_junk'
            end
        ], null)::text[] as low_quality_reasons,
        round((positive_signal_score - negative_signal_score)::numeric, 2) as quality_score
    from scored
),
final_rows as (
    select
        *,
        case
            when array_length(low_quality_reasons, 1) is null then 'candidate'
            else 'auto_rejected'
        end as quality_stage
    from classified
)
select
    prompt_hash,
    $1::text as normalization_version,
    prompt,
    raw_prompt_representative,
    variant_count,
    char_count,
    uses,
    users,
    using_user_ids,
    first_seen,
    last_seen,
    task_types,
    task_type_counts,
    source_scopes,
    source_counts,
    result_likes,
    result_dislikes,
    result_like_user_ids,
    result_dislike_user_ids,
    gallery_posts,
    gallery_likes,
    gallery_dislikes,
    gallery_comments,
    gallery_applies,
    gallery_apply_user_ids,
    prompt_unlocks,
    prompt_unlock_user_ids,
    quality_score,
    positive_signal_score,
    negative_signal_score,
    quality_stage,
    low_quality_reasons,
    $2::text as rule_version,
    now() as created_at,
    now() as updated_at,
    now() as refreshed_at
from final_rows
on conflict (prompt_hash) do update set
    normalization_version = excluded.normalization_version,
    prompt = excluded.prompt,
    raw_prompt_representative = excluded.raw_prompt_representative,
    variant_count = excluded.variant_count,
    char_count = excluded.char_count,
    uses = excluded.uses,
    users = excluded.users,
    using_user_ids = excluded.using_user_ids,
    first_seen = excluded.first_seen,
    last_seen = excluded.last_seen,
    task_types = excluded.task_types,
    task_type_counts = excluded.task_type_counts,
    source_scopes = excluded.source_scopes,
    source_counts = excluded.source_counts,
    result_likes = excluded.result_likes,
    result_dislikes = excluded.result_dislikes,
    result_like_user_ids = excluded.result_like_user_ids,
    result_dislike_user_ids = excluded.result_dislike_user_ids,
    gallery_posts = excluded.gallery_posts,
    gallery_likes = excluded.gallery_likes,
    gallery_dislikes = excluded.gallery_dislikes,
    gallery_comments = excluded.gallery_comments,
    gallery_applies = excluded.gallery_applies,
    gallery_apply_user_ids = excluded.gallery_apply_user_ids,
    prompt_unlocks = excluded.prompt_unlocks,
    prompt_unlock_user_ids = excluded.prompt_unlock_user_ids,
    quality_score = excluded.quality_score,
    positive_signal_score = excluded.positive_signal_score,
    negative_signal_score = excluded.negative_signal_score,
    quality_stage = case
        when analytics_prompt_slim_candidates.quality_stage in ('manual_keep', 'manual_reject', 'excellent', 'archived')
        then analytics_prompt_slim_candidates.quality_stage
        else excluded.quality_stage
    end,
    low_quality_reasons = excluded.low_quality_reasons,
    rule_version = excluded.rule_version,
    review_note = analytics_prompt_slim_candidates.review_note,
    reviewed_by = analytics_prompt_slim_candidates.reviewed_by,
    reviewed_at = analytics_prompt_slim_candidates.reviewed_at,
    updated_at = now(),
    refreshed_at = now()
"""


PROMPT_SLIM_STATUS_SQL = """
select
    count(*)::bigint as slim_count,
    count(*) filter (where quality_stage = 'candidate')::bigint as candidate_count,
    count(*) filter (where quality_stage = 'auto_rejected')::bigint as auto_rejected_count,
    count(*) filter (where quality_stage = 'manual_keep')::bigint as manual_keep_count,
    count(*) filter (where quality_stage = 'manual_reject')::bigint as manual_reject_count,
    count(*) filter (where quality_stage = 'excellent')::bigint as excellent_count,
    count(*) filter (where quality_stage = 'archived')::bigint as archived_count,
    max(refreshed_at) as refreshed_at
from analytics_prompt_slim_candidates
"""


async def ensure_prompt_slim_schema(conn: Any) -> None:
    for statement in CREATE_PROMPT_SLIM_SCHEMA_SQL:
        await conn.execute(statement)


async def refresh_prompt_slim_candidates(conn: Any) -> dict[str, Any]:
    await ensure_prompt_slim_schema(conn)
    mart_version = await conn.fetchrow(PROMPT_SLIM_MART_VERSION_SQL)
    normalization_version = (mart_version or {}).get("normalization_version")
    if normalization_version != PROMPT_NORMALIZATION_VERSION:
        raise RuntimeError(
            "prompt mart normalization version mismatch; refresh prompt mart before slim candidates"
        )

    old_version_delete_result = await conn.execute(
        DELETE_OLD_PROMPT_SLIM_VERSION_SQL,
        PROMPT_NORMALIZATION_VERSION,
    )
    rating_backfill_result = await conn.execute(BACKFILL_PROMPT_OCCURRENCE_RATING_SQL)
    upsert_result = await conn.execute(
        UPSERT_PROMPT_SLIM_CANDIDATES_SQL,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_SLIM_RULE_VERSION,
    )
    await conn.execute("analyze analytics_prompt_slim_candidates")
    status = dict(await conn.fetchrow(PROMPT_SLIM_STATUS_SQL))
    status["old_version_delete_result"] = old_version_delete_result
    status["rating_backfill_result"] = rating_backfill_result
    status["slim_upsert_result"] = upsert_result
    status["rule_version"] = PROMPT_SLIM_RULE_VERSION
    status["normalization_version"] = PROMPT_NORMALIZATION_VERSION
    return status
